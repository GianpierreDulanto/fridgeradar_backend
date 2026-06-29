from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories.refrigerator_repository import RefrigeratorRepository
from app.repositories.household_repository import HouseholdRepository
from app.schemas.refrigerator import RefrigeratorResponse
from app.services.auth_service import get_current_user


class RefrigeratorService:
    def __init__(self, db: Session):
        self.repo = RefrigeratorRepository(db)
        self.household_repo = HouseholdRepository(db)

    def list_by_household(self, household_id: str, current_user: dict) -> list[RefrigeratorResponse]:
        self._check_membership(household_id, current_user["id"])
        fridges = self.repo.list_by_household(household_id)
        return [self._to_response(f) for f in fridges]

    def create(self, household_id: str, name: str, type: str, sort_order: int, current_user: dict) -> RefrigeratorResponse:
        self._check_membership(household_id, current_user["id"])
        fridge = self.repo.create(household_id=household_id, name=name, type=type, sort_order=sort_order)
        return self._to_response(fridge)

    def update(self, refrigerator_id: str, name: str | None, type: str | None, sort_order: int | None, current_user: dict) -> RefrigeratorResponse:
        fridge = self.repo.get_by_id(refrigerator_id)
        if not fridge:
            raise HTTPException(status_code=404, detail="Refrigerator not found")
        self._check_membership(str(fridge.household_id), current_user["id"])
        fridge = self.repo.update(fridge, name, type, sort_order)
        return self._to_response(fridge)

    def delete(self, refrigerator_id: str, current_user: dict) -> None:
        fridge = self.repo.get_by_id(refrigerator_id)
        if not fridge:
            raise HTTPException(status_code=404, detail="Refrigerator not found")
        self._check_membership(str(fridge.household_id), current_user["id"])
        self.repo.delete(fridge)

    def _check_membership(self, household_id: str, user_id: str) -> None:
        members = self.household_repo.get_members(household_id)
        if not any(str(m.user_id) == user_id for m, _ in members):
            raise HTTPException(status_code=403, detail="Not a member of this household")

    def _to_response(self, fridge) -> RefrigeratorResponse:
        return RefrigeratorResponse(
            id=str(fridge.id),
            household_id=str(fridge.household_id),
            name=fridge.name,
            type=fridge.type,
            sort_order=fridge.sort_order,
            created_at=fridge.created_at,
            updated_at=fridge.updated_at,
        )


def get_refrigerator_service(db: Session = Depends(get_db)) -> RefrigeratorService:
    return RefrigeratorService(db)
