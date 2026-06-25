from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.household_repository import HouseholdRepository
from app.repositories.zone_repository import ZoneRepository
from app.services.activity_service import ActivityService
from app.services.auth_service import get_current_user
from app.services.food_api import fetch_product_image


class InventoryService:
    def __init__(self, db: Session):
        self.repo = InventoryRepository(db)
        self.household_repo = HouseholdRepository(db)
        self.zone_repo = ZoneRepository(db)
        self.activity_service = ActivityService(db)

    def list(
        self,
        household_id: str,
        zone_id: str | None,
        status: str | None,
        current_user: dict,
    ) -> list[dict]:
        self._check_membership(household_id, current_user["id"])
        items = self.repo.list_by_household(household_id, zone_id, status)
        return [self._to_response(item) for item in items]

    def get(self, item_id: str, current_user: dict) -> dict:
        item = self.repo.get_by_id(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        self._check_membership(str(item.household_id), current_user["id"])
        return self._to_response(item)

    async def create(
        self,
        household_id: str,
        product_name: str,
        product_category: str | None,
        zone_id: str,
        quantity: float,
        unit: str | None,
        purchase_date: str | None,
        expiry_date: str | None,
        current_user: dict,
    ) -> dict:
        self._check_membership(household_id, current_user["id"])
        zone = self.zone_repo.get_by_id(zone_id)
        if not zone:
            raise HTTPException(status_code=404, detail="Zone not found")

        product = self.repo.find_product(household_id, product_name)
        if not product:
            product = self.repo.create_product(household_id, product_name, product_category)

        if not product.image_url:
            image_url = await fetch_product_image(product_name)
            if image_url:
                product.image_url = image_url
                self.repo.db.commit()

        from datetime import date

        item = self.repo.create(
            household_id=household_id,
            product_id=product.id,
            zone_id=zone_id,
            quantity=quantity,
            unit=unit,
            purchase_date=date.fromisoformat(purchase_date) if purchase_date else None,
            expiry_date=date.fromisoformat(expiry_date) if expiry_date else None,
            status="active",
        )

        self.activity_service.log(
            household_id=household_id,
            actor_user_id=current_user["id"],
            entity_type="inventory_item",
            entity_id=str(item.id),
            action="created",
            metadata={"product_name": product_name, "zone_id": zone_id},
        )

        return self._to_response(item)

    def update(self, item_id: str, updates: dict, current_user: dict) -> dict:
        item = self.repo.get_by_id(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        self._check_membership(str(item.household_id), current_user["id"])

        if "expiry_date" in updates and updates["expiry_date"]:
            from datetime import date
            updates["expiry_date"] = date.fromisoformat(updates["expiry_date"])

        item = self.repo.update(item, **updates)
        return self._to_response(item)

    def consume(self, item_id: str, quantity: float, current_user: dict) -> dict:
        item = self.repo.get_by_id(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        self._check_membership(str(item.household_id), current_user["id"])

        new_qty = float(item.quantity) - quantity
        if new_qty <= 0:
            item.status = "consumed"
            item.quantity = 0
        else:
            item.quantity = new_qty
        self.repo.update(item)
        return self._to_response(item)

    def discard(self, item_id: str, current_user: dict) -> dict:
        item = self.repo.get_by_id(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        self._check_membership(str(item.household_id), current_user["id"])
        item.status = "discarded"
        self.repo.update(item)
        return self._to_response(item)

    def restock(self, item_id: str, quantity: float, current_user: dict) -> dict:
        item = self.repo.get_by_id(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        self._check_membership(str(item.household_id), current_user["id"])
        item.quantity = float(item.quantity) + quantity
        item.status = "active"
        self.repo.update(item)
        return self._to_response(item)

    def _check_membership(self, household_id: str, user_id: str) -> None:
        members = self.household_repo.get_members(household_id)
        if not any(str(m.user_id) == user_id for m, _ in members):
            raise HTTPException(status_code=403, detail="Not a member of this household")

    def _to_response(self, item) -> dict:
        return {
            "id": str(item.id),
            "household_id": str(item.household_id),
            "product_id": str(item.product_id),
            "product_name": item.product.name if item.product else "",
            "product_category": item.product.category if item.product else None,
            "zone_id": str(item.zone_id),
            "zone_name": item.zone.name if item.zone else "",
            "zone_type": item.zone.type if item.zone else "",
            "refrigerator_name": item.zone.refrigerator.name if item.zone and item.zone.refrigerator else "",
            "refrigerator_type": item.zone.refrigerator.type if item.zone and item.zone.refrigerator else "",
            "quantity": float(item.quantity),
            "unit": item.unit,
            "image_url": item.product.image_url if item.product else None,
            "purchase_date": item.purchase_date.isoformat() if item.purchase_date else None,
            "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
            "opened_date": item.opened_date.isoformat() if item.opened_date else None,
            "status": item.status,
            "created_at": item.created_at.isoformat(),
        }


def get_inventory_service(db: Session = Depends(get_db)) -> InventoryService:
    return InventoryService(db)
