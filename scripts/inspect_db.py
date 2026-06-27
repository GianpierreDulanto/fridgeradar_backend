"""Inspect current DB state to inform seed audit."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from app.core.database import engine

with engine.connect() as c:
    print("=== Households ===")
    for h in c.execute(text("SELECT id, name, timezone, owner_user_id FROM households")).fetchall():
        print(f"  {h.id}  {h.name}  ({h.timezone})  owner={h.owner_user_id}")

    print("\n=== Household members by status ===")
    for r in c.execute(text("SELECT household_id, status, count(*) FROM household_members GROUP BY 1,2 ORDER BY 1,2")).fetchall():
        print(f"  HH={r.household_id}  status={r.status}  count={r.count}")

    print("\n=== Refrigerators ===")
    for r in c.execute(text("SELECT household_id, name, type, sort_order FROM refrigerators ORDER BY household_id, sort_order")).fetchall():
        print(f"  HH={r.household_id}  {r.name}  ({r.type})  order={r.sort_order}")

    print("\n=== Zones ===")
    for r in c.execute(text("SELECT household_id, name, type, refrigerator_id FROM zones ORDER BY household_id, type")).fetchall():
        print(f"  HH={r.household_id}  {r.name}  ({r.type})  ref={r.refrigerator_id}")

    print("\n=== Products ===")
    for r in c.execute(text("SELECT count(*) AS total, count(*) FILTER (WHERE image_url IS NOT NULL) AS with_image, count(*) FILTER (WHERE barcode IS NOT NULL) AS with_barcode FROM products")).fetchall():
        print(f"  total={r.total}  with_image={r.with_image}  with_barcode={r.with_barcode}")

    print("\n=== Inventory items by status ===")
    for r in c.execute(text("SELECT status, count(*) FROM inventory_items GROUP BY 1")).fetchall():
        print(f"  {r.status}: {r.count}")

    print("\n=== Inventory items by zone_type (active) ===")
    for r in c.execute(text("SELECT z.type, count(*) FROM inventory_items i JOIN zones z ON i.zone_id=z.id WHERE i.status='active' GROUP BY 1 ORDER BY 1")).fetchall():
        print(f"  {r.type}: {r.count}")

    print("\n=== Expiry buckets (active) ===")
    from datetime import date
    today = date.today()
    buckets = {"expired":0,"today":0,"urgent":0,"attention":0,"safe":0,"no_expiry":0}
    for r in c.execute(text("SELECT expiry_date FROM inventory_items WHERE status='active'")).fetchall():
        ed = r.expiry_date
        if ed is None:
            buckets["no_expiry"] += 1
        else:
            d = (ed - today).days
            if d < 0: buckets["expired"] += 1
            elif d == 0: buckets["today"] += 1
            elif d <= 3: buckets["urgent"] += 1
            elif d <= 7: buckets["attention"] += 1
            else: buckets["safe"] += 1
    for k,v in buckets.items():
        print(f"  {k}: {v}")

    print("\n=== Alerts by severity ===")
    for r in c.execute(text("SELECT severity, count(*) FROM alerts GROUP BY 1")).fetchall():
        print(f"  {r.severity}: {r.count}")

    print("\n=== Alerts by type ===")
    for r in c.execute(text("SELECT type, count(*) FROM alerts GROUP BY 1")).fetchall():
        print(f"  {r.type}: {r.count}")

    print("\n=== Shopping list ===")
    for r in c.execute(text("SELECT count(*) AS total, count(*) FILTER (WHERE checked) AS checked, count(*) FILTER (WHERE source IS NOT NULL) AS with_source FROM shopping_list_items")).fetchall():
        print(f"  total={r.total}  checked={r.checked}  with_source={r.with_source}")

    print("\n=== Activity log ===")
    for r in c.execute(text("SELECT entity_type, action, count(*) FROM activity_log GROUP BY 1,2 ORDER BY 1,2")).fetchall():
        print(f"  {r.entity_type} / {r.action}: {r.count}")

    print("\n=== Pending invitations (status='pending' in household_members) ===")
    rows = c.execute(text("SELECT household_id, user_id, role, invited_by FROM household_members WHERE status='pending'")).fetchall()
    if not rows:
        print("  (none)")
    for r in rows:
        print(f"  HH={r.household_id}  user={r.user_id}  role={r.role}  invited_by={r.invited_by}")

engine.dispose()
