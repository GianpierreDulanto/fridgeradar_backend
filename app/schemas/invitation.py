from pydantic import BaseModel
from datetime import datetime


class InvitationResponse(BaseModel):
    id: str
    household_id: str
    household_name: str
    inviter_name: str
    role: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class InvitationAction(BaseModel):
    action: str  # "accept" or "reject"
