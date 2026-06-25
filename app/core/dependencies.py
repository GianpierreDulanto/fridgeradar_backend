import uuid
from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db


def get_household_for_user(
    user_id: str,
    db: Session = Depends(get_db),
) -> dict | None:
    from app.models import HouseholdMember

    membership = (
        db.query(HouseholdMember)
        .filter(HouseholdMember.user_id == user_id)
        .first()
    )
    if not membership:
        return None
    from app.models import Household

    household = db.query(Household).filter(Household.id == membership.household_id).first()
    if not household:
        return None
    return {
        "id": str(household.id),
        "name": household.name,
        "role": membership.role,
    }
