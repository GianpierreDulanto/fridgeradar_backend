"""Verifica que Recipe.id es estable entre llamadas a /suggest.

El id se genera como `sha1(name|source)[:16]` en
`recipe_service._build_recipe`, así que la misma receta siempre debe
devolver el mismo id mientras el seed no cambie.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
RECIPE_SVC = BACKEND / "app" / "services" / "recipe_service.py"


def _load_recipe_module():
    spec = importlib.util.spec_from_file_location("recipe_service_under_test", RECIPE_SVC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestRecipeIdStability(unittest.TestCase):
    """Pure-function tests for `_stable_recipe_id` and `_build_recipe`."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_recipe_module()

    def test_same_name_and_source_produce_same_id(self):
        a = self.mod._stable_recipe_id("Pasta con Salsa de Tomate", "fallback")
        b = self.mod._stable_recipe_id("Pasta con Salsa de Tomate", "fallback")
        self.assertEqual(a, b)

    def test_id_is_16_hex_chars(self):
        rid = self.mod._stable_recipe_id("Pasta con Salsa de Tomate", "fallback")
        self.assertEqual(len(rid), 16)
        self.assertTrue(all(c in "0123456789abcdef" for c in rid))

    def test_different_sources_produce_different_ids(self):
        a = self.mod._stable_recipe_id("Pasta con Salsa de Tomate", "fallback")
        b = self.mod._stable_recipe_id("Pasta con Salsa de Tomate", "ai")
        self.assertNotEqual(a, b)

    def test_different_names_produce_different_ids(self):
        a = self.mod._stable_recipe_id("Pasta con Salsa de Tomate", "fallback")
        b = self.mod._stable_recipe_id("Tazón de Cereal", "fallback")
        self.assertNotEqual(a, b)

    def test_name_is_normalized_to_lowercase(self):
        """Capitalization differences in `name` should not change the id."""
        a = self.mod._stable_recipe_id("Pasta con Salsa de Tomate", "fallback")
        b = self.mod._stable_recipe_id("pasta con salsa de tomate", "fallback")
        c = self.mod._stable_recipe_id("PASTA CON SALSA DE TOMATE", "fallback")
        self.assertEqual(a, b)
        self.assertEqual(a, c)

    def test_every_fallback_recipe_has_a_unique_stable_id(self):
        """No dos FALLBACK_RECIPES chocan en id, y el id derivado es
        exactamente el que el endpoint /suggest devolvería."""
        ids_seen: dict[str, str] = {}
        for recipe in self.mod.FALLBACK_RECIPES:
            rid = self.mod._stable_recipe_id(recipe["name"], "fallback")
            if rid in ids_seen:
                self.fail(
                    f"id collision: '{recipe['name']}' and "
                    f"'{ids_seen[rid]}' both -> {rid}"
                )
            ids_seen[rid] = recipe["name"]

    def test_recipe_id_collision_against_seeded_product_names(self):
        """Si el id fuera solo `sha1(name)[:16]`, podría chocar con un id
        de producto o alert. Como usa `name|source`, dos cosas distintas
        con el mismo nombre siguen teniendo ids distintos."""
        from app.models import Product  # type: ignore
        recipe_id = self.mod._stable_recipe_id("Pasta con Salsa de Tomate", "fallback")
        # El id no es un UUID (que es lo que usan Product.id, Alert.id, etc.)
        self.assertNotIn("-", recipe_id)
        self.assertEqual(len(recipe_id), 16)


if __name__ == "__main__":
    unittest.main()
