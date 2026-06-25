from fastapi import APIRouter, Depends

from app.schemas.zone import ZoneCreate, ZoneUpdate, ZoneResponse
from app.services.zone_service import ZoneService, get_zone_service
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/zones", tags=["zones"])


@router.get("", response_model=list[ZoneResponse])
def list_zones(
    household_id: str,
    current_user: dict = Depends(get_current_user),
    service: ZoneService = Depends(get_zone_service),
):
    return service.list_by_household(household_id=household_id, current_user=current_user)


@router.post("", response_model=ZoneResponse)
def create_zone(
    body: ZoneCreate,
    current_user: dict = Depends(get_current_user),
    service: ZoneService = Depends(get_zone_service),
):
    return service.create(
        household_id=body.household_id,
        name=body.name,
        type=body.type,
        sort_order=body.sort_order,
        current_user=current_user,
    )


@router.patch("/{zone_id}", response_model=ZoneResponse)
def update_zone(
    zone_id: str,
    body: ZoneUpdate,
    current_user: dict = Depends(get_current_user),
    service: ZoneService = Depends(get_zone_service),
):
    return service.update(
        zone_id=zone_id,
        name=body.name,
        type=body.type,
        sort_order=body.sort_order,
        current_user=current_user,
    )


@router.delete("/{zone_id}")
def delete_zone(
    zone_id: str,
    current_user: dict = Depends(get_current_user),
    service: ZoneService = Depends(get_zone_service),
):
    service.delete(zone_id=zone_id, current_user=current_user)
    return {"message": "Zone deleted"}
