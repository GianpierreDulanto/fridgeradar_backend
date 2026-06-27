from datetime import date

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.household_repository import HouseholdRepository
from app.repositories.zone_repository import ZoneRepository
from app.services.activity_service import ActivityService
from app.services.auth_service import get_current_user
from app.services.expiry_service import (
    DEFAULT_LOW_STOCK_THRESHOLD,
    compute_expiry,
    compute_low_stock_priority,
    resolve_low_stock_threshold,
)
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
        limit: int,
        offset: int,
        current_user: dict,
    ) -> dict:
        self._check_membership(household_id, current_user["id"])
        items, total = self.repo.list_paginated(
            household_id=household_id,
            zone_id=zone_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return {
            "items": [self._to_response(item) for item in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

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
        low_stock_threshold: float | None = None,
    ) -> dict:
        self._check_membership(household_id, current_user["id"])
        zone = self.zone_repo.get_by_id(zone_id)
        if not zone:
            raise HTTPException(status_code=404, detail="Zone not found")

        self._validate_quantity(quantity)
        purchase_d = self._parse_date(purchase_date)
        expiry_d = self._parse_date(expiry_date)
        self._validate_dates(purchase_d, expiry_d)

        product = self.repo.find_product(household_id, product_name)
        if not product:
            product = self.repo.create_product(
                household_id, product_name, product_category, low_stock_threshold,
            )
        elif low_stock_threshold is not None:
            product = self.repo.update_product_threshold(product, low_stock_threshold)

        if not product.image_url:
            image_url = await fetch_product_image(product_name)
            if image_url:
                product.image_url = image_url
                self.repo.db.commit()

        item = self.repo.create(
            household_id=household_id,
            product_id=product.id,
            zone_id=zone_id,
            quantity=quantity,
            unit=unit,
            purchase_date=purchase_d,
            expiry_date=expiry_d,
            status="active",
        )

        self.activity_service.log(
            household_id=household_id,
            actor_user_id=current_user["id"],
            entity_type="inventory_item",
            entity_id=str(item.id),
            action="created",
            metadata={"product_name": product_name, "zone_id": zone_id, "quantity": quantity},
        )

        return self._to_response(item)

    def update(self, item_id: str, updates: dict, current_user: dict) -> dict:
        item = self.repo.get_by_id(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        self._check_membership(str(item.household_id), current_user["id"])

        if "quantity" in updates and updates["quantity"] is not None:
            self._validate_quantity(updates["quantity"])

        if "expiry_date" in updates and updates["expiry_date"]:
            updates["expiry_date"] = self._parse_date(updates["expiry_date"])

        purchase_d = updates.get("purchase_date") or item.purchase_date
        expiry_d = updates.get("expiry_date") or item.expiry_date
        self._validate_dates(purchase_d, expiry_d)

        before = {k: getattr(item, k) for k in ("zone_id", "quantity", "unit", "expiry_date")}
        item = self.repo.update(item, **updates)
        after = {k: getattr(item, k) for k in ("zone_id", "quantity", "unit", "expiry_date")}

        changes = {
            k: {"from": self._changeable(before[k]), "to": self._changeable(after[k])}
            for k in before
            if self._changeable(before[k]) != self._changeable(after[k])
        }
        if changes:
            self.activity_service.log(
                household_id=str(item.household_id),
                actor_user_id=current_user["id"],
                entity_type="inventory_item",
                entity_id=str(item.id),
                action="updated",
                metadata={
                    "product_name": item.product.name if item.product else "",
                    "changes": changes,
                },
            )

        return self._to_response(item)

    def consume(self, item_id: str, quantity: float, current_user: dict) -> dict:
        item = self.repo.get_by_id(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        self._check_membership(str(item.household_id), current_user["id"])
        self._validate_quantity(quantity)

        previous_qty = float(item.quantity)
        new_qty = previous_qty - quantity
        if new_qty <= 0:
            item.status = "consumed"
            item.quantity = 0
            remaining = 0.0
        else:
            item.quantity = new_qty
            remaining = new_qty
        self.repo.update(item)

        self.activity_service.log(
            household_id=str(item.household_id),
            actor_user_id=current_user["id"],
            entity_type="inventory_item",
            entity_id=str(item.id),
            action="consumed",
            metadata={
                "product_name": item.product.name if item.product else "",
                "quantity_consumed": quantity,
                "remaining": remaining,
            },
        )

        return self._to_response(item)

    def discard(self, item_id: str, current_user: dict) -> dict:
        item = self.repo.get_by_id(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        self._check_membership(str(item.household_id), current_user["id"])
        item.status = "discarded"
        self.repo.update(item)

        self.activity_service.log(
            household_id=str(item.household_id),
            actor_user_id=current_user["id"],
            entity_type="inventory_item",
            entity_id=str(item.id),
            action="discarded",
            metadata={"product_name": item.product.name if item.product else ""},
        )

        return self._to_response(item)

    def restock(self, item_id: str, quantity: float, current_user: dict) -> dict:
        item = self.repo.get_by_id(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        self._check_membership(str(item.household_id), current_user["id"])
        self._validate_quantity(quantity)

        item.quantity = float(item.quantity) + quantity
        item.status = "active"
        self.repo.update(item)

        self.activity_service.log(
            household_id=str(item.household_id),
            actor_user_id=current_user["id"],
            entity_type="inventory_item",
            entity_id=str(item.id),
            action="restocked",
            metadata={
                "product_name": item.product.name if item.product else "",
                "quantity_added": quantity,
                "new_quantity": float(item.quantity),
            },
        )

        return self._to_response(item)

    def _check_membership(self, household_id: str, user_id: str) -> None:
        members = self.household_repo.get_members(household_id)
        if not any(str(m.user_id) == user_id for m, _ in members):
            raise HTTPException(status_code=403, detail="Not a member of this household")

    def _validate_quantity(self, quantity: float | None) -> None:
        if quantity is None or quantity <= 0:
            raise HTTPException(status_code=422, detail="quantity must be greater than 0")

    def _validate_dates(self, purchase_date: date | None, expiry_date: date | None) -> None:
        if purchase_date and expiry_date and expiry_date < purchase_date:
            raise HTTPException(
                status_code=422,
                detail="expiry_date must be on or after purchase_date",
            )

    def _parse_date(self, value) -> date | None:
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

    def _changeable(self, value):
        if value is None:
            return None
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    def _to_response(self, item) -> dict:
        zone = item.zone
        refrigerator = zone.refrigerator if zone else None
        product = item.product
        threshold = resolve_low_stock_threshold(product)
        quantity = float(item.quantity) if item.quantity is not None else 0.0
        is_low_stock = quantity < threshold
        low_stock_priority = compute_low_stock_priority(quantity, threshold) if is_low_stock else 0
        expiry_info = compute_expiry(item.expiry_date)
        expiry_priority = expiry_info["priority_score"]
        return {
            "id": str(item.id),
            "household_id": str(item.household_id),
            "product_id": str(item.product_id),
            "product_name": product.name if product else "",
            "product_category": product.category if product else None,
            "zone_id": str(item.zone_id),
            "zone_name": zone.name if zone else "",
            "zone_type": zone.type if zone else "",
            "refrigerator_id": str(refrigerator.id) if refrigerator else None,
            "refrigerator_name": refrigerator.name if refrigerator else None,
            "refrigerator_type": refrigerator.type if refrigerator else None,
            "quantity": quantity,
            "unit": item.unit,
            "low_stock_threshold": threshold,
            "is_low_stock": is_low_stock,
            "image_url": product.image_url if product else None,
            "purchase_date": item.purchase_date.isoformat() if item.purchase_date else None,
            "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
            "opened_date": item.opened_date.isoformat() if item.opened_date else None,
            "expiry_status": expiry_info["status"],
            "days_left": expiry_info["days_left"],
            "priority_score": max(expiry_priority, low_stock_priority),
            "status": item.status,
            "created_at": item.created_at.isoformat(),
        }


def get_inventory_service(db: Session = Depends(get_db)) -> InventoryService:
    return InventoryService(db)
