from datetime import date, datetime, timezone
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories.alert_repository import AlertRepository
from app.repositories.household_repository import HouseholdRepository
from app.repositories.inventory_repository import InventoryRepository
from app.services.auth_service import get_current_user


class AlertService:
    def __init__(self, db: Session):
        self.repo = AlertRepository(db)
        self.household_repo = HouseholdRepository(db)
        self.inventory_repo = InventoryRepository(db)

    def list(self, household_id: str, severity: str | None, current_user: dict) -> list[dict]:
        self._check_membership(household_id, current_user["id"])
        alerts = self.repo.list_by_household(household_id, severity)
        result = []
        for alert in alerts:
            d = self._to_response(alert)
            if alert.inventory_item_id:
                item = self.inventory_repo.get_by_id(str(alert.inventory_item_id))
                if item and item.product:
                    d["product_name"] = item.product.name
            result.append(d)
        return result

    def mark_read(self, alert_id: str, current_user: dict) -> dict:
        alert = self.repo.get_by_id(alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        self._check_membership(str(alert.household_id), current_user["id"])
        alert = self.repo.mark_read(alert)
        return self._to_response(alert)

    def snooze(self, alert_id: str, current_user: dict) -> dict:
        alert = self.repo.get_by_id(alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        self._check_membership(str(alert.household_id), current_user["id"])
        alert = self.repo.snooze(alert)
        return self._to_response(alert)

    def scan_and_generate(self, household_id: str | None = None) -> dict:
        today = date.today()

        if household_id:
            households = [h for h in [self.household_repo.get_by_id(household_id)] if h]
        else:
            from app.models import Household
            db = self.household_repo.db
            households = db.query(Household).all()

        total_created = 0

        for household in households:
            items = self.inventory_repo.list_by_household(str(household.id), status="active")

            for item in items:
                if not item.expiry_date:
                    continue

                diff_days = (item.expiry_date - today).days

                alert_type = None
                severity = None
                title = ""
                message = ""

                if diff_days < 0:
                    alert_type = "expired"
                    severity = "critical"
                    title = f"{item.product.name} has expired"
                    message = f"Expired {abs(diff_days)} day(s) ago"
                elif diff_days == 0:
                    alert_type = "expiring_today"
                    severity = "critical"
                    title = f"{item.product.name} expires today"
                    message = "Use or discard today"
                elif diff_days <= 3:
                    alert_type = "expiring_soon"
                    severity = "warning"
                    title = f"{item.product.name} expiring in {diff_days} days"
                    message = f"Expires on {item.expiry_date}"
                elif diff_days <= 7:
                    alert_type = "expiring_soon"
                    severity = "info"
                    title = f"{item.product.name} expiring in {diff_days} days"
                    message = f"Expires on {item.expiry_date}"
                else:
                    continue

                existing = self.repo.list_by_household(str(household.id))
                already_exists = any(
                    a.type == alert_type and str(a.inventory_item_id) == str(item.id)
                    for a in existing
                )
                if already_exists:
                    continue

                self.repo.create(
                    household_id=item.household_id,
                    inventory_item_id=item.id,
                    type=alert_type,
                    severity=severity,
                    title=title,
                    message=message,
                    due_at=datetime.combine(item.expiry_date, datetime.min.time()).replace(tzinfo=timezone.utc),
                )
                total_created += 1

        total_active = 0
        if household_id:
            total_active = self.repo.get_active_count(household_id)
        return {"created": total_created, "total_active": total_active}

    def _check_membership(self, household_id: str, user_id: str) -> None:
        members = self.household_repo.get_members(household_id)
        if not any(str(m.user_id) == user_id for m, _ in members):
            raise HTTPException(status_code=403, detail="Not a member of this household")

    def _to_response(self, alert) -> dict:
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
            "created_at": alert.created_at.isoformat(),
            "product_name": None,
        }


def get_alert_service(db: Session = Depends(get_db)) -> AlertService:
    return AlertService(db)
