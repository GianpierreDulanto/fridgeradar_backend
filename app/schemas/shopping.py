from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal


class ShoppingItemCreate(BaseModel):
    household_id: str
    product_name: str
    quantity: float | None = None
    unit: str | None = None
    source: str | None = None  # e.g. "recipe:Fruit Salad"


class ShoppingItemUpdate(BaseModel):
    product_name: str | None = None
    quantity: float | None = None
    unit: str | None = None
    checked: bool | None = None


class ShoppingItemResponse(BaseModel):
    id: str
    household_id: str
    product_name: str
    quantity: float | None
    unit: str | None
    checked: bool
    source: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class AddRecipeMissingRequest(BaseModel):
    """Payload for POST /api/shopping-lists/from-recipe (RF-REC-015)."""

    household_id: str
    recipe_name: str
