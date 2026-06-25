from pydantic import BaseModel
from datetime import datetime


class ZoneCreate(BaseModel):
    household_id: str
    name: str
    type: str = "other"
    sort_order: int = 0


class ZoneUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    sort_order: int | None = None


class ZoneResponse(BaseModel):
    id: str
    household_id: str
    name: str
    type: str
    sort_order: int
    created_at: datetime

    class Config:
        from_attributes = True
