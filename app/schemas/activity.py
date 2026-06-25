from pydantic import BaseModel
from datetime import datetime


class ActivityResponse(BaseModel):
    id: str
    household_id: str
    actor_user_id: str
    actor_name: str | None = None
    entity_type: str
    entity_id: str | None
    action: str
    metadata: dict | None
    created_at: datetime

    class Config:
        from_attributes = True
