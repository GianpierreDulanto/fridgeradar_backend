from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import HouseholdMember, User, Household
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/invitations", tags=["invitations"])


@router.get("/pending")
def list_pending_invitations(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    members = (
        db.query(HouseholdMember, Household, User)
        .join(Household, HouseholdMember.household_id == Household.id)
        .join(User, HouseholdMember.invited_by == User.id)
        .filter(HouseholdMember.user_id == current_user["id"])
        .filter(HouseholdMember.status == "pending")
        .all()
    )
    result = []
    for member, household, inviter in members:
        result.append({
            "id": str(member.id),
            "member_id": str(member.id),
            "household_id": str(household.id),
            "household_name": household.name,
            "inviter_name": inviter.full_name,
            "role": member.role,
            "status": member.status,
            "created_at": member.created_at.isoformat(),
        })
    return result


@router.post("/{member_id}/accept")
def accept_invitation(
    member_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    member = db.query(HouseholdMember).filter(HouseholdMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if str(member.user_id) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not your invitation")
    if member.status != "pending":
        raise HTTPException(status_code=400, detail="Invitation is not pending")
    member.status = "active"
    db.commit()
    return {"message": "Invitation accepted"}


@router.post("/{member_id}/reject")
def reject_invitation(
    member_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    member = db.query(HouseholdMember).filter(HouseholdMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if str(member.user_id) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not your invitation")
    if member.status != "pending":
        raise HTTPException(status_code=400, detail="Invitation is not pending")
    member.status = "rejected"
    db.commit()
    return {"message": "Invitation rejected"}
