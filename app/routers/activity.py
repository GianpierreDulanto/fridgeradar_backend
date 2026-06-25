from fastapi import APIRouter, Depends, Query

from app.schemas.activity import ActivityResponse
from app.services.activity_service import ActivityService, get_activity_service
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("", response_model=list[ActivityResponse])
def list_activity(
    household_id: str = Query(...),
    limit: int = Query(50, le=100),
    current_user: dict = Depends(get_current_user),
    service: ActivityService = Depends(get_activity_service),
):
    return service.list(
        household_id=household_id,
        limit=limit,
        current_user=current_user,
    )
