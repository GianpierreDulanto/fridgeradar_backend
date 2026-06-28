from pydantic import BaseModel, Field, model_validator
from datetime import date, datetime


class InventoryCreate(BaseModel):
    household_id: str
    product_name: str = Field(min_length=1, max_length=255)
    product_category: str | None = None
    zone_id: str
    quantity: float = Field(default=1, gt=0)
    unit: str | None = None
    purchase_date: date | None = None
    expiry_date: date | None = None
    low_stock_threshold: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _validate_dates(self) -> "InventoryCreate":
        if (
            self.purchase_date is not None
            and self.expiry_date is not None
            and self.expiry_date < self.purchase_date
        ):
            raise ValueError("expiry_date must be on or after purchase_date")
        return self


class InventoryUpdate(BaseModel):
    zone_id: str | None = None
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = None
    expiry_date: date | None = None
    low_stock_threshold: float | None = Field(default=None, gt=0)


class InventoryAction(BaseModel):
    quantity: float = Field(default=1, gt=0)


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
    refrigerator_id: str | None = None
    refrigerator_name: str | None = None
    refrigerator_type: str | None = None
    quantity: float
    unit: str | None
    low_stock_threshold: float | None = None
    is_low_stock: bool = False
    expiry_status: str | None = None
    days_left: int | None = None
    priority_score: float = 0
    purchase_date: date | None
    expiry_date: date | None
    opened_date: date | None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class InventoryListResponse(BaseModel):
    """Paginated wrapper for GET /api/inventory-items."""
    items: list[InventoryResponse]
    total: int
    limit: int
    offset: int
