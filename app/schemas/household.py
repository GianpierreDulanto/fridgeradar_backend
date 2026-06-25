from pydantic import BaseModel
from datetime import datetime


class HouseholdCreate(BaseModel):
    name: str
    timezone: str = "UTC"


class HouseholdUpdate(BaseModel):
    name: str | None = None
    timezone: str | None = None


class HouseholdResponse(BaseModel):
    id: str
    name: str
    timezone: str
    owner_user_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class MemberResponse(BaseModel):
    id: str
    user_id: str
    email: str
    full_name: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class InviteRequest(BaseModel):
    email: str
