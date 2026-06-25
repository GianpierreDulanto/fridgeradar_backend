from sqlalchemy.orm import Session

from app.models import ShoppingListItem


class ShoppingRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_household(self, household_id: str) -> list[ShoppingListItem]:
        return (
            self.db.query(ShoppingListItem)
            .filter(ShoppingListItem.household_id == household_id)
            .order_by(ShoppingListItem.checked.asc(), ShoppingListItem.created_at.desc())
            .all()
        )

    def get_by_id(self, item_id: str) -> ShoppingListItem | None:
        return self.db.query(ShoppingListItem).filter(ShoppingListItem.id == item_id).first()

    def create(self, **kwargs) -> ShoppingListItem:
        item = ShoppingListItem(**kwargs)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update(self, item: ShoppingListItem, **kwargs) -> ShoppingListItem:
        for k, v in kwargs.items():
            if v is not None:
                setattr(item, k, v)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete(self, item: ShoppingListItem) -> None:
        self.db.delete(item)
        self.db.commit()
