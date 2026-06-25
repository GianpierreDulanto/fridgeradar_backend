from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.models import InventoryItem, Product, Zone, Refrigerator
from app.services.auth_service import get_current_user
import httpx

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


@router.get("/suggest")
async def suggest_recipes(
    household_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Get all active inventory items
    items = (
        db.query(InventoryItem)
        .join(Product, InventoryItem.product_id == Product.id)
        .filter(InventoryItem.household_id == household_id)
        .filter(InventoryItem.status == "active")
        .all()
    )

    if not items:
        return {"recipes": [], "message": "No items in inventory"}

    product_names = [item.product.name for item in items if item.product]

    # Try Gemini AI for recipe suggestions
    api_key = settings.gemini_api_key
    if api_key:
        try:
            prompt = f"I have these ingredients: {', '.join(product_names[:30])}. Suggest 3 recipes I can make. For each recipe give: name, brief description, list of ingredients I have, list of ingredients I might need to buy. Format as JSON array with fields: name, description, have_ingredients (array), need_ingredients (array)."

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
                    json={
                        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024},
                    },
                    timeout=15,
                )
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]

                import json as json_mod

                # Try to extract JSON from the response
                start = text.find("[")
                end = text.rfind("]") + 1
                if start >= 0 and end > start:
                    recipes = json_mod.loads(text[start:end])
                    return {"recipes": recipes, "source": "ai"}
        except Exception:
            pass

    # Fallback: simple suggestions based on categories
    categories = {}
    for item in items:
        cat = item.product.category if item.product else "Other"
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item.product.name)

    fallback_recipes = []
    if "Dairy" in categories and "Grains" in categories:
        fallback_recipes.append({
            "name": "Cereal Bowl",
            "description": "Quick breakfast with dairy and grains",
            "have_ingredients": categories.get("Dairy", [])[:3] + categories.get("Grains", [])[:3],
            "need_ingredients": [],
        })
    if "Vegetables" in categories and "Meat" in categories:
        fallback_recipes.append({
            "name": "Stir Fry",
            "description": "Quick stir fry with your vegetables and meat",
            "have_ingredients": categories.get("Vegetables", [])[:3] + categories.get("Meat", [])[:3],
            "need_ingredients": ["Soy sauce", "Oil", "Rice"],
        })
    if "Fruits" in categories:
        fallback_recipes.append({
            "name": "Fruit Salad",
            "description": "Fresh fruit salad for a healthy snack",
            "have_ingredients": categories.get("Fruits", [])[:5],
            "need_ingredients": [],
        })

    return {"recipes": fallback_recipes, "source": "fallback"}
