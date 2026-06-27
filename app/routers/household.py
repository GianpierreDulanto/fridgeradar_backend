from fastapi import APIRouter, Depends

from app.schemas.household import (
    HouseholdCreate,
    HouseholdUpdate,
    HouseholdResponse,
    InviteRequest,
    MemberResponse,
)
from app.services.household_service import (
    HouseholdService,
    get_household_service,
)
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/households", tags=["households"])


@router.post("", response_model=HouseholdResponse)
def create_household(
    body: HouseholdCreate,
    current_user: dict = Depends(get_current_user),
    service: HouseholdService = Depends(get_household_service),
):
    return service.create(
        name=body.name,
        timezone=body.timezone,
        current_user=current_user,
        create_freezer=body.create_freezer,
        create_pantry=body.create_pantry,
    )


@router.get("", response_model=list[HouseholdResponse])
def list_households(
    current_user: dict = Depends(get_current_user),
    service: HouseholdService = Depends(get_household_service),
):
    return service.list_user_households(current_user=current_user)


@router.get("/{household_id}", response_model=HouseholdResponse)
def get_household(
    household_id: str,
    current_user: dict = Depends(get_current_user),
    service: HouseholdService = Depends(get_household_service),
):
    return service.get_by_id(household_id=household_id, current_user=current_user)


@router.patch("/{household_id}", response_model=HouseholdResponse)
def update_household(
    household_id: str,
    body: HouseholdUpdate,
    current_user: dict = Depends(get_current_user),
    service: HouseholdService = Depends(get_household_service),
):
    return service.update(
        household_id=household_id,
        name=body.name,
        timezone=body.timezone,
        current_user=current_user,
    )


@router.post("/{household_id}/invite")
def invite_member(
    household_id: str,
    body: InviteRequest,
    current_user: dict = Depends(get_current_user),
    service: HouseholdService = Depends(get_household_service),
):
    return service.invite_member(
        household_id=household_id,
        email=body.email,
        current_user=current_user,
    )


@router.get("/{household_id}/members", response_model=list[MemberResponse])
def list_members(
    household_id: str,
    current_user: dict = Depends(get_current_user),
    service: HouseholdService = Depends(get_household_service),
):
    return service.get_members(household_id=household_id, current_user=current_user)


@router.delete("/{household_id}/members/{member_id}")
def remove_member(
    household_id: str,
    member_id: str,
    current_user: dict = Depends(get_current_user),
    service: HouseholdService = Depends(get_household_service),
):
    return service.remove_member(household_id=household_id, member_id=member_id, current_user=current_user)
