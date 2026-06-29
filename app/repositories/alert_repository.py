from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from app.models import Alert


class AlertRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_household(
        self,
        household_id: str,
        severity: str | None = None,
    ) -> list[Alert]:
        q = self.db.query(Alert).filter(
            Alert.household_id == household_id,
            Alert.resolved_at.is_(None),
        )
        if severity:
            q = q.filter(Alert.severity == severity)
        return q.order_by(Alert.severity, Alert.due_at.asc().nullslast()).all()

    def list_open_by_household(self, household_id: str) -> list[Alert]:
        """All unresolved alerts of a household in one query (for dedup)."""
        return (
            self.db.query(Alert)
            .filter(
                Alert.household_id == household_id,
                Alert.resolved_at.is_(None),
            )
            .all()
        )

    def get_by_id(self, alert_id: str) -> Alert | None:
        return self.db.query(Alert).filter(Alert.id == alert_id).first()

    def create(self, **kwargs) -> Alert:
        alert = Alert(**kwargs)
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def mark_read(self, alert: Alert) -> Alert:
        alert.read_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def snooze(self, alert: Alert, duration_hours: int) -> Alert:
        """Move due_at forward by duration_hours and mark as read.

        If the alert has no due_at, fall back to now() + duration_hours.
        """
        from app.services.expiry_service import next_due_at
        alert.due_at = next_due_at(alert.due_at, duration_hours)
        alert.read_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def resolve(self, alert: Alert) -> Alert:
        alert.resolved_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def resolve_by_item(self, item_id: str) -> None:
        self.db.query(Alert).filter(
            Alert.inventory_item_id == item_id,
            Alert.resolved_at.is_(None),
        ).update({"resolved_at": datetime.now(timezone.utc)})
        self.db.commit()

    def bulk_create(self, alerts_data: Iterable[dict]) -> list[Alert]:
        rows = [Alert(**data) for data in alerts_data]
        self.db.add_all(rows)
        self.db.commit()
        for row in rows:
            self.db.refresh(row)
        return rows

    def get_active_count(self, household_id: str) -> int:
        return self.db.query(Alert).filter(
            Alert.household_id == household_id,
            Alert.resolved_at.is_(None),
        ).count()

    def get_unread_count(self, household_id: str) -> int:
        return self.db.query(Alert).filter(
            Alert.household_id == household_id,
            Alert.resolved_at.is_(None),
            Alert.read_at.is_(None),
        ).count()
