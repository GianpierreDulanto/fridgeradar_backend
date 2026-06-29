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

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

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
    "Lácteos", "Carne", "Aves", "Pescado", "Verduras", "Frutas",
    "Granos", "Pasta", "Pan", "Condimentos", "Aceites", "Salsas",
    "Especias", "Hierbas", "Bebidas", "Botanas", "Congelados", "Enlatados",
    "Panadería", "Alternativas Lácteas", "Comidas Preparadas", "Bebé", "Mascotas", "Otros",
]


PRODUCTS = [
    ("Leche Entera",        "Lácteos",            "lt"),
    ("Queso Cheddar",       "Lácteos",            "kg"),
    ("Yogur Griego",         "Lácteos",            "kg"),
    ("Bistec de Res",        "Carne",              "kg"),
    ("Carne Molida",         "Carne",              "kg"),
    ("Pechuga de Pollo",     "Aves",               "kg"),
    ("Huevos de Campo",      "Aves",               "units"),
    ("Filete de Salmón",     "Pescado",            "kg"),
    ("Atún en Lata",         "Pescado",            "units"),
    ("Espinaca Fresca",      "Verduras",           "kg"),
    ("Tomates Roma",         "Verduras",           "kg"),
    ("Plátanos",             "Frutas",             "units"),
    ("Manzanas Rojas",       "Frutas",             "units"),
    ("Arroz Blanco",         "Granos",             "kg"),
    ("Quinoa",               "Granos",             "kg"),
    ("Espagueti",            "Pasta",              "kg"),
    ("Penne",                "Pasta",              "kg"),
    ("Pan Integral",         "Pan",                "units"),
    ("Pan de Masa Madre",    "Pan",                "units"),
    ("Ketchup",              "Condimentos",        "lt"),
    ("Mayonesa",             "Condimentos",        "kg"),
    ("Aceite de Oliva",      "Aceites",            "lt"),
    ("Aceite Vegetal",       "Aceites",            "lt"),
    ("Salsa de Tomate",      "Salsas",             "lt"),
    ("Salsa de Soja",        "Salsas",             "lt"),
    ("Pimienta Negra",       "Especias",           "kg"),
    ("Pimentón",             "Especias",           "kg"),
    ("Albahaca Fresca",      "Hierbas",            "kg"),
    ("Cilantro",             "Hierbas",            "kg"),
    ("Jugo de Naranja",      "Bebidas",            "lt"),
    ("Agua con Gas",         "Bebidas",            "lt"),
    ("Papas Fritas",         "Botanas",            "kg"),
    ("Chocolate Negro",      "Botanas",            "kg"),
    ("Arvejas Congeladas",   "Congelados",         "kg"),
    ("Pizza Congelada",      "Congelados",         "units"),
    ("Frijoles Negros",      "Enlatados",          "kg"),
    ("Maíz en Lata",         "Enlatados",          "kg"),
    ("Croissant",            "Panadería",          "units"),
    ("Bagels",               "Panadería",          "units"),
    ("Leche de Almendras",   "Alternativas Lácteas","lt"),
    ("Bloque de Tofu",       "Alternativas Lácteas","kg"),
    ("Hummus",               "Comidas Preparadas", "kg"),
    ("Sopa Lista",           "Comidas Preparadas", "lt"),
    ("Fórmula Infantil",     "Bebé",               "kg"),
    ("Cereal para Bebé",     "Bebé",               "kg"),
    ("Comida para Perro",    "Mascotas",           "kg"),
    ("Snacks para Gato",     "Mascotas",           "kg"),
    ("Sal",                  "Otros",              "kg"),
    ("Azúcar",               "Otros",              "kg"),
]


# Items activos en Casa de Alice. Cubre las 24 categorías y los 6 buckets
# de expiry (expired / today / this_week / this_month / later / no_date).
# Formato: (product_name, zone_key, qty, unit, days_offset)
#   days_offset < 0 = ya expirado
#   days_offset == 0 = vence hoy
#   None = sin fecha de caducidad
INVENTORY_PLAN = [
    # ---- Lácteos (3 buckets) ----
    ("Leche Entera",         "fridge",  2.0,  "lt",    -2),  # expired
    ("Queso Cheddar",        "fridge",  0.3,  "kg",     3),  # this_week, low-stock
    ("Yogur Griego",         "fridge",  0.5,  "kg",     4),  # this_week
    # ---- Carne ----
    ("Bistec de Res",        "fridge",  0.3,  "kg",     2),  # this_week, low-stock
    ("Carne Molida",         "fridge",  0.5,  "kg",    10),  # this_month
    # ---- Aves ----
    ("Pechuga de Pollo",     "fridge",  1.0,  "kg",     0),  # today
    ("Huevos de Campo",      "fridge", 12.0,  "units",  7),  # this_week
    # ---- Pescado ----
    ("Filete de Salmón",     "fridge",  0.4,  "kg",     1),  # this_week
    ("Atún en Lata",         "pantry",  3.0,  "units", 365),  # later
    # ---- Verduras ----
    ("Espinaca Fresca",      "fridge",  0.5,  "kg",     1),  # this_week
    ("Tomates Roma",         "fridge",  0.4,  "kg",     4),  # this_week
    # ---- Frutas ----
    ("Plátanos",             "pantry",  3.0,  "units",  5),  # this_week
    ("Manzanas Rojas",       "pantry",  4.0,  "units", 14),  # this_month
    # ---- Granos ----
    ("Arroz Blanco",         "pantry",  2.0,  "kg",    60),  # later
    ("Quinoa",               "pantry",  1.0,  "kg",   180),  # later
    # ---- Pasta ----
    ("Espagueti",            "pantry",  1.0,  "kg",   120),  # later
    ("Penne",                "pantry",  0.8,  "kg",   365),  # later
    # ---- Pan ----
    ("Pan Integral",         "pantry",  1.0,  "units",  2),  # this_week
    ("Pan de Masa Madre",    "pantry",  1.0,  "units",  4),  # this_week
    # ---- Condimentos ----
    ("Ketchup",              "pantry",  0.5,  "lt",   300),  # later
    ("Mayonesa",             "pantry",  0.5,  "kg",   180),  # later
    # ---- Aceites ----
    ("Aceite de Oliva",      "pantry",  0.4,  "lt",   180),  # later, low-stock
    ("Aceite Vegetal",       "pantry",  1.0,  "lt",   365),  # later
    # ---- Salsas ----
    ("Salsa de Tomate",      "pantry",  0.5,  "lt",   120),  # later
    ("Salsa de Soja",        "pantry",  0.3,  "lt",   240),  # later
    # ---- Especias ----
    ("Pimienta Negra",       "pantry",  0.01, "kg",   None),  # no_date, low-stock
    ("Pimentón",             "pantry",  0.04, "kg",   None),  # no_date, low-stock
    # ---- Hierbas ----
    ("Albahaca Fresca",      "fridge",  0.1,  "kg",     2),  # this_week
    ("Cilantro",             "fridge",  0.1,  "kg",     3),  # this_week
    # ---- Bebidas ----
    ("Jugo de Naranja",      "fridge",  1.0,  "lt",    14),  # this_month
    ("Agua con Gas",         "pantry",  2.0,  "lt",   None),  # no_date
    # ---- Botanas ----
    ("Papas Fritas",         "pantry",  0.3,  "kg",    90),  # later
    ("Chocolate Negro",      "pantry",  0.2,  "kg",   180),  # later
    # ---- Enlatados ----
    ("Frijoles Negros",      "pantry",  0.5,  "kg",   365),  # later
    ("Maíz en Lata",         "pantry",  0.4,  "kg",   240),  # later
    # ---- Panadería ----
    ("Croissant",            "pantry",  4.0,  "units",  3),  # this_week
    ("Bagels",               "pantry",  6.0,  "units",  5),  # this_week
    # ---- Alternativas Lácteas ----
    ("Leche de Almendras",   "fridge",  1.0,  "lt",    30),  # this_month
    ("Bloque de Tofu",       "fridge",  0.4,  "kg",    10),  # this_month
    # ---- Comidas Preparadas ----
    ("Hummus",               "fridge",  0.3,  "kg",    10),  # this_month
    ("Sopa Lista",           "pantry",  0.5,  "lt",   150),  # later
    # ---- Congelados (en refri, no en freezer) ----
    ("Pizza Congelada",      "fridge",  1.0,  "units", 14),  # this_month
    # ---- Bebé ----
    ("Fórmula Infantil",     "pantry",  0.8,  "kg",   120),  # later
    ("Cereal para Bebé",     "pantry",  0.5,  "kg",   180),  # later
    # ---- Mascotas ----
    ("Comida para Perro",    "pantry",  2.0,  "kg",    60),  # later
    ("Snacks para Gato",     "pantry",  0.3,  "kg",   120),  # later
    # ---- Otros (no_date bucket) ----
    ("Sal",                  "pantry",  0.4,  "kg",   None),  # no_date, low-stock
    ("Azúcar",               "pantry",  1.0,  "kg",   None),  # no_date
]


# Items extra solo en el freezer. (product_name, qty, unit, days_until_expiry)
# Cubre expiry buckets tardíos (later) para mantener la zona con contenido.
FREEZER_PLAN = [
    ("Arvejas Congeladas", 1.0,  "kg",    90),
    ("Pizza Congelada",    2.0,  "units", 60),
    ("Filete de Salmón",   0.5,  "kg",    30),
    ("Bistec de Res",      0.3,  "kg",    45),
    ("Pechuga de Pollo",   0.5,  "kg",   180),
    ("Espinaca Fresca",    0.5,  "kg",   240),
    ("Hummus",             0.3,  "kg",    90),
    ("Bloque de Tofu",     0.4,  "kg",   120),
    ("Arroz Blanco",       1.0,  "kg",   365),
    ("Manzanas Rojas",     2.0,  "units",180),
    ("Pan de Masa Madre",  1.0,  "units", 30),
    ("Pan Integral",       1.0,  "units", 60),
]


# Items con status NO activo, para que /inventory/[id] muestre el mensaje
# "item was {status}". (product_name, status, days_ago_expired, qty, unit)
INACTIVE_PLAN = [
    ("Leche Entera",        "consumed",  -3, 0, "lt"),
    ("Queso Cheddar",       "discarded", -1, 0, "kg"),
    ("Espinaca Fresca",     "consumed",  -2, 0, "kg"),
    ("Yogur Griego",        "consumed",  -7, 0, "kg"),
    ("Bistec de Res",       "discarded",-10, 0, "kg"),
    ("Huevos de Campo",     "consumed", -14, 0, "units"),
    ("Pan de Masa Madre",   "discarded",-30, 0, "units"),
    ("Tomates Roma",        "consumed",  -2, 0, "kg"),
    ("Leche de Almendras",  "consumed", -45, 0, "lt"),
    ("Pizza Congelada",     "consumed",-120, 0, "units"),
    # Archived (older, never re-purchased)
    ("Azúcar",              "archived",-400, 0, "kg"),
]


# Items en Casa de Luis. (product_name, zone_key, qty, unit, days_until_expiry)
# Cubre categorías y buckets también para que el switcher de household
# tenga datos interesantes en los dos lados.
LUIS_INVENTORY_PLAN = [
    ("Leche Entera",         "fridge",  1.0,  "lt",    5),
    ("Huevos de Campo",      "fridge",  6.0,  "units",14),
    ("Pan de Masa Madre",    "fridge",  1.0,  "units", 3),
    ("Pizza Congelada",      "freezer", 1.0,  "units",90),
    ("Bistec de Res",        "fridge",  0.4,  "kg",    2),
    ("Plátanos",             "pantry",  4.0,  "units", 7),
    ("Manzanas Rojas",       "pantry",  3.0,  "units",21),
    ("Arroz Blanco",         "pantry",  1.5,  "kg",   90),
    ("Espagueti",            "pantry",  0.8,  "kg",  180),
    ("Aceite de Oliva",      "pantry",  0.5,  "lt",  300),
    ("Leche de Almendras",   "fridge",  0.8,  "lt",   14),
    ("Tomates Roma",         "fridge",  0.3,  "kg",    4),
    ("Pechuga de Pollo",     "fridge",  0.8,  "kg",    5),
    ("Queso Cheddar",        "fridge",  0.3,  "kg",    8),
    ("Espinaca Fresca",      "fridge",  0.4,  "kg",    1),
    ("Yogur Griego",         "fridge",  0.4,  "kg",    3),
    ("Comida para Perro",    "pantry",  1.5,  "kg",   60),
]


# Productos que tendran opened_date seteado (productos tipicamente abiertos
# antes de su consumo: leche, queso, hummus, etc.)
OPENED_PRODUCTS = {
    "Leche Entera", "Queso Cheddar", "Yogur Griego", "Hummus",
    "Bloque de Tofu", "Salsa de Tomate", "Leche de Almendras",
}


# Productos con threshold custom para que disparen/not-disparen low_stock segun
# convenga. Si el producto no aparece, usa DEFAULT=1.0
LOW_STOCK_OVERRIDES = {
    "Pimienta Negra": 0.02,
    "Pimentón": 0.05,
    "Sal": 0.5,
    "Aceite de Oliva": 0.5,
    "Bistec de Res": 0.2,
    "Tomates Roma": 0.5,
    "Hummus": 0.25,
    "Queso Cheddar": 0.4,
    "Espinaca Fresca": 0.3,
    "Carne Molida": 0.4,
    "Albahaca Fresca": 0.1,
    "Cilantro": 0.1,
    "Chocolate Negro": 0.3,
    "Salsa de Tomate": 0.4,
    "Papas Fritas": 0.5,
    "Maíz en Lata": 0.5,
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

        fridge = Refrigerator(id=uuid.uuid4(), household_id=casa.id, name="Refrigerador", type="refrigerator", sort_order=0)
        freezer = Refrigerator(id=uuid.uuid4(), household_id=casa.id, name="Congelador", type="freezer", sort_order=1)
        pantry = Refrigerator(id=uuid.uuid4(), household_id=casa.id, name="Despensa", type="pantry", sort_order=2)
        db.add_all([fridge, freezer, pantry])
        db.flush()

        zone_fridge = Zone(id=uuid.uuid4(), household_id=casa.id, refrigerator_id=fridge.id, name="Estantes", type="refrigerator", sort_order=0)
        zone_freezer = Zone(id=uuid.uuid4(), household_id=casa.id, refrigerator_id=freezer.id, name="Cajones", type="freezer", sort_order=0)
        zone_pantry = Zone(id=uuid.uuid4(), household_id=casa.id, refrigerator_id=pantry.id, name="Estantes de Despensa", type="pantry", sort_order=0)
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
        luis_pantry  = Refrigerator(id=uuid.uuid4(), household_id=casa_luis.id, name="Despensa",   type="pantry",    sort_order=2)
        db.add_all([luis_fridge, luis_freezer, luis_pantry])
        db.flush()

        luis_zone_fridge  = Zone(id=uuid.uuid4(), household_id=casa_luis.id, refrigerator_id=luis_fridge.id,  name="Estantes",         type="refrigerator", sort_order=0)
        luis_zone_freezer = Zone(id=uuid.uuid4(), household_id=casa_luis.id, refrigerator_id=luis_freezer.id, name="Cajones",          type="freezer",     sort_order=0)
        luis_zone_pantry  = Zone(id=uuid.uuid4(), household_id=casa_luis.id, refrigerator_id=luis_pantry.id,  name="Estantes de Despensa", type="pantry", sort_order=0)
        db.add_all([luis_zone_fridge, luis_zone_freezer, luis_zone_pantry])
        db.flush()

        # ---------- Products: 49 catalog items en AMBOS households ----------
        # image_url is left NULL on purpose: the frontend renders a Lucide icon
        # per category, no images are stored. See category-icons.ts in the FE.

        def _create_products_for(household_id):
            by_name = {}
            for name, category, unit in PRODUCTS:
                threshold = LOW_STOCK_OVERRIDES.get(name)
                p = Product(
                    id=uuid.uuid4(),
                    household_id=household_id,
                    name=name, category=category, default_unit=unit,
                    image_url=None,
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
        luis_zone_by_key = {"fridge": luis_zone_fridge, "freezer": luis_zone_freezer, "pantry": luis_zone_pantry}
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

        # ---------- Shopping list (manual + from-recipe, algunos ya marcados) ----------
        shopping_items = [
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Aceite de Oliva",   quantity=1,   unit="lt",    source="manual"),
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Ajo",              quantity=3,   unit="units", source="from-recipe"),
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Cebollas",         quantity=2,   unit="kg",    checked=True, source="manual"),
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Leche Entera",     quantity=2,   unit="lt",    source="manual"),
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Huevos de Campo",  quantity=12,  unit="units", source="from-recipe"),
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Pimienta Negra",   quantity=1,   unit="kg",    source="manual"),
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Tomates Roma",     quantity=1,   unit="kg",    checked=True, source="from-recipe"),
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Arroz Blanco",     quantity=1,   unit="kg",    source="manual"),
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Bistec de Res",    quantity=0.5, unit="kg",    source="from-recipe"),
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Espinaca Fresca",  quantity=0.5, unit="kg",    source="manual"),
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Queso Cheddar",    quantity=0.3, unit="kg",    source="from-recipe"),
            ShoppingListItem(id=uuid.uuid4(), household_id=casa.id, product_name="Hummus",          quantity=0.3, unit="kg",    checked=True, source="manual"),
        ]
        db.add_all(shopping_items)
        db.flush()

        # ---------- Activity log: 20+ entradas distribuidas en los últimos 7 días.
        # Cubre las 6 acciones de inventory_item + shopping_item + refrigerator.
        now = datetime.now(timezone.utc)
        activity_seed = [
            # (hours_ago, hh, actor, entity_id, entity_type, action, extra)
            # Inventory: las 6 acciones que pinta la UI
            (1,    casa.id, alice.id,    items_by_name["Leche Entera"].id,     "inventory_item", "created",   {"product_name": "Leche Entera"}),
            (3,    casa.id, bob.id,      items_by_name["Queso Cheddar"].id,    "inventory_item", "updated",   {"product_name": "Queso Cheddar", "changes": {"quantity": {"from": 0.5, "to": 0.3}}}),
            (6,    casa.id, alice.id,    items_by_name["Espinaca Fresca"].id,  "inventory_item", "consumed",  {"product_name": "Espinaca Fresca", "quantity_consumed": 0.3}),
            (12,   casa.id, alice.id,    items_by_name["Yogur Griego"].id,     "inventory_item", "discarded", {"product_name": "Yogur Griego"}),
            (24,   casa.id, lbizarro.id, items_by_name["Aceite de Oliva"].id,  "inventory_item", "restocked", {"product_name": "Aceite de Oliva", "delta": 1, "new_quantity": 0.5}),
            (36,   casa.id, alice.id,    items_by_name["Sal"].id,              "inventory_item", "deleted",   {"product_name": "Sal"}),
            (48,   casa.id, bob.id,      items_by_name["Pan de Masa Madre"].id,"inventory_item", "consumed",  {"product_name": "Pan de Masa Madre", "quantity_consumed": 1}),
            (60,   casa.id, alice.id,    items_by_name["Huevos de Campo"].id,  "inventory_item", "restocked", {"product_name": "Huevos de Campo", "delta": 6}),
            (72,   casa.id, lbizarro.id, items_by_name["Manzanas Rojas"].id,   "inventory_item", "consumed",  {"product_name": "Manzanas Rojas", "quantity_consumed": 1}),
            (96,   casa.id, alice.id,    items_by_name["Bistec de Res"].id,     "inventory_item", "consumed",  {"product_name": "Bistec de Res", "quantity_consumed": 0.3}),
            (120,  casa.id, alice.id,    items_by_name["Salsa de Tomate"].id,    "inventory_item", "updated", {"product_name": "Salsa de Tomate"}),
            (144,  casa.id, bob.id,      items_by_name["Leche de Almendras"].id,"inventory_item", "restocked", {"product_name": "Leche de Almendras", "delta": 1}),
            # Shopping items
            (2,    casa.id, alice.id,    shopping_items[0].id,                 "shopping_item",  "created",   {"product_name": "Aceite de Oliva"}),
            (5,    casa.id, bob.id,      shopping_items[1].id,                 "shopping_item",  "created",   {"product_name": "Ajo"}),
            (8,    casa.id, alice.id,    shopping_items[2].id,                 "shopping_item",  "updated",   {"product_name": "Cebollas", "changes": {"checked": {"from": False, "to": True}}}),
            (24,   casa.id, alice.id,    shopping_items[3].id,                 "shopping_item",  "created",   {"product_name": "Leche Entera"}),
            # Refrigerator / Zone
            (72,   casa.id, alice.id,    fridge.id,                            "refrigerator",   "created",   {"name": "Refrigerador"}),
            (48,   casa.id, alice.id,    freezer.id,                           "refrigerator",   "created",   {"name": "Congelador"}),
            (24,   casa.id, alice.id,    pantry.id,                            "refrigerator",   "created",   {"name": "Despensa"}),
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
            print(f"[reset_db] AlertService.scan_and_generate -> created={result.created}")
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
            print(f"  Products:        {db_summary.query(Product).count()} (across {len(CATEGORIES)} categories, icons via FE)")
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
