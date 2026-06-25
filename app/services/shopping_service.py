from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories.shopping_repository import ShoppingRepository
from app.repositories.household_repository import HouseholdRepository
from app.services.auth_service import get_current_user


class ShoppingService:
    def __init__(self, db: Session):
        self.repo = ShoppingRepository(db)
        self.household_repo = HouseholdRepository(db)

    def get_current(self, household_id: str, current_user: dict) -> list[dict]:
        self._check_membership(household_id, current_user["id"])
        items = self.repo.list_by_household(household_id)
        return [self._to_response(i) for i in items]

    def add_item(self, household_id: str, product_name: str, quantity: float | None, unit: str | None, current_user: dict) -> dict:
        self._check_membership(household_id, current_user["id"])
        item = self.repo.create(
            household_id=household_id,
            product_name=product_name,
            quantity=quantity,
            unit=unit,
        )
        return self._to_response(item)

    def update_item(self, item_id: str, updates: dict, current_user: dict) -> dict:
        item = self.repo.get_by_id(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        self._check_membership(str(item.household_id), current_user["id"])
        item = self.repo.update(item, **updates)
        return self._to_response(item)

    def delete_item(self, item_id: str, current_user: dict) -> None:
        item = self.repo.get_by_id(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        self._check_membership(str(item.household_id), current_user["id"])
        self.repo.delete(item)

    def _check_membership(self, household_id: str, user_id: str) -> None:
        members = self.household_repo.get_members(household_id)
        if not any(str(m.user_id) == user_id for m, _ in members):
            raise HTTPException(status_code=403, detail="Not a member of this household")

    def _to_response(self, item) -> dict:
        return {
            "id": str(item.id),
            "household_id": str(item.household_id),
            "product_name": item.product_name,
            "quantity": float(item.quantity) if item.quantity else None,
            "unit": item.unit,
            "checked": item.checked,
            "source": item.source,
            "created_at": item.created_at.isoformat(),
        }


def get_shopping_service(db: Session = Depends(get_db)) -> ShoppingService:
    return ShoppingService(db)
