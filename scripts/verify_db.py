"""
Verificación de la base de datos para las 3 parejas.

USO:
    python scripts/verify_db.py

Imprime un reporte completo del estado de la base y devuelve exit code:
    0 = todo OK para que las 3 parejas trabajen
    1 = falta algo (zonas sin refrigerator, <2 productos por categoría,
        <2 items de low_stock, o bucket de expiry_status sin datos)

Cubre:
  - Pareja A: schema, zonas con refrigerator_id, conteos.
  - Pareja B: distribución de expiry_status, alertas por severidad,
    items de low_stock, potencial de alertas si se ejecutara el scan.
  - Pareja C: productos por categoría (mínimo 2 por categoría).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import date

from app.core.database import SessionLocal
from app.models import (
    Alert, Household, HouseholdMember, InventoryItem, Product, User, Zone,
)
from app.models.refrigerator import Refrigerator


LOW_STOCK_THRESHOLD = 1.0

EXPIRY_BUCKETS = ("expired", "today", "urgent", "attention", "safe", "no_expiry")
ALERT_SEVERITIES = ("critical", "warning", "info")


def compute_expiry_status(expiry_date, today):
    if expiry_date is None:
        return None
    diff = (expiry_date - today).days
    if diff < 0:
        return "expired"
    if diff == 0:
        return "today"
    if diff <= 3:
        return "urgent"
    if diff <= 7:
        return "attention"
    return "safe"


def compute_alert_spec(expiry_date, today):
    """Replica la lógica de alert_service para calcular lo que el scan generaría."""
    if expiry_date is None:
        return None
    diff = (expiry_date - today).days
    if diff < 0:
        return ("expired", "critical")
    if diff == 0:
        return ("expiring_today", "critical")
    if diff <= 3:
        return ("expiring_soon", "warning")
    if diff <= 7:
        return ("expiring_soon", "info")
    return None


def section(title):
    print()
    print(f"=== {title} ===")


def check_schema(db):
    section("Schema")
    p = db.query(Product).first()
    has_image = bool(p) and hasattr(p, "image_url")
    has_threshold = bool(p) and hasattr(p, "low_stock_threshold")
    print(f"  [{'OK' if has_image else 'WARN'}] Product.image_url attribute present")
    print(f"  [{'OK' if has_threshold else 'WARN'}] Product.low_stock_threshold attribute present")
    m = db.query(HouseholdMember).first()
    has_invited = bool(m) and hasattr(m, "invited_by")
    has_status = bool(m) and hasattr(m, "status")
    print(f"  [{'OK' if has_invited else 'WARN'}] HouseholdMember.invited_by present")
    print(f"  [{'OK' if has_status else 'WARN'}] HouseholdMember.status present")
    sample_item = db.query(InventoryItem).first()
    has_priority_item = bool(sample_item) and hasattr(sample_item, "priority_score")
    print(f"  [{'OK' if has_priority_item else 'WARN'}] InventoryItem.priority_score attribute present")
    sample_alert = db.query(Alert).first()
    has_priority_alert = bool(sample_alert) and hasattr(sample_alert, "priority_score")
    print(f"  [{'OK' if has_priority_alert else 'WARN'}] Alert.priority_score attribute present")
    return all([
        has_image, has_threshold, has_invited, has_status, has_priority_item, has_priority_alert,
    ])


def check_counts(db):
    section("Counts")
    print(f"  Users:           {db.query(User).count()}")
    print(f"  Households:      {db.query(Household).count()}")
    print(f"  Refrigerators:   {db.query(Refrigerator).count()}")
    print(f"  Zones:           {db.query(Zone).count()}")
    print(f"  Products:        {db.query(Product).count()}")
    print(f"  Inventory items: {db.query(InventoryItem).count()}")
    print(f"  Alerts:          {db.query(Alert).count()}")

    by_status = {s: 0 for s in ("active", "consumed", "discarded", "archived")}
    for it in db.query(InventoryItem).all():
        by_status[it.status] = by_status.get(it.status, 0) + 1
    print("  Inventory by status:")
    for s, n in by_status.items():
        print(f"    {s}: {n}")


def check_zones(db):
    section("Zones -> Refrigerator")
    zones = db.query(Zone).all()
    all_ok = True
    for z in zones:
        ok = z.refrigerator_id is not None
        all_ok = all_ok and ok
        marker = "OK" if ok else "FAIL"
        print(f"  [{marker}] {z.name} -> refrigerator_id={z.refrigerator_id}")
    return all_ok


def check_expiry_distribution(db):
    section("Expiry status (active items)")
    today = date.today()
    items = db.query(InventoryItem).filter(InventoryItem.status == "active").all()
    buckets = {b: 0 for b in EXPIRY_BUCKETS}
    for it in items:
        st = compute_expiry_status(it.expiry_date, today)
        buckets[st if st else "no_expiry"] += 1
    for b in EXPIRY_BUCKETS:
        marker = "OK" if buckets[b] > 0 else "EMPTY"
        print(f"  [{marker}] {b}: {buckets[b]}")
    return buckets


def check_alerts(db):
    section("Alerts by severity (current state)")
    by_sev = {s: 0 for s in ALERT_SEVERITIES}
    for a in db.query(Alert).all():
        by_sev[a.severity] = by_sev.get(a.severity, 0) + 1
    for s in ALERT_SEVERITIES:
        print(f"  {s}: {by_sev[s]}")

    section("Alerts that scan_and_generate WOULD produce right now")
    today = date.today()
    potential = {s: 0 for s in ALERT_SEVERITIES}
    items = db.query(InventoryItem).filter(InventoryItem.status == "active").all()
    for it in items:
        spec = compute_alert_spec(it.expiry_date, today)
        if spec:
            potential[spec[1]] += 1
    for s in ALERT_SEVERITIES:
        print(f"  {s}: {potential[s]}")


def check_categories(db):
    section("Products by category")
    by_cat = {}
    for p in db.query(Product).all():
        key = p.category or "(uncategorized)"
        by_cat[key] = by_cat.get(key, 0) + 1
    sorted_cats = sorted(by_cat.items(), key=lambda x: (-x[1], x[0]))
    all_ok = True
    for cat, n in sorted_cats:
        ok = n >= 2
        all_ok = all_ok and ok
        marker = "OK" if ok else "FEW"
        print(f"  [{marker}] {cat}: {n}")
    return all_ok


def check_low_stock(db):
    section(f"Low stock (active items, quantity < {LOW_STOCK_THRESHOLD})")
    items = (
        db.query(InventoryItem)
        .filter(
            InventoryItem.status == "active",
            InventoryItem.quantity < LOW_STOCK_THRESHOLD,
        )
        .all()
    )
    if not items:
        print("  (none)")
    for it in items:
        prod_name = it.product.name if it.product else "?"
        print(f"  - {prod_name}: qty={it.quantity} {it.unit or ''}")
    return len(items) >= 2


def main():
    db = SessionLocal()
    try:
        check_schema(db)
        check_counts(db)
        zones_ok = check_zones(db)
        buckets = check_expiry_distribution(db)
        check_alerts(db)
        categories_ok = check_categories(db)
        low_stock_ok = check_low_stock(db)

        section("Health verdict")
        buckets_ok = all(buckets[b] > 0 for b in ("expired", "today", "urgent", "attention"))
        overall = zones_ok and categories_ok and low_stock_ok and buckets_ok

        print(f"  Zones assigned to refrigerator:    {'PASS' if zones_ok else 'FAIL'}")
        print(f"  All expiry buckets populated:      {'PASS' if buckets_ok else 'FAIL'}")
        print(f"  Categories with >=2 products:      {'PASS' if categories_ok else 'FAIL'}")
        print(f"  Low stock items >=2:               {'PASS' if low_stock_ok else 'FAIL'}")
        print(f"  Overall:                           {'PASS' if overall else 'FAIL'}")
        return 0 if overall else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
