import httpx
from typing import Optional

async def fetch_product_image(product_name: str) -> Optional[str]:
    """Search Open Food Facts for a product image."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://world.openfoodfacts.org/cgi/search.pl",
                params={
                    "search_terms": product_name,
                    "search_simple": 1,
                    "action": "process",
                    "fields": "image_url,product_name",
                    "json": 1,
                    "page_size": 1,
                },
                timeout=10,
            )
            data = resp.json()
            products = data.get("products", [])
            if products and products[0].get("image_url"):
                return products[0]["image_url"]
    except Exception:
        pass
    return None
