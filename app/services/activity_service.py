from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories.activity_repository import ActivityRepository
from app.repositories.household_repository import HouseholdRepository
from app.services.auth_service import get_current_user

from app.models import User


class ActivityService:
    def __init__(self, db: Session):
        self.repo = ActivityRepository(db)
        self.household_repo = HouseholdRepository(db)

    def list(self, household_id: str, limit: int, current_user: dict) -> list[dict]:
        self._check_membership(household_id, current_user["id"])
        entries = self.repo.list_by_household(household_id, limit)
        result = []
        for entry in entries:
            actor = (
                self.household_repo.db.query(User)
                .filter(User.id == entry.actor_user_id)
                .first()
            )
            result.append({
                "id": str(entry.id),
                "household_id": str(entry.household_id),
                "actor_user_id": str(entry.actor_user_id),
                "actor_name": actor.full_name if actor else None,
                "entity_type": entry.entity_type,
                "entity_id": str(entry.entity_id) if entry.entity_id else None,
                "action": entry.action,
                "metadata": entry.extra_data,
                "created_at": entry.created_at.isoformat(),
            })
        return result

    def log(
        self,
        household_id: str,
        actor_user_id: str,
        entity_type: str,
        entity_id: str | None,
        action: str,
        metadata: dict | None = None,
    ) -> None:
        self.repo.create(
            household_id=household_id,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            extra_data=metadata,
        )

    def _check_membership(self, household_id: str, user_id: str) -> None:
        members = self.household_repo.get_members(household_id)
        if not any(str(m.user_id) == user_id for m, _ in members):
            raise HTTPException(status_code=403, detail="Not a member of this household")


def get_activity_service(db: Session = Depends(get_db)) -> ActivityService:
    return ActivityService(db)
