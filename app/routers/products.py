from fastapi import APIRouter, Depends, Query, HTTPException
import httpx
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("/search")
async def search_products(
    q: str = Query(..., min_length=1),
    current_user: dict = Depends(get_current_user),
):
    """Search Open Food Facts for products by name."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://world.openfoodfacts.org/cgi/search.pl",
                params={
                    "search_terms": q,
                    "search_simple": 1,
                    "action": "process",
                    "fields": "product_name,categories_tags,image_url,code,brands",
                    "json": 1,
                    "page_size": 20,
                },
                timeout=10,
            )
            data = resp.json()
            products = data.get("products", [])
            results = []
            for p in products:
                cat_tags = p.get("categories_tags", [])
                category = None
                if cat_tags:
                    cat = cat_tags[0].replace("en:", "").replace("-", " ").title()
                    category = cat
                results.append({
                    "name": p.get("product_name", q).strip(),
                    "category": category,
                    "image_url": p.get("image_url"),
                    "barcode": p.get("code"),
                    "brand": p.get("brands"),
                })
            return results[:20]
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to search products")
