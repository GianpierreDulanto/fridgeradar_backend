import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.core.database import SessionLocal
from app.models import Product, HouseholdMember
from app.models.refrigerator import Refrigerator
db = SessionLocal()
p = db.query(Product).first()
print("Product has image_url:", hasattr(p, "image_url"))
m = db.query(HouseholdMember).first()
print("Member has invited_by:", hasattr(m, "invited_by"))
print("Member has status:", hasattr(m, "status"))
print("Refrigerators count:", db.query(Refrigerator).count())
print("Zones:", db.query(type("Z", (object,), {"__tablename__": "zones"})).count() if False else "checking...")
from app.models import Zone
zones = db.query(Zone).all()
for z in zones:
    print(f"  Zone {z.name}: refrigerator_id={z.refrigerator_id}")
db.close()
