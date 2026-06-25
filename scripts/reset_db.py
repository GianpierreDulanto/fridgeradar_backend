import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.core.database import Base, engine
from app.models import (
    User, Household, HouseholdMember, Zone, Product, InventoryItem,
    Alert, ShoppingListItem, ActivityLog
)
from app.models.refrigerator import Refrigerator
from sqlalchemy import text
from passlib.hash import bcrypt
from datetime import date, datetime, timezone, timedelta
import uuid

def drop_all():
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS activity_log CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS alerts CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS shopping_list_items CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS inventory_items CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS products CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS zones CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS refrigerators CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS household_members CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS households CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))
        conn.execute(text("DROP TYPE IF EXISTS item_status CASCADE"))
        conn.execute(text("DROP TYPE IF EXISTS zone_type CASCADE"))
        conn.execute(text("DROP TYPE IF EXISTS household_role CASCADE"))
        conn.execute(text("DROP TYPE IF EXISTS alert_type CASCADE"))
        conn.execute(text("DROP TYPE IF EXISTS alert_severity CASCADE"))
        conn.execute(text("DROP TYPE IF EXISTS entity_type CASCADE"))
        conn.commit()
    print("All tables dropped")

def create_all():
    Base.metadata.create_all(bind=engine)
    print("All tables created")

def seed():
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        pw = bcrypt.hash("password123")

        alice = User(id=uuid.uuid4(), email="alice@example.com", password_hash=pw, full_name="Alice Johnson")
        bob = User(id=uuid.uuid4(), email="bob@example.com", password_hash=pw, full_name="Bob Smith")
        db.add_all([alice, bob])
        db.flush()

        casa = Household(id=uuid.uuid4(), name="Casa de Alice", timezone="America/Mexico_City", owner_user_id=alice.id)
        db.add(casa)
        db.flush()

        member_owner = HouseholdMember(id=uuid.uuid4(), household_id=casa.id, user_id=alice.id, role="owner", status="active")
        db.add(member_owner)
        db.flush()

        fridge = Refrigerator(id=uuid.uuid4(), household_id=casa.id, name="Main Refrigerator", type="refrigerator", sort_order=0)
        freezer = Refrigerator(id=uuid.uuid4(), household_id=casa.id, name="Freezer", type="freezer", sort_order=1)
        pantry = Refrigerator(id=uuid.uuid4(), household_id=casa.id, name="Pantry", type="pantry", sort_order=2)
        db.add_all([fridge, freezer, pantry])
        db.flush()

        zone_fridge = Zone(id=uuid.uuid4(), household_id=casa.id, refrigerator_id=fridge.id, name="Fridge Shelves", type="refrigerator", sort_order=0)
        zone_freezer = Zone(id=uuid.uuid4(), household_id=casa.id, refrigerator_id=freezer.id, name="Freezer Drawers", type="freezer", sort_order=0)
        zone_pantry = Zone(id=uuid.uuid4(), household_id=casa.id, refrigerator_id=pantry.id, name="Pantry Shelves", type="pantry", sort_order=0)
        db.add_all([zone_fridge, zone_freezer, zone_pantry])
        db.flush()

        milk = Product(id=uuid.uuid4(), household_id=casa.id, name="Whole Milk", category="Dairy", default_unit="lt",
                       image_url="https://images.openfoodfacts.org/images/products/000/000/000/0001/front_en.1.200.jpg")
        eggs = Product(id=uuid.uuid4(), household_id=casa.id, name="Free-Range Eggs", category="Poultry", default_unit="units",
                       image_url="https://images.openfoodfacts.org/images/products/000/000/000/0002/front_en.1.200.jpg")
        chicken = Product(id=uuid.uuid4(), household_id=casa.id, name="Chicken Breast", category="Meat", default_unit="kg",
                          image_url="https://images.openfoodfacts.org/images/products/000/000/000/0003/front_en.1.200.jpg")
        cheese = Product(id=uuid.uuid4(), household_id=casa.id, name="Cheddar Cheese", category="Dairy", default_unit="kg")
        tomato = Product(id=uuid.uuid4(), household_id=casa.id, name="Tomato Sauce", category="Canned", default_unit="lt")
        spinach = Product(id=uuid.uuid4(), household_id=casa.id, name="Fresh Spinach", category="Vegetables", default_unit="kg")
        bread = Product(id=uuid.uuid4(), household_id=casa.id, name="Whole Wheat Bread", category="Bakery", default_unit="units")
        rice = Product(id=uuid.uuid4(), household_id=casa.id, name="White Rice", category="Grains", default_unit="kg")
        db.add_all([milk, eggs, chicken, cheese, tomato, spinach, bread, rice])
        db.flush()

        today = date.today()
        items_data = [
            (milk, zone_fridge, 2, "lt", today + timedelta(days=5)),
            (eggs, zone_fridge, 12, "units", today + timedelta(days=10)),
            (chicken, zone_freezer, 1.5, "kg", today + timedelta(days=60)),
            (cheese, zone_fridge, 0.5, "kg", today + timedelta(days=20)),
            (tomato, zone_pantry, 3, "lt", today + timedelta(days=180)),
            (spinach, zone_fridge, 0.3, "kg", today + timedelta(days=2)),
            (bread, zone_pantry, 1, "units", today + timedelta(days=7)),
            (rice, zone_pantry, 2, "kg", None),
        ]
        items = []
        for prod, zone, qty, unit, exp in items_data:
            item = InventoryItem(
                id=uuid.uuid4(), household_id=casa.id, product_id=prod.id,
                zone_id=zone.id, quantity=qty, unit=unit, expiry_date=exp, status="active"
            )
            items.append(item)
        db.add_all(items)
        db.flush()

        alerts_data = [
            Alert(id=uuid.uuid4(), household_id=casa.id, inventory_item_id=items[5].id,
                  type="expiring_soon", severity="warning",
                  title="Spinach expires soon", message="Fresh Spinach expires in 2 days",
                  due_at=datetime.combine(today + timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc)),
            Alert(id=uuid.uuid4(), household_id=casa.id, inventory_item_id=items[0].id,
                  type="expiring_soon", severity="info",
                  title="Milk expiring soon", message="Whole Milk expires in 5 days",
                  due_at=datetime.combine(today + timedelta(days=5), datetime.min.time(), tzinfo=timezone.utc)),
        ]
        db.add_all(alerts_data)

        shopping_items = [
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Olive Oil", quantity=1, unit="lt"),
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Garlic", quantity=3, unit="units"),
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Onions", quantity=2, unit="kg", checked=True),
        ]
        db.add_all(shopping_items)

        activity = [
            ActivityLog(id=uuid.uuid4(), household_id=casa.id, actor_user_id=alice.id,
                        entity_type="inventory_item", entity_id=items[0].id,
                        action="created", extra_data={"product_name": "Whole Milk"}),
            ActivityLog(id=uuid.uuid4(), household_id=casa.id, actor_user_id=alice.id,
                        entity_type="shopping_item", entity_id=shopping_items[0].id,
                        action="created", extra_data={"product_name": "Olive Oil"}),
        ]
        db.add_all(activity)

        db.commit()
        print(f"Seed complete: {db.query(User).count()} users, {db.query(Household).count()} households, "
              f"{db.query(Product).count()} products, {db.query(InventoryItem).count()} inventory items")
    finally:
        db.close()

if __name__ == "__main__":
    drop_all()
    create_all()
    seed()
