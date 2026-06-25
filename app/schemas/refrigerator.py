from pydantic import BaseModel
from datetime import datetime


class CreateRefrigeratorInput(BaseModel):
    household_id: str
    name: str
    type: str = "other"
    sort_order: int = 0


class UpdateRefrigeratorInput(BaseModel):
    name: str | None = None
    type: str | None = None
    sort_order: int | None = None


class RefrigeratorResponse(BaseModel):
    id: str
    household_id: str
    name: str
    type: str
    sort_order: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
