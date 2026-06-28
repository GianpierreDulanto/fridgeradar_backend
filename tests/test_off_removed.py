"""Smoke test: post-OFF cleanup is complete.

Verifies:
  - `food_api` module is gone
  - `products` router is gone
  - `main.py` does not import/include them
  - `inventory_service.create` is sync (no `await`, no `fetch_product_image`)
  - `reset_db.py` has no OFF integration (httpx/asyncio/fetch_product removed)
  - `requirements.txt` keeps httpx only because ai.py and recipe_service still use it
"""
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SRC = BACKEND / "app"
SCRIPTS = BACKEND / "scripts"


def read(rel: str) -> str:
    p = BACKEND / rel
    return p.read_text(encoding="utf-8")


class TestOffRemoved(unittest.TestCase):
    def test_food_api_module_deleted(self):
        self.assertFalse(
            (SRC / "services" / "food_api.py").exists(),
            "app/services/food_api.py should be removed",
        )

    def test_products_router_deleted(self):
        self.assertFalse(
            (SRC / "routers" / "products.py").exists(),
            "app/routers/products.py should be removed",
        )

    def test_fetch_product_images_script_deleted(self):
        self.assertFalse(
            (SCRIPTS / "fetch_product_images.py").exists(),
            "scripts/fetch_product_images.py should be removed",
        )

    def test_main_no_products_import(self):
        src = read("app/main.py")
        self.assertNotIn("products", src, "main.py should not reference products router")
        self.assertNotIn("food_api", src)

    def test_inventory_create_no_await(self):
        src = read("app/services/inventory_service.py")
        # No fetch_product_image call
        self.assertNotIn("fetch_product_image", src)
        self.assertNotIn("from app.services.food_api", src)
        # create() should be sync (not async)
        m = re.search(r"def create\(\s*\n\s*self", src)
        self.assertIsNotNone(m, "inventory_service.create method missing")
        self.assertNotIn(
            "async def create",
            src,
            "inventory_service.create should not be async after OFF removal",
        )

    def test_inventory_router_no_await_create(self):
        src = read("app/routers/inventory.py")
        self.assertNotIn("await service.create", src)

    def test_reset_db_no_off_imports(self):
        src = read("scripts/reset_db.py")
        self.assertNotIn("import httpx", src)
        self.assertNotIn("import asyncio", src)
        self.assertNotIn("openfoodfacts", src.lower())
        # Stubs are no longer needed but if they exist they must be no-ops
        if "maybe_fetch_images" in src:
            self.assertIn("return {n: None for n in names}", src)
        if "fetch_product_images" in src:
            self.assertIn("return {n: None for n in names}", src)

    def test_requirements_keep_httpx_for_ai(self):
        """httpx is still needed by ai.py (Gemini) and recipe_service.py
        (Gemini throttle). We don't remove the dep just because OFF is gone."""
        reqs = read("requirements.txt")
        self.assertIn("httpx", reqs)

    def test_ai_and_recipes_still_use_httpx(self):
        """Sanity check: the two remaining httpx users are AI/chat and
        recipe gemini — those should not regress."""
        ai_src = read("app/routers/ai.py")
        self.assertIn("httpx", ai_src)
        recipe_src = read("app/services/recipe_service.py")
        self.assertIn("httpx", recipe_src)

    def test_app_still_loads(self):
        """The whole app must import without errors after the OFF removal."""
        out = subprocess.run(
            [sys.executable, "-c", "from app.main import app; print(f'ok:{len(app.routes)}')"],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(out.returncode, 0, f"app failed to import: {out.stderr}")
        self.assertTrue(
            out.stdout.startswith("ok:"),
            f"unexpected stdout: {out.stdout!r}",
        )
        # Should still have a healthy number of routes (we removed 1: products).
        route_count = int(out.stdout.split(":")[1])
        self.assertGreater(route_count, 40)


if __name__ == "__main__":
    unittest.main()
