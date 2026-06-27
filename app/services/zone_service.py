from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Zone
from app.repositories.zone_repository import ZoneRepository
from app.repositories.household_repository import HouseholdRepository
from app.services.auth_service import get_current_user


class ZoneService:
    def __init__(self, db: Session):
        self.repo = ZoneRepository(db)
        self.household_repo = HouseholdRepository(db)

    def list_by_household(self, household_id: str, current_user: dict) -> list[dict]:
        self._check_membership(household_id, current_user["id"])
        zones = self.repo.list_by_household(household_id)
        return [self._to_response(z) for z in zones]

    def create(self, household_id: str, name: str, type: str, sort_order: int, current_user: dict) -> dict:
        self._check_membership(household_id, current_user["id"])
        zone = self.repo.create(household_id=household_id, name=name, type=type, sort_order=sort_order)
        return self._to_response(zone)

    def update(self, zone_id: str, name: str | None, type: str | None, sort_order: int | None, current_user: dict) -> dict:
        zone = self.repo.get_by_id(zone_id)
        if not zone:
            raise HTTPException(status_code=404, detail="Zone not found")
        self._check_membership(str(zone.household_id), current_user["id"])
        zone = self.repo.update(zone, name, type, sort_order)
        return self._to_response(zone)

    def delete(self, zone_id: str, current_user: dict) -> None:
        zone = self.repo.get_by_id(zone_id)
        if not zone:
            raise HTTPException(status_code=404, detail="Zone not found")
        self._check_membership(str(zone.household_id), current_user["id"])
        self.repo.delete(zone)

    def _check_membership(self, household_id: str, user_id: str) -> None:
        members = self.household_repo.get_members(household_id)
        if not any(str(m.user_id) == user_id for m, _ in members):
            raise HTTPException(status_code=403, detail="Not a member of this household")

    def _to_response(self, zone: Zone) -> dict:
        return {
            "id": str(zone.id),
            "household_id": str(zone.household_id),
            "name": zone.name,
            "type": zone.type,
            "sort_order": zone.sort_order,
            "refrigerator_id": str(zone.refrigerator_id) if zone.refrigerator_id else None,
            "created_at": zone.created_at.isoformat(),
        }


def get_zone_service(db: Session = Depends(get_db)) -> ZoneService:
    return ZoneService(db)
