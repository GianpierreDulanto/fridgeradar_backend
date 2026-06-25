import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.database import engine, SessionLocal
from app.models import Zone, Refrigerator


def migrate():
    db = SessionLocal()
    try:
        zones = db.query(Zone).all()
        for zone in zones:
            existing = db.query(Refrigerator).filter(
                Refrigerator.household_id == zone.household_id,
                Refrigerator.name == zone.name
            ).first()
            if not existing:
                fridge = Refrigerator(
                    household_id=zone.household_id,
                    name=zone.name,
                    type=zone.type.value if hasattr(zone.type, 'value') else zone.type,
                    sort_order=zone.sort_order
                )
                db.add(fridge)
                db.flush()
                zone.refrigerator_id = fridge.id
        db.commit()
        print("Migration complete: created refrigerators from zones")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
