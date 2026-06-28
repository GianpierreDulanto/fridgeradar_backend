"""Smoke test: el seed está completamente en español (idioma principal)."""
import re
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SCRIPTS = BACKEND / "scripts"


def read(rel: str) -> str:
    p = BACKEND / rel
    return p.read_text(encoding="utf-8")


class TestSeedInSpanish(unittest.TestCase):
    """El seed es la fuente de verdad del contenido visible: productos,
    categorías, refrigeradores, zonas y recetas deben estar en español."""

    @classmethod
    def setUpClass(cls):
        cls.src = read("scripts/reset_db.py")
        cls.recipe_src = read("app/services/recipe_service.py")

    def test_categories_list_is_spanish(self):
        m = re.search(r"CATEGORIES = \[(.*?)\]", self.src, re.DOTALL)
        self.assertIsNotNone(m, "CATEGORIES not found in reset_db.py")
        categories = re.findall(r'"([^"]+)"', m.group(1))
        self.assertEqual(len(categories), 24, f"expected 24 categories, got {len(categories)}")
        spanish_categories = {
            "Lácteos", "Carne", "Aves", "Pescado", "Verduras", "Frutas",
            "Granos", "Pasta", "Pan", "Condimentos", "Aceites", "Salsas",
            "Especias", "Hierbas", "Bebidas", "Botanas", "Congelados",
            "Enlatados", "Panadería", "Alternativas Lácteas",
            "Comidas Preparadas", "Bebé", "Mascotas", "Otros",
        }
        self.assertEqual(set(categories), spanish_categories)

    def test_products_count(self):
        m = re.search(r"PRODUCTS = \[(.*?)\]", self.src, re.DOTALL)
        self.assertIsNotNone(m)
        products = re.findall(r'\("([^"]+)",', m.group(1))
        self.assertEqual(len(products), 49, f"expected 49 products, got {len(products)}")

    def test_sample_products_are_spanish(self):
        m = re.search(r"PRODUCTS = \[(.*?)\]", self.src, re.DOTALL)
        products = re.findall(r'\("([^"]+)",', m.group(1))
        expected = [
            "Leche Entera", "Queso Cheddar", "Yogur Griego", "Bistec de Res",
            "Pechuga de Pollo", "Huevos de Campo", "Espinaca Fresca",
            "Plátanos", "Manzanas Rojas", "Arroz Blanco", "Espagueti",
            "Pan Integral", "Pan de Masa Madre", "Aceite de Oliva",
            "Pasta de Tomate" if False else "Salsa de Tomate",
            "Pizza Congelada", "Croissant", "Leche de Almendras",
            "Bloque de Tofu", "Hummus", "Comida para Perro",
            "Snacks para Gato", "Sal", "Azúcar",
        ]
        for name in expected:
            self.assertIn(name, products, f"missing product: {name}")

    def test_refrigerators_are_spanish(self):
        self.assertIn('name="Refrigerador"', self.src)
        self.assertIn('name="Congelador"', self.src)
        self.assertIn('name="Despensa"', self.src)

    def test_zones_are_spanish(self):
        self.assertIn('name="Estantes"', self.src)
        self.assertIn('name="Cajones"', self.src)

    def test_inventory_plan_uses_spanish_product_names(self):
        m = re.search(r"INVENTORY_PLAN = \[(.*?)\]", self.src, re.DOTALL)
        self.assertIsNotNone(m)
        names = re.findall(r'\("([^"]+)",', m.group(1))
        self.assertIn("Leche Entera", names)
        self.assertIn("Huevos de Campo", names)
        self.assertIn("Pan de Masa Madre", names)
        # No raw English names
        for en in ["Whole Milk", "Free-Range Eggs", "Sourdough Loaf", "Frozen Pizza"]:
            self.assertNotIn(en, names, f"inventory plan still has English name: {en}")

    def test_low_stock_overrides_use_spanish_keys(self):
        m = re.search(r"LOW_STOCK_OVERRIDES = \{(.*?)\}", self.src, re.DOTALL)
        self.assertIsNotNone(m)
        keys = re.findall(r'"([^"]+)":', m.group(1))
        # Las keys de LOW_STOCK_OVERRIDES tienen que ser nombres de producto
        # del seed (en español). No validamos contra un whitelist de categorías
        # porque los thresholds son por producto, no por categoría.
        product_m = re.search(r"PRODUCTS = \[(.*?)\]", self.src, re.DOTALL)
        product_names = set(re.findall(r'\("([^"]+)",', product_m.group(1)))
        for k in keys:
            self.assertIn(k, product_names,
                f"low_stock_overrides key not in PRODUCTS: {k}")
        # Y ninguno de los viejos nombres en inglés puede quedar.
        # "Hummus" se queda en español/inglés igual, así que no lo verificamos.
        for en in ["Black Pepper", "Paprika", "Salt", "Olive Oil",
                    "Beef Steak", "Roma Tomatoes"]:
            self.assertNotIn(en, keys, f"english key still in LOW_STOCK_OVERRIDES: {en}")

    def test_recipe_categories_are_spanish(self):
        # needs_categories in FALLBACK_RECIPES
        m = re.search(r"\"needs_categories\":\s*\[([^\]]+)\]", self.recipe_src)
        cats = re.findall(r'"([^"]+)"', m.group(1))
        spanish_only = {"Lácteos", "Carne", "Aves", "Verduras", "Frutas",
                         "Granos", "Pasta", "Salsas", "Pan", "Panadería"}
        for c in cats:
            self.assertIn(c, spanish_only, f"recipe category still in English: {c}")

    def test_recipe_ingredient_categories_are_spanish(self):
        # Every {"name": ..., "category": ...} inside FALLBACK_RECIPES ingredients
        # must use a Spanish category. "Pasta" is the same in both languages
        # (borrowed from Italian), so we allow it.
        spanish_only = {
            "Lácteos", "Carne", "Aves", "Pescado", "Verduras", "Frutas",
            "Granos", "Pasta", "Pan", "Condimentos", "Aceites", "Salsas",
            "Especias", "Hierbas", "Bebidas", "Botanas", "Congelados",
            "Enlatados", "Panadería", "Alternativas Lácteas",
            "Comidas Preparadas", "Bebé", "Mascotas", "Otros",
        }
        for m in re.finditer(r'\{"name":\s*"([^"]+)",\s*"category":\s*"([^"]+)"',
                              self.recipe_src):
            self.assertIn(m.group(2), spanish_only,
                f"recipe ingredient category not in Spanish whitelist: {m.group(2)} (ingredient {m.group(1)})")

    def test_recipe_names_are_spanish(self):
        m = re.findall(r'"name":\s*"([^"]+)"', self.recipe_src)
        spanish_recipes = {"Tazón de Cereal", "Salteado de Verduras",
                            "Ensalada de Frutas", "Pasta con Salsa de Tomate",
                            "Pollo con Arroz", "Tostadas Francesas",
                            "Omelette de Verduras", "Tostada con Queso",
                            "Bowl de Arroz con Verduras", "Tacos de Res"}
        for r in m:
            if r in {"Cereal Bowl", "Stir Fry", "Fruit Salad", "French Toast",
                     "Cheese Toast", "Veggie Omelet", "Veggie Rice Bowl",
                     "Beef Tacos", "Chicken and Rice", "Pasta with Tomato Sauce"}:
                self.fail(f"recipe still in English: {r}")


if __name__ == "__main__":
    unittest.main()
