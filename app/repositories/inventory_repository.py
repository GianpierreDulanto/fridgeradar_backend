from sqlalchemy.orm import Session

from app.models import InventoryItem, Product


class InventoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_paginated(
        self,
        household_id: str,
        zone_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[InventoryItem], int]:
        q = self.db.query(InventoryItem).filter(InventoryItem.household_id == household_id)
        if zone_id:
            q = q.filter(InventoryItem.zone_id == zone_id)
        if status:
            q = q.filter(InventoryItem.status == status)

        total = q.count()
        items = (
            q.order_by(InventoryItem.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return items, total

    def list_by_household(
        self,
        household_id: str,
        zone_id: str | None = None,
        status: str | None = None,
    ) -> list[InventoryItem]:
        items, _ = self.list_paginated(household_id, zone_id, status, limit=1000, offset=0)
        return items

    def get_by_id(self, item_id: str) -> InventoryItem | None:
        return self.db.query(InventoryItem).filter(InventoryItem.id == item_id).first()

    def create(self, **kwargs) -> InventoryItem:
        item = InventoryItem(**kwargs)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update(self, item: InventoryItem, **kwargs) -> InventoryItem:
        for k, v in kwargs.items():
            if v is not None:
                setattr(item, k, v)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete(self, item: InventoryItem) -> None:
        self.db.delete(item)
        self.db.commit()

    def find_product(self, household_id: str, name: str) -> Product | None:
        return (
            self.db.query(Product)
            .filter(Product.household_id == household_id, Product.name == name)
            .first()
        )

    def create_product(
        self,
        household_id: str,
        name: str,
        category: str | None,
        low_stock_threshold: float | None = None,
    ) -> Product:
        product = Product(
            household_id=household_id,
            name=name,
            category=category,
            low_stock_threshold=low_stock_threshold,
        )
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        return product

    def update_product_threshold(self, product: Product, threshold: float | None) -> Product:
        product.low_stock_threshold = threshold
        self.db.commit()
        self.db.refresh(product)
        return product
