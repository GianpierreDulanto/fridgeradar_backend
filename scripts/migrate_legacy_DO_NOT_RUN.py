"""
!!! DEPRECATED — DO NOT RUN !!!

Este script quedó obsoleto. Su propósito era crear un Refrigerator por cada
Zone preexistente y asignarlo. Ese trabajo lo hace ahora automáticamente
`household_service.create()` cuando se crea un household, y `Zone` siempre
nace con su `refrigerator_id` ya definido.

Si lo corrés sobre una DB ya migrada, va a CREAR DUPLICADOS porque hace
lookup por (household_id, name) exacto y los refrigerators por defecto
("Refrigerator" / "Pantry") no coinciden con los nombres de zones
("Main Shelves" / "Shelves").

Para inicializar la base de datos desde cero, usá:

    python scripts/reset_db.py

Para verificar la base, usá:

    python scripts/verify_db.py

Se conserva solo como referencia histórica del brief original.
"""

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
