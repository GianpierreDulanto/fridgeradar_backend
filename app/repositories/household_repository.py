from sqlalchemy.orm import Session

from app.models import Household, HouseholdMember


class HouseholdRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, name: str, timezone: str, owner_user_id: str) -> Household:
        household = Household(name=name, timezone=timezone, owner_user_id=owner_user_id)
        self.db.add(household)
        self.db.commit()
        self.db.refresh(household)
        return household

    def get_by_id(self, household_id: str) -> Household | None:
        return self.db.query(Household).filter(Household.id == household_id).first()

    def update(self, household: Household, name: str | None, timezone: str | None) -> Household:
        if name is not None:
            household.name = name
        if timezone is not None:
            household.timezone = timezone
        self.db.commit()
        self.db.refresh(household)
        return household

    def get_by_user_id(self, user_id: str) -> list:
        return (
            self.db.query(Household)
            .join(HouseholdMember)
            .filter(HouseholdMember.user_id == user_id)
            .all()
        )

    def add_member(self, household_id: str, user_id: str, role: str = "member", invited_by: str | None = None, status: str = "active") -> HouseholdMember:
        member = HouseholdMember(household_id=household_id, user_id=user_id, role=role, invited_by=invited_by, status=status)
        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)
        return member

    def get_members(self, household_id: str) -> list:
        from app.models import User

        return (
            self.db.query(HouseholdMember, User)
            .join(User, HouseholdMember.user_id == User.id)
            .filter(HouseholdMember.household_id == household_id)
            .all()
        )

    def delete_member(self, member_id: str) -> None:
        member = self.db.query(HouseholdMember).filter(HouseholdMember.id == member_id).first()
        if member:
            self.db.delete(member)
            self.db.commit()
