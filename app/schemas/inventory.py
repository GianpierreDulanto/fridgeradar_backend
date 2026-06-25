from pydantic import BaseModel
from datetime import date, datetime


class InventoryCreate(BaseModel):
    household_id: str
    product_name: str
    product_category: str | None = None
    zone_id: str
    quantity: float = 1
    unit: str | None = None
    purchase_date: date | None = None
    expiry_date: date | None = None


class InventoryUpdate(BaseModel):
    zone_id: str | None = None
    quantity: float | None = None
    unit: str | None = None
    expiry_date: date | None = None


class InventoryAction(BaseModel):
    quantity: float = 1


class InventoryResponse(BaseModel):
    id: str
    household_id: str
    product_id: str
    product_name: str
    product_category: str | None
    image_url: str | None = None
    zone_id: str
    zone_name: str
    zone_type: str
    quantity: float
    unit: str | None
    purchase_date: date | None
    expiry_date: date | None
    opened_date: date | None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
