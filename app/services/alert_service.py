from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Household
from app.repositories.alert_repository import AlertRepository
from app.repositories.household_repository import HouseholdRepository
from app.repositories.inventory_repository import InventoryRepository
from app.services.auth_service import get_current_user
from app.services.expiry_service import (
    DEFAULT_LOW_STOCK_THRESHOLD,
    compute_expiry,
    compute_low_stock_priority,
    resolve_low_stock_threshold,
)


class AlertService:
    def __init__(self, db: Session):
        self.repo = AlertRepository(db)
        self.household_repo = HouseholdRepository(db)
        self.inventory_repo = InventoryRepository(db)

    def list(
        self,
        household_id: str,
        severity: str | None,
        current_user: dict,
    ) -> list[dict]:
        self._check_membership(household_id, current_user["id"])
        alerts = self.repo.list_by_household(household_id, severity)
        return [self._to_response(alert) for alert in alerts]

    def mark_read(self, alert_id: str, current_user: dict) -> dict:
        alert = self.repo.get_by_id(alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        self._check_membership(str(alert.household_id), current_user["id"])
        alert = self.repo.mark_read(alert)
        return self._to_response(alert)

    def snooze(
        self,
        alert_id: str,
        duration_hours: int,
        current_user: dict,
    ) -> dict:
        alert = self.repo.get_by_id(alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        self._check_membership(str(alert.household_id), current_user["id"])
        alert = self.repo.snooze(alert, duration_hours)
        return self._to_response(alert)

    def scan_and_generate(
        self,
        household_id: str | None = None,
        current_user: dict | None = None,
    ) -> dict:
        """Scan and generate alerts. Used by both the manual run-preview endpoint
        and the cron scheduler. When called by an HTTP endpoint, pass current_user
        so we can validate membership. When called by the scheduler (current_user
        is None), the household_id must also be None (we process all households).
        """
        if household_id and current_user is not None:
            self._check_membership(household_id, current_user["id"])
            households = [self.household_repo.get_by_id(household_id)]
        elif household_id is None and current_user is None:
            households = self.household_repo.db.query(Household).all()
        elif household_id is None and current_user is not None:
            raise HTTPException(
                status_code=400,
                detail="household_id is required when called by a user",
            )
        else:
            households = []

        today = date.today()
        total_created = 0

        for household in households:
            if household is None:
                continue
            total_created += self._scan_one_household(household, today)

        total_active = (
            self.repo.get_active_count(household_id) if household_id else None
        )
        return {"created": total_created, "total_active": total_active}

    def _scan_one_household(self, household, today: date) -> int:
        """Scan one household's inventory and return count of alerts created."""
        items = self.inventory_repo.list_by_household(
            str(household.id), status="active"
        )
        if not items:
            return 0

        existing_alerts = self.repo.list_open_by_household(str(household.id))
        existing_keys = {
            (str(a.type), str(a.inventory_item_id) if a.inventory_item_id else None)
            for a in existing_alerts
        }

        new_alerts: list[dict] = []
        for item in items:
            new_alerts.extend(self._alerts_for_item(item, today, existing_keys))

        if new_alerts:
            self.repo.bulk_create(new_alerts)

        return len(new_alerts)

    def _alerts_for_item(self, item, today: date, existing_keys: set) -> list[dict]:
        """Return the list of alert dicts to create for an item, or [] if none."""
        out: list[dict] = []
        product_name = item.product.name if item.product else "Item"

        expiry_info = compute_expiry(item.expiry_date, today)
        expiry_status = expiry_info["status"]

        if expiry_status:
            spec = self._expiry_alert_spec(expiry_status, expiry_info["days_left"], product_name, item.expiry_date)
            if spec:
                key = (spec["type"], str(item.id))
                if key not in existing_keys:
                    spec["household_id"] = item.household_id
                    spec["inventory_item_id"] = item.id
                    out.append(spec)

        if item.product is not None and item.quantity is not None:
            threshold = resolve_low_stock_threshold(item.product)
            if float(item.quantity) < threshold:
                priority = compute_low_stock_priority(item.quantity, threshold)
                key = ("low_stock", str(item.id))
                if key not in existing_keys:
                    out.append({
                        "household_id": item.household_id,
                        "inventory_item_id": item.id,
                        "type": "low_stock",
                        "severity": "warning" if float(item.quantity) > 0 else "critical",
                        "title": f"{product_name} is low on stock",
                        "message": f"Quantity {item.quantity} {item.unit or ''} is below threshold of {threshold}",
                        "priority_score": priority,
                    })

        return out

    @staticmethod
    def _expiry_alert_spec(status: str, days_left: int, product_name: str, expiry_date) -> dict | None:
        if status == "expired":
            return {
                "type": "expired",
                "severity": "critical",
                "title": f"{product_name} has expired",
                "message": f"Expired {abs(days_left)} day(s) ago",
                "due_at": datetime.combine(expiry_date, datetime.min.time(), tzinfo=timezone.utc),
                "priority_score": 100,
            }
        if status == "today":
            return {
                "type": "expiring_today",
                "severity": "critical",
                "title": f"{product_name} expires today",
                "message": "Use or discard today",
                "due_at": datetime.combine(expiry_date, datetime.min.time(), tzinfo=timezone.utc),
                "priority_score": 90,
            }
        if status == "urgent":
            return {
                "type": "expiring_soon",
                "severity": "warning",
                "title": f"{product_name} expiring in {days_left} day(s)",
                "message": f"Expires on {expiry_date}",
                "due_at": datetime.combine(expiry_date, datetime.min.time(), tzinfo=timezone.utc),
                "priority_score": 70 + (3 - days_left),
            }
        if status == "attention":
            return {
                "type": "expiring_soon",
                "severity": "info",
                "title": f"{product_name} expiring in {days_left} day(s)",
                "message": f"Expires on {expiry_date}",
                "due_at": datetime.combine(expiry_date, datetime.min.time(), tzinfo=timezone.utc),
                "priority_score": 40 + (7 - days_left) * 5,
            }
        return None

    def _check_membership(self, household_id: str, user_id: str) -> None:
        members = self.household_repo.get_members(household_id)
        if not any(str(m.user_id) == user_id for m, _ in members):
            raise HTTPException(status_code=403, detail="Not a member of this household")

    def _to_response(self, alert) -> dict:
        product_name = None
        if alert.inventory_item_id:
            item = self.inventory_repo.get_by_id(str(alert.inventory_item_id))
            if item and item.product:
                product_name = item.product.name
        return {
            "id": str(alert.id),
            "household_id": str(alert.household_id),
            "inventory_item_id": str(alert.inventory_item_id) if alert.inventory_item_id else None,
            "type": alert.type,
            "severity": alert.severity,
            "title": alert.title,
            "message": alert.message,
            "due_at": alert.due_at.isoformat() if alert.due_at else None,
            "read_at": alert.read_at.isoformat() if alert.read_at else None,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "priority_score": float(alert.priority_score) if alert.priority_score is not None else 0,
            "created_at": alert.created_at.isoformat(),
            "product_name": product_name,
        }


def get_alert_service(db: Session = Depends(get_db)) -> AlertService:
    return AlertService(db)
