from sqlalchemy.orm import Session, joinedload

from app.models import ActivityLog


class ActivityRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_household(self, household_id: str, limit: int = 50) -> list[ActivityLog]:
        return (
            self.db.query(ActivityLog)
            .options(joinedload(ActivityLog.actor))
            .filter(ActivityLog.household_id == household_id)
            .order_by(ActivityLog.created_at.desc())
            .limit(limit)
            .all()
        )

    def create(self, **kwargs) -> ActivityLog:
        entry = ActivityLog(**kwargs)
        self.db.add(entry)
        self.db.commit()
        return entry
