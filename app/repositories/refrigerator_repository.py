from sqlalchemy.orm import Session

from app.models import Refrigerator


class RefrigeratorRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_household(self, household_id: str) -> list[Refrigerator]:
        return (
            self.db.query(Refrigerator)
            .filter(Refrigerator.household_id == household_id)
            .order_by(Refrigerator.sort_order)
            .all()
        )

    def get_by_id(self, refrigerator_id: str) -> Refrigerator | None:
        return self.db.query(Refrigerator).filter(Refrigerator.id == refrigerator_id).first()

    def create(self, household_id: str, name: str, type: str, sort_order: int) -> Refrigerator:
        fridge = Refrigerator(household_id=household_id, name=name, type=type, sort_order=sort_order)
        self.db.add(fridge)
        self.db.commit()
        self.db.refresh(fridge)
        return fridge

    def update(self, fridge: Refrigerator, name: str | None, type: str | None, sort_order: int | None) -> Refrigerator:
        if name is not None:
            fridge.name = name
        if type is not None:
            fridge.type = type
        if sort_order is not None:
            fridge.sort_order = sort_order
        self.db.commit()
        self.db.refresh(fridge)
        return fridge

    def delete(self, fridge: Refrigerator) -> None:
        self.db.delete(fridge)
        self.db.commit()
