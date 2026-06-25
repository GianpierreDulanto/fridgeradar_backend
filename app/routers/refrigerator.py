from fastapi import APIRouter, Depends

from app.schemas.refrigerator import CreateRefrigeratorInput, UpdateRefrigeratorInput, RefrigeratorResponse
from app.services.refrigerator_service import RefrigeratorService, get_refrigerator_service
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/refrigerators", tags=["refrigerators"])


@router.get("", response_model=list[RefrigeratorResponse])
def list_refrigerators(
    household_id: str,
    current_user: dict = Depends(get_current_user),
    service: RefrigeratorService = Depends(get_refrigerator_service),
):
    return service.list_by_household(household_id=household_id, current_user=current_user)


@router.post("", response_model=RefrigeratorResponse)
def create_refrigerator(
    body: CreateRefrigeratorInput,
    current_user: dict = Depends(get_current_user),
    service: RefrigeratorService = Depends(get_refrigerator_service),
):
    return service.create(
        household_id=body.household_id,
        name=body.name,
        type=body.type,
        sort_order=body.sort_order,
        current_user=current_user,
    )


@router.patch("/{refrigerator_id}", response_model=RefrigeratorResponse)
def update_refrigerator(
    refrigerator_id: str,
    body: UpdateRefrigeratorInput,
    current_user: dict = Depends(get_current_user),
    service: RefrigeratorService = Depends(get_refrigerator_service),
):
    return service.update(
        refrigerator_id=refrigerator_id,
        name=body.name,
        type=body.type,
        sort_order=body.sort_order,
        current_user=current_user,
    )


@router.delete("/{refrigerator_id}")
def delete_refrigerator(
    refrigerator_id: str,
    current_user: dict = Depends(get_current_user),
    service: RefrigeratorService = Depends(get_refrigerator_service),
):
    service.delete(refrigerator_id=refrigerator_id, current_user=current_user)
    return {"message": "Refrigerator deleted"}
