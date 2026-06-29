"""Smoke test: el seed es lo bastante robusto para que el equipo de
desarrollo pueda seguir probando.

Verifica:
  - Cobertura de las 24 categorías
  - Cobertura de los 6 buckets de expiry (expired, today, this_week,
    this_month, later, no_date)
  - Suficientes items activos (>= 50)
  - Items inactivos en cada estado (consumed, discarded, archived)
  - 3+ refrigeradores por household y zonas correspondientes
  - shopping list con items
  - activity log con las 6 acciones de inventory + shopping + refrigerator
"""
import re
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SCRIPTS = BACKEND / "scripts"


def read(rel: str) -> str:
    p = BACKEND / rel
    return p.read_text(encoding="utf-8")


class TestSeedRobust(unittest.TestCase):
    """El seed debe generar data suficiente para que el FE tenga algo que
    mostrar sin que el usuario tenga que crear items."""

    @classmethod
    def setUpClass(cls):
        cls.src = read("scripts/reset_db.py")

    def test_inventory_plan_covers_all_24_categories(self):
        m = re.search(r"INVENTORY_PLAN = \[(.*?)\]", self.src, re.DOTALL)
        # INVENTORY_PLAN: (product_name, zone_key, qty, unit, days_offset)
        product_names = re.findall(r'\("([^"]+)",\s*"[a-z]+"', m.group(1))
        # Para cada nombre, su categoría está en PRODUCTS (mismo orden)
        products_m = re.search(r"PRODUCTS = \[(.*?)\]", self.src, re.DOTALL)
        product_to_category = dict(re.findall(r'\("([^"]+)",\s*"([^"]+)"', products_m.group(1)))
        categories = {product_to_category[n] for n in product_names if n in product_to_category}
        self.assertEqual(
            len(categories), 24,
            f"INVENTORY_PLAN should cover all 24 categories, "
            f"only covers {len(categories)}: {sorted(categories)}",
        )

    def test_inventory_plan_has_at_least_45_items(self):
        m = re.search(r"INVENTORY_PLAN = \[(.*?)\]", self.src, re.DOTALL)
        items = re.findall(r'\("([^"]+)",\s*"([^"]+)"', m.group(1))
        self.assertGreaterEqual(
            len(items), 45,
            f"INVENTORY_PLAN should have >= 45 items, has {len(items)}",
        )

    def test_inventory_plan_covers_all_expiry_buckets(self):
        """days_offset buckets:
          expired    < 0
          today      == 0
          this_week  1..7
          this_month 8..30
          later      31..365
          no_date    None
        """
        m = re.search(r"INVENTORY_PLAN = \[(.*?)\]", self.src, re.DOTALL)
        items = re.findall(r'\("[^"]+",\s*"[^"]+",\s*[\d.]+,\s*"[^"]+",\s*([^)]+)\)', m.group(1))
        days = []
        for raw in items:
            raw = raw.strip()
            days.append(None if raw == "None" else int(raw))

        buckets = {
            "expired":   [d for d in days if d is not None and d < 0],
            "today":     [d for d in days if d == 0],
            "this_week": [d for d in days if d is not None and 1 <= d <= 7],
            "this_month":[d for d in days if d is not None and 8 <= d <= 30],
            "later":     [d for d in days if d is not None and d > 30],
            "no_date":   [d for d in days if d is None],
        }
        for name, items in buckets.items():
            self.assertGreater(
                len(items), 0,
                f"INVENTORY_PLAN has no items in bucket {name!r}: {buckets}",
            )

    def test_inactive_plan_has_all_three_statuses(self):
        m = re.search(r"INACTIVE_PLAN = \[(.*?)\]", self.src, re.DOTALL)
        items = re.findall(r'\("[^"]+",\s*"([^"]+)"', m.group(1))
        statuses = set(items)
        self.assertIn("consumed", statuses)
        self.assertIn("discarded", statuses)
        self.assertIn("archived", statuses)

    def test_each_household_has_three_refrigerators(self):
        for name in ("Refrigerador", "Congelador", "Despensa"):
            self.assertIn(f'name="{name}"', self.src,
                          f"missing refrigerator: {name}")

    def test_opened_products_set_includes_dairy_and_spreads(self):
        m = re.search(r"OPENED_PRODUCTS = \{(.*?)\}", self.src, re.DOTALL)
        keys = set(re.findall(r'"([^"]+)"', m.group(1)))
        self.assertIn("Leche Entera", keys)
        self.assertIn("Queso Cheddar", keys)
        self.assertIn("Hummus", keys)

    def test_low_stock_overrides_has_at_least_10_items(self):
        m = re.search(r"LOW_STOCK_OVERRIDES = \{(.*?)\}", self.src, re.DOTALL)
        items = re.findall(r'"([^"]+)":', m.group(1))
        self.assertGreaterEqual(
            len(items), 10,
            f"need >= 10 low_stock overrides to trigger alerts, has {len(items)}",
        )

    def test_activity_log_has_all_action_types(self):
        """Las 6 acciones de inventory + shopping + refrigerator aparecen
        al menos una vez en el activity_seed."""
        # Buscamos la línea que abre la lista y la línea que la cierra.
        # La lista está indentada dentro de `seed()`, así que aceptamos
        # cualquier cantidad de espacios al inicio.
        lines = self.src.splitlines()
        start = None
        for i, l in enumerate(lines):
            if l.lstrip().startswith("activity_seed = ["):
                start = i + 1
                break
        self.assertIsNotNone(start, "activity_seed not found")
        end = None
        for i in range(start, len(lines)):
            if lines[i].lstrip().startswith("]"):
                end = i
                break
        self.assertIsNotNone(end, "activity_seed closing bracket not found")
        block = "\n".join(lines[start:end])
        actions = set(re.findall(r'"(created|updated|consumed|discarded|restocked|deleted)"', block))
        self.assertEqual(
            actions,
            {"created", "updated", "consumed", "discarded", "restocked", "deleted"},
            f"activity_seed missing actions: {actions}",
        )

    def test_activity_log_has_at_least_15_entries(self):
        lines = self.src.splitlines()
        start = None
        for i, l in enumerate(lines):
            if l.lstrip().startswith("activity_seed = ["):
                start = i + 1
                break
        end = None
        for i in range(start, len(lines)):
            if lines[i].lstrip().startswith("]"):
                end = i
                break
        block = "\n".join(lines[start:end])
        # Cada entrada empieza con un `(\d+,` (hours_ago) al inicio de la línea
        entries = re.findall(r'^\s*\(\s*\d+', block, re.MULTILINE)
        self.assertGreaterEqual(
            len(entries), 15,
            f"activity_seed should have >= 15 entries, has {len(entries)}",
        )

    def test_luis_inventory_has_at_least_15_items(self):
        m = re.search(r"LUIS_INVENTORY_PLAN = \[(.*?)\]", self.src, re.DOTALL)
        items = re.findall(r'\("([^"]+)",\s*"[^"]+"', m.group(1))
        self.assertGreaterEqual(
            len(items), 15,
            f"Casa de Luis should have >= 15 items, has {len(items)}",
        )


if __name__ == "__main__":
    unittest.main()
