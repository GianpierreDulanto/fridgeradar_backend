from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories.household_repository import HouseholdRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import get_current_user


class HouseholdService:
    def __init__(self, db: Session):
        self.repo = HouseholdRepository(db)
        self.user_repo = UserRepository(db)

    def create(
        self,
        name: str,
        timezone: str,
        current_user: dict,
        create_freezer: bool = True,
        create_pantry: bool = False,
    ) -> dict:
        household = self.repo.create(name=name, timezone=timezone, owner_user_id=current_user["id"])
        self.repo.add_member(household_id=str(household.id), user_id=current_user["id"], role="owner")

        from app.models.refrigerator import Refrigerator
        from app.models import Zone

        refrigerators_to_add: list[Refrigerator] = [
            Refrigerator(household_id=household.id, name="Refrigerator", type="refrigerator", sort_order=0),
        ]
        if create_freezer:
            refrigerators_to_add.append(
                Refrigerator(household_id=household.id, name="Freezer", type="freezer", sort_order=1)
            )
        if create_pantry:
            sort_order = 2 if create_freezer else 1
            refrigerators_to_add.append(
                Refrigerator(household_id=household.id, name="Pantry", type="pantry", sort_order=sort_order)
            )
        self.repo.db.add_all(refrigerators_to_add)
        self.repo.db.flush()

        zones_to_add: list[Zone] = [
            Zone(
                household_id=household.id, refrigerator_id=refrigerators_to_add[0].id,
                name="Main Shelves", type="refrigerator", sort_order=0,
            ),
        ]
        if create_freezer:
            zones_to_add.append(
                Zone(
                    household_id=household.id, refrigerator_id=refrigerators_to_add[1].id,
                    name="Freezer Drawers", type="freezer", sort_order=0,
                )
            )
        if create_pantry:
            pantry_index = 2 if create_freezer else 1
            zones_to_add.append(
                Zone(
                    household_id=household.id, refrigerator_id=refrigerators_to_add[pantry_index].id,
                    name="Pantry Shelves", type="pantry", sort_order=0,
                )
            )
        self.repo.db.add_all(zones_to_add)
        self.repo.db.commit()

        return self._to_response(household)

    def get_by_id(self, household_id: str, current_user: dict) -> dict:
        self._check_membership(household_id, current_user["id"])
        household = self.repo.get_by_id(household_id)
        if not household:
            raise HTTPException(status_code=404, detail="Household not found")
        return self._to_response(household)

    def update(self, household_id: str, name: str | None, timezone: str | None, current_user: dict) -> dict:
        self._check_owner(household_id, current_user["id"])
        household = self.repo.get_by_id(household_id)
        if not household:
            raise HTTPException(status_code=404, detail="Household not found")
        household = self.repo.update(household, name, timezone)
        return self._to_response(household)

    def list_user_households(self, current_user: dict) -> list[dict]:
        households = self.repo.get_by_user_id(current_user["id"])
        return [self._to_response(h) for h in households]

    def invite_member(self, household_id: str, email: str, current_user: dict) -> dict:
        self._check_admin(household_id, current_user["id"])
        user = self.user_repo.get_by_email(email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        existing_members = self.repo.get_members(household_id)
        for m, _ in existing_members:
            if str(m.user_id) == str(user.id):
                raise HTTPException(status_code=409, detail="User already a member")
        member = self.repo.add_member(household_id=household_id, user_id=str(user.id), invited_by=current_user["id"], status="pending")
        return {"id": str(member.id), "user_id": str(user.id), "email": user.email, "full_name": user.full_name, "role": member.role, "status": member.status}

    def remove_member(self, household_id: str, member_id: str, current_user: dict) -> dict:
        self._check_owner(household_id, current_user["id"])
        members = self.repo.get_members(household_id)
        target = None
        for m, u in members:
            if str(m.id) == member_id:
                target = (m, u)
                break
        if not target:
            raise HTTPException(status_code=404, detail="Member not found")
        member, user = target
        if str(member.user_id) == current_user["id"]:
            raise HTTPException(status_code=400, detail="Cannot remove yourself")
        self.repo.delete_member(member_id)
        return {"message": "Member removed", "user_id": str(user.id), "full_name": user.full_name}

    def get_members(self, household_id: str, current_user: dict) -> list[dict]:
        self._check_membership(household_id, current_user["id"])
        members = self.repo.get_members(household_id)
        result = []
        for member, user in members:
            result.append({
                "id": str(member.id),
                "user_id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "role": member.role,
                "created_at": member.created_at.isoformat(),
            })
        return result

    def _check_membership(self, household_id: str, user_id: str) -> None:
        members = self.repo.get_members(household_id)
        if not any(str(m.user_id) == user_id for m, _ in members):
            raise HTTPException(status_code=403, detail="Not a member of this household")

    def _check_owner(self, household_id: str, user_id: str) -> None:
        household = self.repo.get_by_id(household_id)
        if not household or str(household.owner_user_id) != user_id:
            raise HTTPException(status_code=403, detail="Only the owner can perform this action")

    def _check_admin(self, household_id: str, user_id: str) -> None:
        members = self.repo.get_members(household_id)
        for m, _ in members:
            if str(m.user_id) == user_id and m.role in ("owner", "admin"):
                return
        raise HTTPException(status_code=403, detail="Admin or owner role required")

    def _to_response(self, household) -> dict:
        return {
            "id": str(household.id),
            "name": household.name,
            "timezone": household.timezone,
            "owner_user_id": str(household.owner_user_id),
            "created_at": household.created_at.isoformat(),
        }


def get_household_service(db: Session = Depends(get_db)) -> HouseholdService:
    return HouseholdService(db)
