from pydantic import BaseModel, Field
from datetime import datetime


class AlertResponse(BaseModel):
    id: str
    household_id: str
    inventory_item_id: str | None
    type: str
    severity: str
    title: str
    message: str | None
    due_at: datetime | None
    read_at: datetime | None
    resolved_at: datetime | None
    priority_score: float = 0
    created_at: datetime
    product_name: str | None = None

    class Config:
        from_attributes = True


class AlertScanResult(BaseModel):
    created: int
    total_active: int


class AlertSnooze(BaseModel):
    duration_hours: int = Field(default=24, ge=1, le=168)
