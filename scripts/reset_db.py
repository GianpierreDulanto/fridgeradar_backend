"""
Reset + seed de la base de datos para desarrollo.

USO:
    python scripts/reset_db.py

ADVERTENCIA: este script DESTRUYE todas las tablas y las recrea. No usar
en produccion. Pensado para que las 3 parejas (Inventario, Caducidad,
Recetas) tengan datos consistentes para trabajar en paralelo.

Ademas cubre el resto de pantallas testeables del frontend:
  - 2 households ("Casa de Alice" y "Casa de Luis") para probar el switcher.
  - 3 miembros con roles owner/admin/member en Casa de Alice + invitacion
    pendiente para bob en Casa de Luis (cubre /notifications y banner).
  - Refrigerador + Freezer + Pantry por household (cubre los 4 zone_types).
  - Items con status active/consumed/discarded (cubre /inventory/[id]).
  - Items con opened_date (cubre flujos que lo consultan).
  - Productos con image_url obtenido de Open Food Facts en paralelo
    (cubre la card de inventario y el add-item-dialog).
  - Shopping list con source (manual / from-recipe).
  - Activity log con las 6 acciones que pinta la UI: created, updated,
    consumed, discarded, restocked, deleted (+ shopping_item y refrigerator).
  - Alertas generadas por AlertService.scan_and_generate: incluye tanto
    las de caducidad (expired, expiring_today, expiring_soon) como las de
    low_stock (que el seed anterior no producia).

Credenciales de los usuarios seed (password unica para todo el entorno dev):
    alice@example.com   / pass1234
    bob@example.com     / pass1234
    lbizarro@gmail.com  / pass1234
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import httpx
from sqlalchemy import text
from datetime import date, datetime, timezone, timedelta
import uuid

from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.models import (
    User, Household, HouseholdMember, Zone, Product, InventoryItem,
    Alert, ShoppingListItem, ActivityLog,
)
from app.models.refrigerator import Refrigerator


LOW_STOCK_THRESHOLD = 1.0

DEV_PASSWORD_HASH = "$2b$12$PpeIPwx6wUWQ7GuuACenQuDcyUHVrm9E.eTaQneJNAcVmz4u6d.qa"

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


# Items activos en Casa de Alice. (product_name, zone_key, qty, unit, days_offset)
# days_offset < 0 = ya expirado; None = sin fecha de caducidad
INVENTORY_PLAN = [
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
    # Recipes-relevant extras
    ("Roma Tomatoes",       "fridge",  0.4,  "kg",     4),
    ("Beef Steak",          "fridge",  0.3,  "kg",     3),
    ("Bananas",             "pantry",  3.0,  "units",  6),
    ("Red Apples",          "pantry",  4.0,  "units", 14),
    ("Tomato Sauce",        "pantry",  0.5,  "lt",   120),
    ("Hummus",              "fridge",  0.3,  "kg",    10),
    ("Sourdough Loaf",      "pantry",  1.0,  "units",  4),
]


# Items extra solo en el freezer (para que la zona freezer tenga contenido)
# (product_name, qty, unit, days_until_expiry)
FREEZER_PLAN = [
    ("Frozen Peas",   1.0,  "kg",    90),
    ("Frozen Pizza",  2.0,  "units", 60),
    ("Salmon Fillet", 0.5,  "kg",    30),
    ("Beef Steak",    0.3,  "kg",    45),
]


# Items con status NO activo, para que /inventory/[id] muestre el mensaje
# "item was {status}". (product_name, status, days_ago_expired, qty, unit)
INACTIVE_PLAN = [
    ("Whole Milk",     "consumed",  -3, 0, "lt"),
    ("Cheddar Cheese", "discarded", -1, 0, "kg"),
    ("Fresh Spinach",  "consumed",  -2, 0, "kg"),
]


# Items en Casa de Luis. (product_name, zone_key, qty, unit, days_until_expiry)
LUIS_INVENTORY_PLAN = [
    ("Whole Milk",      "fridge",  1.0,  "lt",    5),
    ("Free-Range Eggs", "fridge",  6.0,  "units", 14),
    ("Sourdough Loaf",  "fridge",  1.0,  "units", 3),
    ("Frozen Pizza",    "freezer", 1.0,  "units", 90),
]


# Productos que tendran opened_date seteado (productos tipicamente abiertos
# antes de su consumo: leche, queso, hummus, etc.)
OPENED_PRODUCTS = {"Whole Milk", "Cheddar Cheese", "Greek Yogurt", "Hummus"}


# Productos con threshold custom para que disparen/not-disparen low_stock segun
# convenga. Si el producto no aparece, usa DEFAULT=1.0
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
        conn.execute(text("DROP TABLE IF EXISTS token_blacklist CASCADE"))
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


async def _fetch_one_image(client: httpx.AsyncClient, name: str) -> tuple[str, str | None]:
    """Busca image_url del primer match de `name` en Open Food Facts.

    Lento a proposito: OFF nos rate-limita agresivamente desde IPs compartidas
    (HTTP 503/timeout), asi que serializamos con ~3s entre requests.
    """
    try:
        resp = await client.get(
            "https://world.openfoodfacts.org/cgi/search.pl",
            params={
                "search_terms": name,
                "search_simple": 1,
                "action": "process",
                "fields": "image_url",
                "json": 1,
                "page_size": 1,
            },
            headers={"User-Agent": "FridgeRadar-Seed/1.0 (contact: dev@local)"},
            timeout=15.0,
        )
        if resp.status_code != 200:
            return name, None
        data = resp.json()
        products = data.get("products") or []
        if products and products[0].get("image_url"):
            return name, products[0]["image_url"]
    except Exception:
        pass
    return name, None


def fetch_product_images(names: list[str], delay_s: float = 3.0) -> dict[str, str | None]:
    """Fetch image_url secuencial. ~3s por producto para no ser rate-limited.

    Devuelve {} silenciosamente si OFF no responde. Para un fetch opt-in
    mas agresivo, usa scripts/fetch_product_images.py.
    """
    async def _run():
        out: dict[str, str | None] = {}
        async with httpx.AsyncClient() as client:
            for n in names:
                _n, url = await _fetch_one_image(client, n)
                out[_n] = url
                await asyncio.sleep(delay_s)
        return out
    try:
        return asyncio.run(_run())
    except Exception:
        return {}


def maybe_fetch_images(names: list[str]) -> dict[str, str | None]:
    """Devuelve {} salvo que el usuario fuerce el fetch con FETCH_IMAGES=1."""
    if os.environ.get("FETCH_IMAGES", "").lower() not in ("1", "true", "yes"):
        return {}
    print(f"[reset_db] FETCH_IMAGES=1 -> descargando imagenes de OFF (lento, ~{len(names)*3}s)")
    return fetch_product_images(names)


def seed():
    db = SessionLocal()
    try:
        # ---------- Users ----------
        alice = User(id=uuid.uuid4(), email="alice@example.com", password_hash=DEV_PASSWORD_HASH, full_name="Alice Johnson")
        bob = User(id=uuid.uuid4(), email="bob@example.com", password_hash=DEV_PASSWORD_HASH, full_name="Bob Smith")
        lbizarro = User(id=uuid.uuid4(), email="lbizarro@gmail.com", password_hash=DEV_PASSWORD_HASH, full_name="Luis Bizarro")
        db.add_all([alice, bob, lbizarro])
        db.flush()

        # ---------- Household 1: Casa de Alice ----------
        casa = Household(
            id=uuid.uuid4(),
            name="Casa de Alice",
            timezone="America/Mexico_City",
            owner_user_id=alice.id,
        )
        db.add(casa)
        db.flush()

        # alice (owner), bob (admin), lbizarro (member)
        db.add_all([
            HouseholdMember(id=uuid.uuid4(), household_id=casa.id, user_id=alice.id, role="owner", status="active"),
            HouseholdMember(id=uuid.uuid4(), household_id=casa.id, user_id=bob.id, role="admin", status="active", invited_by=alice.id),
            HouseholdMember(id=uuid.uuid4(), household_id=casa.id, user_id=lbizarro.id, role="member", status="active", invited_by=alice.id),
        ])

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

        # ---------- Household 2: Casa de Luis ----------
        casa_luis = Household(
            id=uuid.uuid4(),
            name="Casa de Luis",
            timezone="America/Mexico_City",
            owner_user_id=lbizarro.id,
        )
        db.add(casa_luis)
        db.flush()

        # lbizarro (owner), alice (admin), bob (PENDING -> cubre /notifications)
        db.add_all([
            HouseholdMember(id=uuid.uuid4(), household_id=casa_luis.id, user_id=lbizarro.id, role="owner", status="active"),
            HouseholdMember(id=uuid.uuid4(), household_id=casa_luis.id, user_id=alice.id, role="admin", status="active", invited_by=lbizarro.id),
            HouseholdMember(
                id=uuid.uuid4(), household_id=casa_luis.id, user_id=bob.id, role="member",
                status="pending", invited_by=lbizarro.id,
            ),
        ])

        luis_fridge = Refrigerator(id=uuid.uuid4(), household_id=casa_luis.id, name="Refrigerador", type="refrigerator", sort_order=0)
        luis_freezer = Refrigerator(id=uuid.uuid4(), household_id=casa_luis.id, name="Congelador", type="freezer", sort_order=1)
        db.add_all([luis_fridge, luis_freezer])
        db.flush()

        luis_zone_fridge = Zone(id=uuid.uuid4(), household_id=casa_luis.id, refrigerator_id=luis_fridge.id, name="Estantes", type="refrigerator", sort_order=0)
        luis_zone_freezer = Zone(id=uuid.uuid4(), household_id=casa_luis.id, refrigerator_id=luis_freezer.id, name="Cajones", type="freezer", sort_order=0)
        db.add_all([luis_zone_fridge, luis_zone_freezer])
        db.flush()

        # ---------- Products: 49 catalog items en AMBOS households ----------
        all_product_names = [name for name, _, _ in PRODUCTS]
        # Por defecto, image_url=None. Para forzar fetch: FETCH_IMAGES=1 python scripts/reset_db.py
        # (tarda ~3s por producto, susceptible a rate-limit de OFF)
        image_urls = maybe_fetch_images(all_product_names)
        with_image = sum(1 for v in image_urls.values() if v)
        if with_image:
            print(f"[reset_db] Got images for {with_image}/{len(all_product_names)} products")
        else:
            print(f"[reset_db] image_url=None para todos los productos (usa FETCH_IMAGES=1 o scripts/fetch_product_images.py)")

        def _create_products_for(household_id):
            by_name = {}
            for name, category, unit in PRODUCTS:
                threshold = LOW_STOCK_OVERRIDES.get(name)
                p = Product(
                    id=uuid.uuid4(),
                    household_id=household_id,
                    name=name, category=category, default_unit=unit,
                    image_url=image_urls.get(name),
                    low_stock_threshold=threshold,
                )
                by_name[name] = p
                db.add(p)
            return by_name

        alice_product_by_name = _create_products_for(casa.id)
        luis_product_by_name = _create_products_for(casa_luis.id)
        db.flush()

        # ---------- Active inventory items in Casa de Alice ----------
        today = date.today()
        zone_by_key = {"fridge": zone_fridge, "freezer": zone_freezer, "pantry": zone_pantry}

        items_by_name: dict[str, InventoryItem] = {}
        for prod_name, zone_key, qty, unit, days in INVENTORY_PLAN:
            product = alice_product_by_name[prod_name]
            zone = zone_by_key[zone_key]
            exp = None if days is None else (today + timedelta(days=days))
            purchase = (exp - timedelta(days=5)) if exp else (today - timedelta(days=10))
            opened = None
            if prod_name in OPENED_PRODUCTS:
                opened = (exp - timedelta(days=1)) if exp else (today - timedelta(days=2))
            item = InventoryItem(
                id=uuid.uuid4(), household_id=casa.id,
                product_id=product.id, zone_id=zone.id,
                quantity=qty, unit=unit,
                purchase_date=purchase, expiry_date=exp,
                opened_date=opened,
                status="active",
            )
            items_by_name[prod_name] = item
            db.add(item)

        # Freezer-only items
        for prod_name, qty, unit, days in FREEZER_PLAN:
            product = alice_product_by_name[prod_name]
            exp = (today + timedelta(days=days)) if days is not None else None
            item = InventoryItem(
                id=uuid.uuid4(), household_id=casa.id,
                product_id=product.id, zone_id=zone_freezer.id,
                quantity=qty, unit=unit,
                purchase_date=today - timedelta(days=2),
                expiry_date=exp,
                status="active",
            )
            items_by_name[f"freezer_{prod_name}"] = item
            db.add(item)

        # Inactive items (consumed / discarded)
        for prod_name, status, days_ago, qty, unit in INACTIVE_PLAN:
            product = alice_product_by_name[prod_name]
            exp = (today + timedelta(days=days_ago)) if days_ago is not None else None
            item = InventoryItem(
                id=uuid.uuid4(), household_id=casa.id,
                product_id=product.id, zone_id=zone_fridge.id,
                quantity=qty, unit=unit,
                purchase_date=today - timedelta(days=7),
                expiry_date=exp,
                status=status,
            )
            db.add(item)
        db.flush()

        # ---------- Items in Casa de Luis ----------
        luis_zone_by_key = {"fridge": luis_zone_fridge, "freezer": luis_zone_freezer}
        for prod_name, zone_key, qty, unit, days in LUIS_INVENTORY_PLAN:
            product = luis_product_by_name[prod_name]
            zone = luis_zone_by_key[zone_key]
            exp = today + timedelta(days=days)
            item = InventoryItem(
                id=uuid.uuid4(), household_id=casa_luis.id,
                product_id=product.id, zone_id=zone.id,
                quantity=qty, unit=unit,
                purchase_date=today - timedelta(days=3),
                expiry_date=exp,
                status="active",
            )
            db.add(item)
        db.flush()

        # ---------- Shopping list (con source) ----------
        shopping_items = [
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Olive Oil", quantity=1, unit="lt", source="manual"),
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Garlic", quantity=3, unit="units", source="from-recipe"),
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Onions", quantity=2, unit="kg", checked=True, source="manual"),
        ]
        db.add_all(shopping_items)
        db.flush()

        # ---------- Activity log: cubre las 6 acciones que pinta la UI ----------
        now = datetime.now(timezone.utc)
        activity_seed = [
            # (hours_ago, hh, actor, entity_id, entity_type, action, extra)
            (1,  casa.id, alice.id, items_by_name["Whole Milk"].id,       "inventory_item", "created",   {"product_name": "Whole Milk"}),
            (2,  casa.id, bob.id,   items_by_name["Cheddar Cheese"].id,   "inventory_item", "updated",   {"product_name": "Cheddar Cheese"}),
            (4,  casa.id, alice.id, items_by_name["Fresh Spinach"].id,    "inventory_item", "consumed",  {"product_name": "Fresh Spinach"}),
            (6,  casa.id, alice.id, items_by_name["Greek Yogurt"].id,     "inventory_item", "discarded", {"product_name": "Greek Yogurt"}),
            (12, casa.id, lbizarro.id, items_by_name["Olive Oil"].id,     "inventory_item", "restocked", {"product_name": "Olive Oil", "delta": 1}),
            (18, casa.id, alice.id, items_by_name["Salt"].id,             "inventory_item", "deleted",   {"product_name": "Salt"}),
            (1,  casa.id, alice.id, shopping_items[0].id,                 "shopping_item",  "created",   {"product_name": "Olive Oil"}),
            (3,  casa.id, alice.id, freezer.id,                           "refrigerator",   "created",   {"name": "Freezer"}),
        ]
        for hours_ago, hh, actor_id, entity_id, etype, action, extra in activity_seed:
            db.add(ActivityLog(
                id=uuid.uuid4(), household_id=hh, actor_user_id=actor_id,
                entity_type=etype, entity_id=entity_id,
                action=action, extra_data=extra,
                created_at=now - timedelta(hours=hours_ago),
            ))

        db.commit()

        # ---------- Alerts via AlertService (expiry + low_stock) ----------
        # bulk_create hace commit internamente, pero abrimos sesion propia para
        # que el scan recorra ambos households sin contaminar esta sesion.
        from app.services.alert_service import AlertService
        db_alerts = SessionLocal()
        try:
            result = AlertService(db_alerts).scan_and_generate(
                household_id=None, current_user=None,
            )
            print(f"[reset_db] AlertService.scan_and_generate -> created={result.get('created')}")
        finally:
            db_alerts.close()

        # ---------- Resumen ----------
        db_summary = SessionLocal()
        try:
            print()
            print("[reset_db] Seed complete:")
            print(f"  Users:           {db_summary.query(User).count()}")
            print(f"  Households:      {db_summary.query(Household).count()}")
            print(f"  Refrigerators:   {db_summary.query(Refrigerator).count()}")
            print(f"  Zones:           {db_summary.query(Zone).count()}")
            print(f"  Products:        {db_summary.query(Product).count()} (across {len(CATEGORIES)} categories, {with_image} with image_url)")
            active = db_summary.query(InventoryItem).filter(InventoryItem.status == "active").count()
            consumed = db_summary.query(InventoryItem).filter(InventoryItem.status == "consumed").count()
            discarded = db_summary.query(InventoryItem).filter(InventoryItem.status == "discarded").count()
            print(f"  Inventory items: {active} active, {consumed} consumed, {discarded} discarded")
            print(f"  Alerts:          {db_summary.query(Alert).count()}")
            print(f"  Shopping items:  {db_summary.query(ShoppingListItem).count()}")
            pending_inv = db_summary.query(HouseholdMember).filter(HouseholdMember.status == "pending").count()
            print(f"  Pending invites: {pending_inv}")
            print(f"  Activity log:    {db_summary.query(ActivityLog).count()}")
            print()
            print("  Dev credentials (password for all): pass1234")
            print("    alice@example.com   / pass1234   (owner of Casa de Alice, admin of Casa de Luis)")
            print("    bob@example.com     / pass1234   (admin in Casa de Alice, pending in Casa de Luis)")
            print("    lbizarro@gmail.com  / pass1234   (member in Casa de Alice, owner of Casa de Luis)")
        finally:
            db_summary.close()
    finally:
        db.close()


if __name__ == "__main__":
    drop_all()
    create_all()
    seed()
