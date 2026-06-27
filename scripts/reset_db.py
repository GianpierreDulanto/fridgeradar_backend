"""
Reset + seed de la base de datos para desarrollo.

USO:
    python scripts/reset_db.py

ADVERTENCIA: este script DESTRUYE todas las tablas y las recrea. No usar
en producción. Pensado para que las 3 parejas (Inventario, Caducidad,
Recetas) tengan datos consistentes para trabajar en paralelo.

El seed cubre explícitamente:
  - Pareja A (Inventario): 2 refrigerators, 2 zones con refrigerator_id,
    49 productos (2 por cada una de las 24 categorías del frontend, 3 en
    Dairy para soportar el seed de caducidad), catálogo poblado.
  - Pareja B (Caducidad): items distribuidos en todos los buckets de
    expiry_status (expired, today, urgent, attention, safe, sin fecha),
    2 items con quantity < 1 (low_stock) y alertas pre-generadas que
    coinciden con lo que produciría el scan.
  - Pareja C (Recetas): 49 productos repartidos en 24 categorías para
    que el matching tenga variedad (≥2 por categoría es el mínimo útil
    para distinguir "tienes" vs "necesitas").

Credenciales de los usuarios seed:
    alice@example.com / password123
    bob@example.com   / password123
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.core.database import Base, engine
from app.models import (
    User, Household, HouseholdMember, Zone, Product, InventoryItem,
    Alert, ShoppingListItem, ActivityLog,
)
from app.models.refrigerator import Refrigerator
from sqlalchemy import text
from passlib.hash import bcrypt
from datetime import date, datetime, timezone, timedelta
import uuid


LOW_STOCK_THRESHOLD = 1.0


CATEGORIES = [
    "Dairy", "Meat", "Poultry", "Fish", "Vegetables", "Fruits",
    "Grains", "Pasta", "Bread", "Condiments", "Oils", "Sauces",
    "Spices", "Herbs", "Beverages", "Snacks", "Frozen", "Canned",
    "Bakery", "Dairy Alternatives", "Prepared Foods", "Baby", "Pet", "Other",
]


PRODUCTS = [
    ("Whole Milk",          "Dairy",              "lt"),
    ("Cheddar Cheese",      "Dairy",              "kg"),
    ("Greek Yogurt",        "Dairy",              "kg"),
    ("Beef Steak",          "Meat",               "kg"),
    ("Ground Beef",         "Meat",               "kg"),
    ("Chicken Breast",      "Poultry",            "kg"),
    ("Free-Range Eggs",     "Poultry",            "units"),
    ("Salmon Fillet",       "Fish",               "kg"),
    ("Canned Tuna",         "Fish",               "units"),
    ("Fresh Spinach",       "Vegetables",         "kg"),
    ("Roma Tomatoes",       "Vegetables",         "kg"),
    ("Bananas",             "Fruits",             "units"),
    ("Red Apples",          "Fruits",             "units"),
    ("White Rice",          "Grains",             "kg"),
    ("Quinoa",              "Grains",             "kg"),
    ("Spaghetti",           "Pasta",              "kg"),
    ("Penne",               "Pasta",              "kg"),
    ("Whole Wheat Bread",   "Bread",              "units"),
    ("Sourdough Loaf",      "Bread",              "units"),
    ("Ketchup",             "Condiments",         "lt"),
    ("Mayonnaise",          "Condiments",         "kg"),
    ("Olive Oil",           "Oils",               "lt"),
    ("Vegetable Oil",       "Oils",               "lt"),
    ("Tomato Sauce",        "Sauces",             "lt"),
    ("Soy Sauce",           "Sauces",             "lt"),
    ("Black Pepper",        "Spices",             "kg"),
    ("Paprika",             "Spices",             "kg"),
    ("Fresh Basil",         "Herbs",              "kg"),
    ("Cilantro",            "Herbs",              "kg"),
    ("Orange Juice",        "Beverages",          "lt"),
    ("Sparkling Water",     "Beverages",          "lt"),
    ("Potato Chips",        "Snacks",             "kg"),
    ("Dark Chocolate",      "Snacks",             "kg"),
    ("Frozen Peas",         "Frozen",             "kg"),
    ("Frozen Pizza",        "Frozen",             "units"),
    ("Black Beans",         "Canned",             "kg"),
    ("Canned Corn",         "Canned",             "kg"),
    ("Croissant",           "Bakery",             "units"),
    ("Bagels",              "Bakery",             "units"),
    ("Almond Milk",         "Dairy Alternatives", "lt"),
    ("Tofu Block",          "Dairy Alternatives", "kg"),
    ("Hummus",              "Prepared Foods",     "kg"),
    ("Ready Soup",          "Prepared Foods",     "lt"),
    ("Baby Formula",        "Baby",               "kg"),
    ("Baby Cereal",         "Baby",               "kg"),
    ("Dog Food",            "Pet",                "kg"),
    ("Cat Treats",          "Pet",                "kg"),
    ("Salt",                "Other",              "kg"),
    ("Sugar",               "Other",              "kg"),
]


INVENTORY_PLAN = [
    # (product_name, zone_key, quantity, unit, days_offset)
    # days_offset < 0 = ya expirado; None = sin fecha de caducidad
    # quantity < low_stock_threshold = low_stock (algunos productos tienen
    # threshold explícito vía LOW_STOCK_OVERRIDES; el resto usa DEFAULT=1.0)
    ("Whole Milk",          "fridge",  2.0,  "lt",    -2),
    ("Greek Yogurt",        "fridge",  0.5,  "kg",    -5),
    ("Chicken Breast",      "fridge",  1.0,  "kg",     0),
    ("Fresh Spinach",       "fridge",  0.5,  "kg",     1),
    ("Whole Wheat Bread",   "pantry",  1.0,  "units",  2),
    ("Cheddar Cheese",      "fridge",  0.5,  "kg",     5),
    ("Free-Range Eggs",     "fridge",  12.0, "units",  7),
    ("White Rice",          "pantry",  2.0,  "kg",    30),
    ("Spaghetti",           "pantry",  1.0,  "kg",    60),
    ("Olive Oil",           "pantry",  1.0,  "lt",   180),
    ("Salt",                "pantry",  1.0,  "kg",   None),
    ("Black Pepper",        "pantry",  0.05, "kg",    90),
    ("Paprika",             "pantry",  0.1,  "kg",    90),
    # Recipes-relevant extras (so fallback recipes can find their categories)
    ("Roma Tomatoes",       "fridge",  0.4,  "kg",     4),
    ("Beef Steak",          "fridge",  0.3,  "kg",     3),
    ("Bananas",             "pantry",  3.0,  "units",  6),
    ("Red Apples",          "pantry",  4.0,  "units", 14),
    ("Tomato Sauce",        "pantry",  0.5,  "lt",   120),
    ("Hummus",              "fridge",  0.3,  "kg",    10),
    ("Sourdough Loaf",      "pantry",  1.0,  "units",  4),
]


# Per-product low_stock_threshold overrides. Si el producto no aparece, usa
# el DEFAULT (1.0). Útil para especias / condimentos que se consumen en
# pequeñas cantidades y no deberían disparar low_stock con quantity=0.5.
LOW_STOCK_OVERRIDES = {
    "Black Pepper": 0.02,
    "Paprika": 0.05,
    "Salt": 0.5,
    "Olive Oil": 0.5,
    "Beef Steak": 0.2,
    "Roma Tomatoes": 0.5,
    "Hummus": 0.25,
}


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
    print("[reset_db] All tables dropped")


def create_all():
    Base.metadata.create_all(bind=engine)
    print("[reset_db] All tables created")


def _alert_for(item, exp_date, today):
    """Devuelve (type, severity, title, message, due_at) o None si no aplica."""
    if exp_date is None:
        return None
    diff = (exp_date - today).days
    if diff < 0:
        return (
            "expired",
            "critical",
            f"{item.product.name} expired",
            f"{item.product.name} expired {-diff} day(s) ago",
            datetime.combine(exp_date, datetime.min.time(), tzinfo=timezone.utc),
        )
    if diff == 0:
        return (
            "expiring_today",
            "critical",
            f"{item.product.name} expires today",
            f"Use {item.product.name} today",
            datetime.combine(exp_date, datetime.min.time(), tzinfo=timezone.utc),
        )
    if diff <= 3:
        return (
            "expiring_soon",
            "warning",
            f"{item.product.name} expires soon",
            f"{item.product.name} expires in {diff} day(s)",
            datetime.combine(exp_date, datetime.min.time(), tzinfo=timezone.utc),
        )
    if diff <= 7:
        return (
            "expiring_soon",
            "info",
            f"{item.product.name} expiring this week",
            f"{item.product.name} expires in {diff} day(s)",
            datetime.combine(exp_date, datetime.min.time(), tzinfo=timezone.utc),
        )
    return None


def _priority_for_alert(alert_type: str, severity: str, exp_date, today) -> float:
    """Compute the priority_score that matches alert_service._expiry_alert_spec."""
    if alert_type == "expired":
        return 100.0
    if alert_type == "expiring_today":
        return 90.0
    if alert_type == "expiring_soon" and severity == "warning":
        diff = (exp_date - today).days
        return float(70 + (3 - diff))
    if alert_type == "expiring_soon" and severity == "info":
        diff = (exp_date - today).days
        return float(40 + (7 - diff) * 5)
    return 0.0


def seed():
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        pw = bcrypt.hash("password123")

        alice = User(id=uuid.uuid4(), email="alice@example.com", password_hash=pw, full_name="Alice Johnson")
        bob = User(id=uuid.uuid4(), email="bob@example.com", password_hash=pw, full_name="Bob Smith")
        db.add_all([alice, bob])
        db.flush()

        casa = Household(
            id=uuid.uuid4(),
            name="Casa de Alice",
            timezone="America/Mexico_City",
            owner_user_id=alice.id,
        )
        db.add(casa)
        db.flush()

        db.add(HouseholdMember(
            id=uuid.uuid4(),
            household_id=casa.id,
            user_id=alice.id,
            role="owner",
            status="active",
        ))
        db.flush()

        fridge = Refrigerator(
            id=uuid.uuid4(), household_id=casa.id,
            name="Main Refrigerator", type="refrigerator", sort_order=0,
        )
        pantry = Refrigerator(
            id=uuid.uuid4(), household_id=casa.id,
            name="Pantry", type="pantry", sort_order=1,
        )
        db.add_all([fridge, pantry])
        db.flush()

        zone_fridge = Zone(
            id=uuid.uuid4(), household_id=casa.id, refrigerator_id=fridge.id,
            name="Fridge Shelves", type="refrigerator", sort_order=0,
        )
        zone_pantry = Zone(
            id=uuid.uuid4(), household_id=casa.id, refrigerator_id=pantry.id,
            name="Pantry Shelves", type="pantry", sort_order=0,
        )
        db.add_all([zone_fridge, zone_pantry])
        db.flush()

        product_by_name = {}
        for name, category, unit in PRODUCTS:
            threshold = LOW_STOCK_OVERRIDES.get(name)
            p = Product(
                id=uuid.uuid4(),
                household_id=casa.id,
                name=name,
                category=category,
                default_unit=unit,
                image_url=None,
                low_stock_threshold=threshold,
            )
            product_by_name[name] = p
            db.add(p)
        db.flush()

        today = date.today()
        zone_by_key = {"fridge": zone_fridge, "pantry": zone_pantry}

        items_by_name = {}
        for prod_name, zone_key, qty, unit, days in INVENTORY_PLAN:
            product = product_by_name[prod_name]
            zone = zone_by_key[zone_key]
            exp = None if days is None else (today + timedelta(days=days))
            purchase = (exp - timedelta(days=5)) if exp else (today - timedelta(days=10))
            item = InventoryItem(
                id=uuid.uuid4(),
                household_id=casa.id,
                product_id=product.id,
                zone_id=zone.id,
                quantity=qty,
                unit=unit,
                purchase_date=purchase,
                expiry_date=exp,
                status="active",
            )
            items_by_name[prod_name] = item
            db.add(item)
        db.flush()

        alerts = []
        for prod_name, item in items_by_name.items():
            spec = _alert_for(item, item.expiry_date, today)
            if spec is None:
                continue
            type_, severity, title, message, due_at = spec
            priority = _priority_for_alert(type_, severity, item.expiry_date, today)
            alerts.append(Alert(
                id=uuid.uuid4(),
                household_id=casa.id,
                inventory_item_id=item.id,
                type=type_,
                severity=severity,
                title=title,
                message=message,
                due_at=due_at,
                priority_score=priority,
            ))
        db.add_all(alerts)

        shopping_items = [
            ShoppingListItem(
                id=uuid.uuid4(), household_id=casa.id,
                product_name="Olive Oil", quantity=1, unit="lt",
            ),
            ShoppingListItem(
                id=uuid.uuid4(), household_id=casa.id,
                product_name="Garlic", quantity=3, unit="units",
            ),
            ShoppingListItem(
                id=uuid.uuid4(), household_id=casa.id,
                product_name="Onions", quantity=2, unit="kg", checked=True,
            ),
        ]
        db.add_all(shopping_items)
        db.flush()

        activity = [
            ActivityLog(
                id=uuid.uuid4(), household_id=casa.id, actor_user_id=alice.id,
                entity_type="inventory_item", entity_id=items_by_name["Whole Milk"].id,
                action="created", extra_data={"product_name": "Whole Milk"},
            ),
            ActivityLog(
                id=uuid.uuid4(), household_id=casa.id, actor_user_id=alice.id,
                entity_type="inventory_item", entity_id=items_by_name["Fresh Spinach"].id,
                action="created", extra_data={"product_name": "Fresh Spinach"},
            ),
            ActivityLog(
                id=uuid.uuid4(), household_id=casa.id, actor_user_id=alice.id,
                entity_type="shopping_item", entity_id=shopping_items[0].id,
                action="created", extra_data={"product_name": "Olive Oil"},
            ),
        ]
        db.add_all(activity)

        db.commit()

        active_items = db.query(InventoryItem).filter(InventoryItem.status == "active").all()
        low_stock = [i for i in active_items if i.quantity < LOW_STOCK_THRESHOLD]
        expired = [i for i in active_items if i.expiry_date and i.expiry_date < today]
        no_expiry = [i for i in active_items if i.expiry_date is None]

        print()
        print("[reset_db] Seed complete:")
        print(f"  Users:           {db.query(User).count()}")
        print(f"  Households:      {db.query(Household).count()}")
        print(f"  Refrigerators:   {db.query(Refrigerator).count()}")
        print(f"  Zones:           {db.query(Zone).count()}")
        print(f"  Products:        {db.query(Product).count()} (across {len(CATEGORIES)} categories)")
        print(f"  Inventory items: {len(active_items)} active ({len(expired)} expired, {len(no_expiry)} no expiry, {len(low_stock)} low stock)")
        print(f"  Alerts:          {len(alerts)}")
        print(f"  Shopping items:  {db.query(ShoppingListItem).count()}")
        print()
        print("  Dev credentials: alice@example.com / password123")
        print("                   bob@example.com   / password123")
    finally:
        db.close()


if __name__ == "__main__":
    drop_all()
    create_all()
    seed()
