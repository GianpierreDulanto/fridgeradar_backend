"""
Poblar image_url de los productos desde Open Food Facts.

USO:
    # Solo Casa de Alice (default):
    python scripts/fetch_product_images.py

    # Todos los households del usuario:
    python scripts/fetch_product_images.py --all

NOTAS:
  - Open Food Facts rate-limita agresivamente IPs compartidas. Por eso este
    script serializa con ~3s entre requests (~2.5 min para 49 productos).
  - Si OFF devuelve 503 / timeout, el producto se queda con image_url=NULL
    y el script continua con el siguiente (no aborta).
  - El script es idempotente: re-ejecutar solo actualiza los NULL.
  - Este script es OPCIONAL. El seed (reset_db.py) no lo llama por defecto
    para que el seed sea rapido.
"""
import argparse
import asyncio
import os
import sys
import time

import httpx
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine
from app.models import Household, Product


HEADERS = {"User-Agent": "FridgeRadar-FetchImages/1.0 (contact: dev@local)"}
DELAY_BETWEEN_REQUESTS = 3.0
REQUEST_TIMEOUT = 15.0


async def _fetch_one(client: httpx.AsyncClient, name: str) -> str | None:
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
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        products = data.get("products") or []
        if products and products[0].get("image_url"):
            return products[0]["image_url"]
    except Exception:
        return None
    return None


async def fetch_all(names: list[str], delay_s: float) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    async with httpx.AsyncClient() as client:
        for i, n in enumerate(names, 1):
            url = await _fetch_one(client, n)
            out[n] = url
            marker = "OK" if url else "MISS"
            print(f"  [{i:2d}/{len(names)}] [{marker}] {n}")
            await asyncio.sleep(delay_s)
    return out


def main():
    parser = argparse.ArgumentParser(description="Fetch product image_url from Open Food Facts")
    parser.add_argument("--all", action="store_true", help="Process all households (default: only Casa de Alice)")
    parser.add_argument("--delay", type=float, default=DELAY_BETWEEN_REQUESTS, help="Seconds between OFF requests")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.all:
            households = db.query(Household).all()
        else:
            alice = db.query(Household).filter(Household.name == "Casa de Alice").first()
            households = [alice] if alice else []
        if not households:
            print("No households found. Run scripts/reset_db.py first.")
            return 1

        total_updated = 0
        for hh in households:
            print(f"\n=== Household: {hh.name} ===")
            products = (
                db.query(Product)
                .filter(Product.household_id == hh.id)
                .order_by(Product.name)
                .all()
            )
            # Solo procesamos los que aun no tienen image_url (idempotente)
            to_fetch = [p for p in products if not p.image_url]
            print(f"Products total: {len(products)}, sin image_url: {len(to_fetch)}")
            if not to_fetch:
                print("  (nada que hacer)")
                continue

            names = [p.name for p in to_fetch]
            estimated_s = len(names) * args.delay
            print(f"Estimated time: {estimated_s:.0f}s (delay={args.delay}s, requests={len(names)})")

            urls = asyncio.run(fetch_all(names, args.delay))

            updated = 0
            for p in to_fetch:
                url = urls.get(p.name)
                if url:
                    p.image_url = url
                    updated += 1
            if updated:
                db.commit()
            total_updated += updated
            print(f"  -> {updated}/{len(to_fetch)} productos actualizados en {hh.name}")

        print(f"\nTotal actualizado: {total_updated}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
