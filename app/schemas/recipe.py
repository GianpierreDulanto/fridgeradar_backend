from __future__ import annotations

from pydantic import BaseModel, Field


class RecipeIngredient(BaseModel):
    """A single ingredient referenced by a recipe.

    The `is_have` flag is set by the service after matching against the user's
    inventory. The frontend uses it to decide whether to show the ingredient
    under "You have" or "You need".
    """

    name: str
    quantity: float | None = None
    unit: str | None = None
    is_have: bool = False
    is_urgent: bool = False  # True if the inventory match is expiring soon / today / expired / low_stock


class Recipe(BaseModel):
    id: str
    name: str
    description: str | None = None
    match_pct: float = Field(ge=0, le=100, description="% of ingredients the user already has")
    waste_rescue_score: float = Field(ge=0, le=100, description="How much this recipe helps consume urgent items")
    priority_score: float = Field(ge=0, description="Combined score: waste_rescue * 0.6 + match_pct * 0.4")
    have_ingredients: list[RecipeIngredient] = []
    need_ingredients: list[RecipeIngredient] = []
    source: str = "fallback"  # "ai" or "fallback"


class RecipeListResponse(BaseModel):
    recipes: list[Recipe] = []
    source: str  # "ai" or "fallback" — source of the suggestions
    message: str | None = None
    inventory_summary: dict | None = None  # counts: {have, urgent, expired, low_stock}


# Internal schema used to parse the JSON returned by Gemini.
# Allows partial / loose matching because Gemini doesn't always return
# perfectly clean JSON, and we want to fail gracefully.
class GeminiRecipeIngredient(BaseModel):
    name: str = ""
    quantity: float | None = None
    unit: str | None = None


class GeminiRecipe(BaseModel):
    name: str = ""
    description: str | None = None
    have_ingredients: list[GeminiRecipeIngredient | str] = []
    need_ingredients: list[GeminiRecipeIngredient | str] = []


class GeminiRecipeList(BaseModel):
    recipes: list[GeminiRecipe] = []


class RecipeCookRequest(BaseModel):
    """Payload for POST /api/recipes/{id}/cook.

    The service deducts the `have_ingredients` quantities from the matching
    inventory items, marking items as `consumed` when their quantity hits 0.
    """

    household_id: str
    recipe_name: str
    consume_ingredients: list[RecipeIngredient] = []
