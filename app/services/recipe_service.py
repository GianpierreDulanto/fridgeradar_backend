"""
Recipe matching service.

Single source of truth for "Tengo hambre" / suggestions. Combines:
  - User inventory (with expiry / low_stock priorities from expiry_service)
  - Hardcoded fallback recipes (always available, no external deps)
  - Optional Gemini 2.0 Flash generation (validated against a Pydantic schema)

Public surface:
  - suggest(household_id) -> RecipeListResponse
  - cook(household_id, recipe_name, consume_ingredients) -> dict

The service is intentionally isolated from the inventory_service: it only
reads the DB (no cross-service calls) so it can be tested in isolation and
reused from the scheduler or CLI in the future.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date
from typing import Iterable

import httpx
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models import HouseholdMember, InventoryItem
from app.repositories.household_repository import HouseholdRepository
from app.repositories.inventory_repository import InventoryRepository
from app.schemas.recipe import (
    GeminiRecipe,
    GeminiRecipeIngredient,
    GeminiRecipeList,
    Recipe,
    RecipeCookRequest,
    RecipeIngredient,
    RecipeListResponse,
)
from app.services.auth_service import get_current_user
from app.services.expiry_service import (
    DEFAULT_LOW_STOCK_THRESHOLD,
    compute_expiry,
    compute_low_stock_priority,
    resolve_low_stock_threshold,
)

logger = logging.getLogger(__name__)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)
GEMINI_TIMEOUT_SECONDS = 15


# ---------------------------------------------------------------------------
# Hardcoded fallback recipes
# ---------------------------------------------------------------------------
# Each recipe lists the categories it draws from. The matcher checks if the
# user has any active product in each required category. Quantities / units
# are illustrative (frontend displays them; matcher only cares about presence).
#
# `dietary` is a set of tags; valid tags are exposed in `VALID_DIETARY_TAGS`
# below. `difficulty` ∈ {"easy","medium","hard"}. `max_time_minutes` is used
# by the `?max_time=` filter on /api/recipes/suggest.

VALID_DIFFICULTIES = ("easy", "medium", "hard")
VALID_DIETARY_TAGS = (
    "vegetarian",
    "vegan",
    "gluten_free",
    "dairy_free",
    "high_protein",
    "low_carb",
)

FALLBACK_RECIPES: list[dict] = [
    {
        "name": "Cereal Bowl",
        "description": "Quick breakfast with dairy and grains.",
        "needs_categories": ["Dairy", "Grains"],
        "max_time_minutes": 5,
        "difficulty": "easy",
        "dietary": ["vegetarian"],
        "ingredients": [
            {"name": "Whole Milk", "category": "Dairy", "quantity": 0.25, "unit": "lt"},
            {"name": "White Rice", "category": "Grains", "quantity": 0.05, "unit": "kg"},
        ],
    },
    {
        "name": "Stir Fry",
        "description": "Quick stir fry with your vegetables and meat.",
        "needs_categories": ["Vegetables", "Meat"],
        "max_time_minutes": 25,
        "difficulty": "medium",
        "dietary": ["high_protein"],
        "ingredients": [
            {"name": "Fresh Spinach", "category": "Vegetables", "quantity": 0.2, "unit": "kg"},
            {"name": "Beef Steak", "category": "Meat", "quantity": 0.15, "unit": "kg"},
        ],
    },
    {
        "name": "Fruit Salad",
        "description": "Fresh fruit salad for a healthy snack.",
        "needs_categories": ["Fruits"],
        "max_time_minutes": 10,
        "difficulty": "easy",
        "dietary": ["vegetarian", "vegan", "gluten_free", "dairy_free"],
        "ingredients": [
            {"name": "Bananas", "category": "Fruits", "quantity": 1, "unit": "units"},
            {"name": "Red Apples", "category": "Fruits", "quantity": 1, "unit": "units"},
        ],
    },
    {
        "name": "Pasta with Tomato Sauce",
        "description": "Classic comfort food, ready in 15 minutes.",
        "needs_categories": ["Pasta", "Sauces"],
        "max_time_minutes": 15,
        "difficulty": "easy",
        "dietary": ["vegetarian", "vegan"],
        "ingredients": [
            {"name": "Spaghetti", "category": "Pasta", "quantity": 0.2, "unit": "kg"},
            {"name": "Tomato Sauce", "category": "Sauces", "quantity": 0.15, "unit": "lt"},
        ],
    },
    {
        "name": "Chicken and Rice",
        "description": "Simple one-pan chicken with rice.",
        "needs_categories": ["Poultry", "Grains"],
        "max_time_minutes": 35,
        "difficulty": "medium",
        "dietary": ["gluten_free", "dairy_free", "high_protein"],
        "ingredients": [
            {"name": "Chicken Breast", "category": "Poultry", "quantity": 0.2, "unit": "kg"},
            {"name": "White Rice", "category": "Grains", "quantity": 0.1, "unit": "kg"},
        ],
    },
    {
        "name": "French Toast",
        "description": "Sweet breakfast with eggs and bread.",
        "needs_categories": ["Poultry", "Bread"],
        "max_time_minutes": 15,
        "difficulty": "easy",
        "dietary": ["vegetarian"],
        "ingredients": [
            {"name": "Free-Range Eggs", "category": "Poultry", "quantity": 2, "unit": "units"},
            {"name": "Whole Wheat Bread", "category": "Bread", "quantity": 2, "unit": "units"},
        ],
    },
    {
        "name": "Veggie Omelet",
        "description": "Quick omelet with vegetables.",
        "needs_categories": ["Poultry", "Vegetables"],
        "max_time_minutes": 12,
        "difficulty": "easy",
        "dietary": ["vegetarian", "gluten_free", "high_protein", "low_carb"],
        "ingredients": [
            {"name": "Free-Range Eggs", "category": "Poultry", "quantity": 3, "unit": "units"},
            {"name": "Fresh Spinach", "category": "Vegetables", "quantity": 0.1, "unit": "kg"},
        ],
    },
    {
        "name": "Cheese Toast",
        "description": "Toasted bread with melted cheese.",
        "needs_categories": ["Dairy", "Bread"],
        "max_time_minutes": 8,
        "difficulty": "easy",
        "dietary": ["vegetarian"],
        "ingredients": [
            {"name": "Cheddar Cheese", "category": "Dairy", "quantity": 0.05, "unit": "kg"},
            {"name": "Whole Wheat Bread", "category": "Bread", "quantity": 2, "unit": "units"},
        ],
    },
    {
        "name": "Veggie Rice Bowl",
        "description": "Rice bowl loaded with fresh vegetables.",
        "needs_categories": ["Grains", "Vegetables"],
        "max_time_minutes": 25,
        "difficulty": "easy",
        "dietary": ["vegetarian", "vegan", "gluten_free", "dairy_free"],
        "ingredients": [
            {"name": "White Rice", "category": "Grains", "quantity": 0.15, "unit": "kg"},
            {"name": "Fresh Spinach", "category": "Vegetables", "quantity": 0.15, "unit": "kg"},
            {"name": "Red Apples", "category": "Fruits", "quantity": 1, "unit": "units"},
        ],
    },
    {
        "name": "Beef Tacos",
        "description": "Tacos stuffed with seasoned beef and fresh salsa.",
        "needs_categories": ["Meat", "Vegetables", "Bakery"],
        "max_time_minutes": 30,
        "difficulty": "medium",
        "dietary": ["dairy_free"],
        "ingredients": [
            {"name": "Beef Steak", "category": "Meat", "quantity": 0.2, "unit": "kg"},
            {"name": "Fresh Spinach", "category": "Vegetables", "quantity": 0.1, "unit": "kg"},
            {"name": "Whole Wheat Bread", "category": "Bakery", "quantity": 2, "unit": "units"},
        ],
    },
]


# ---------------------------------------------------------------------------


class RecipeService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = InventoryRepository(db)
        self.household_repo = HouseholdRepository(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def suggest(
        self,
        household_id: str,
        current_user: dict,
        max_time: int | None = None,
        difficulty: str | None = None,
        dietary: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> RecipeListResponse:
        """Suggest recipes for the household, with optional filters and pagination.

        RF-REC-017: max_time, difficulty, dietary filters.
        RF-REC-018: limit/offset pagination.
        RF-REC-019: not implemented here (see daily()).
        """
        self._check_membership(household_id, current_user["id"])
        self._validate_filters(difficulty=difficulty, dietary=dietary)

        items = self.repo.list_by_household(household_id, status="active")
        have_index = self._build_have_index(items)
        summary = self._inventory_summary(items)

        if not items:
            return RecipeListResponse(
                recipes=[],
                source="fallback",
                message="No items in inventory",
                inventory_summary=summary,
                total=0,
                limit=limit,
                offset=offset,
            )

        # Try Gemini first
        ai_recipes = self._generate_with_gemini(have_index, current_user)
        scored: list[Recipe]
        source: str
        if ai_recipes:
            scored = [self._score_recipe(r, have_index) for r in ai_recipes]
            source = "ai"
        else:
            fallback = [
                self._fallback_recipe_to_dict(r, have_index)
                for r in FALLBACK_RECIPES
            ]
            scored = [self._score_recipe(r, have_index) for r in fallback if r is not None]
            source = "fallback"

        # Apply filters (RF-REC-017)
        scored = self._apply_filters(scored, max_time=max_time, difficulty=difficulty, dietary=dietary)

        return self._finalize_paginated(
            scored, source=source, summary=summary, limit=limit, offset=offset
        )

    def daily(self, household_id: str, current_user: dict) -> Recipe:
        """Return today's recipe of the day (RF-REC-019).

        Deterministic per day: index = day_of_year % len(matched_recipes). If
        the household has no usable recipes, returns the first fallback recipe
        so the UI always has something to show.
        """
        self._check_membership(household_id, current_user["id"])
        items = self.repo.list_by_household(household_id, status="active")
        have_index = self._build_have_index(items)
        summary = self._inventory_summary(items)

        if not items:
            # Still return a fallback so the UI is never empty.
            chosen = FALLBACK_RECIPES[0]
        else:
            ai_recipes = self._generate_with_gemini(have_index, current_user)
            candidates: list[dict] = []
            if ai_recipes:
                candidates = ai_recipes
            else:
                for r in FALLBACK_RECIPES:
                    normalized = self._fallback_recipe_to_dict(r, have_index)
                    if normalized is not None:
                        candidates.append(normalized)
            if not candidates:
                chosen = FALLBACK_RECIPES[0]
            else:
                scored = [self._score_recipe(c, have_index) for c in candidates]
                scored.sort(
                    key=lambda r: (r.priority_score, r.match_pct, r.waste_rescue_score),
                    reverse=True,
                )
                day_idx = date.today().toordinal() % len(scored)
                chosen_dict = candidates[day_idx] if day_idx < len(candidates) else candidates[0]
                return self._score_recipe(chosen_dict, have_index)

        normalized = self._fallback_recipe_to_dict(chosen, have_index) or chosen
        return self._score_recipe(normalized, have_index)

    def missing_ingredients_for_recipe(
        self, household_id: str, recipe_name: str, current_user: dict
    ) -> list[dict]:
        """Return the list of ingredients the household is MISSING for a recipe.

        Used by RF-REC-015 to push to the shopping list.
        """
        self._check_membership(household_id, current_user["id"])
        items = self.repo.list_by_household(household_id, status="active")
        have_index = self._build_have_index(items)

        recipe = self._find_recipe_by_name(recipe_name)
        if recipe is None:
            raise HTTPException(status_code=404, detail=f"Recipe '{recipe_name}' not found")

        scored = self._score_recipe(recipe, have_index)
        return [
            {
                "name": ing.name,
                "quantity": ing.quantity,
                "unit": ing.unit,
            }
            for ing in scored.need_ingredients
        ]

    @staticmethod
    def _find_recipe_by_name(name: str) -> dict | None:
        target = name.strip().lower()
        for r in FALLBACK_RECIPES:
            if r["name"].lower() == target:
                return r
        return None

    @staticmethod
    def _validate_filters(difficulty: str | None, dietary: list[str] | None) -> None:
        if difficulty is not None and difficulty not in VALID_DIFFICULTIES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid difficulty '{difficulty}'. Allowed: {list(VALID_DIFFICULTIES)}",
            )
        if dietary:
            invalid = [d for d in dietary if d not in VALID_DIETARY_TAGS]
            if invalid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid dietary tag(s): {invalid}. Allowed: {list(VALID_DIETARY_TAGS)}",
                )

    @staticmethod
    def _apply_filters(
        recipes: list[Recipe],
        max_time: int | None,
        difficulty: str | None,
        dietary: list[str] | None,
    ) -> list[Recipe]:
        out = recipes
        if max_time is not None:
            out = [
                r for r in out
                if r.max_time_minutes is None or r.max_time_minutes <= max_time
            ]
        if difficulty is not None:
            out = [r for r in out if r.difficulty == difficulty]
        if dietary:
            wanted = set(dietary)
            out = [r for r in out if wanted.issubset(set(r.dietary or []))]
        return out

    def cook(
        self,
        household_id: str,
        recipe_name: str,
        consume_ingredients: list[RecipeIngredient],
        current_user: dict,
    ) -> dict:
        """Deduct `consume_ingredients` from matching inventory items.

        For each ingredient, we find the best inventory match by name (case
        insensitive) and subtract the requested quantity. If the resulting
        quantity is <= 0, the inventory item is marked as 'consumed'.
        """
        self._check_membership(household_id, current_user["id"])
        items = self.repo.list_by_household(household_id, status="active")
        have_index = self._build_have_index(items)

        consumed: list[dict] = []
        for ing in consume_ingredients:
            match = self._find_inventory_match(ing, have_index)
            if not match:
                continue
            item = match["item"]
            new_qty = float(item.quantity) - float(ing.quantity or 1)
            if new_qty <= 0:
                item.status = "consumed"
                item.quantity = 0
            else:
                item.quantity = new_qty
            self.repo.update(item)
            consumed.append({
                "product_name": match["product"].name,
                "consumed_quantity": ing.quantity or 1,
                "new_quantity": float(item.quantity),
                "status": item.status,
            })

        return {
            "recipe_name": recipe_name,
            "household_id": household_id,
            "consumed": consumed,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _check_membership(self, household_id: str, user_id: str) -> None:
        members = self.household_repo.get_members(household_id)
        if not any(str(m.user_id) == user_id for m, _ in members):
            raise HTTPException(status_code=403, detail="Not a member of this household")

    def _build_have_index(self, items: list[InventoryItem]) -> dict:
        """Return a dict {lowercase_product_name: {item, product, expiry_info, low_stock_priority, is_urgent}}.

        Also indexed by category -> list of products for category-based matching.
        """
        index: dict = {"by_name": {}, "by_category": {}}
        for item in items:
            if not item.product:
                continue
            product = item.product
            expiry = compute_expiry(item.expiry_date)
            threshold = resolve_low_stock_threshold(product)
            qty = float(item.quantity) if item.quantity is not None else 0.0
            low_stock_pri = compute_low_stock_priority(qty, threshold) if qty < threshold else 0
            is_urgent = (
                expiry["status"] in ("expired", "today", "urgent", "attention")
                or low_stock_pri > 0
            )
            entry = {
                "item": item,
                "product": product,
                "expiry": expiry,
                "low_stock_priority": low_stock_pri,
                "is_urgent": is_urgent,
                "priority_score": max(expiry["priority_score"], low_stock_pri),
            }
            index["by_name"][product.name.lower()] = entry
            cat = (product.category or "Other").lower()
            index["by_category"].setdefault(cat, []).append(entry)
        return index

    def _inventory_summary(self, items: list[InventoryItem]) -> dict:
        today = date.today()
        urgent = 0
        expired = 0
        low_stock = 0
        for item in items:
            expiry = compute_expiry(item.expiry_date, today)
            if expiry["status"] in ("expired", "today", "urgent", "attention"):
                urgent += 1
            if expiry["status"] == "expired":
                expired += 1
            if item.product is not None:
                threshold = resolve_low_stock_threshold(item.product)
                if item.quantity is not None and float(item.quantity) < threshold:
                    low_stock += 1
        return {
            "have": len(items),
            "urgent": urgent,
            "expired": expired,
            "low_stock": low_stock,
        }

    # ----- Gemini -----

    def _generate_with_gemini(self, have_index: dict, current_user: dict) -> list[dict] | None:
        api_key = settings.gemini_api_key
        if not api_key:
            return None

        product_names = list(have_index["by_name"].keys())[:30]
        prompt = self._build_gemini_prompt(product_names)
        try:
            with httpx.Client(timeout=GEMINI_TIMEOUT_SECONDS) as client:
                resp = client.post(
                    f"{GEMINI_URL}?key={api_key}",
                    json={
                        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": 0.7,
                            "maxOutputTokens": 1024,
                            "responseMimeType": "application/json",
                        },
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logger.warning("gemini call failed: %s", e)
            return None

        return self._parse_gemini_response(text)

    @staticmethod
    def _build_gemini_prompt(product_names: list[str]) -> str:
        listed = ", ".join(product_names)
        return (
            "You are a recipe assistant. The user has the following ingredients: "
            f"{listed}.\n"
            "Suggest 3 recipes they can make. Prefer recipes that use ingredients "
            "that are about to expire or that they already have in good quantity.\n"
            "Respond ONLY with valid JSON in this exact shape, no prose, no markdown:\n"
            '{"recipes": ['
            '{"name": "Recipe Name", "description": "One sentence.", '
            '"have_ingredients": [{"name": "X", "quantity": 1, "unit": "kg"}], '
            '"need_ingredients": [{"name": "Y", "quantity": 0.5, "unit": "lt"}]}, '
            "...]}"
        )

    def _parse_gemini_response(self, text: str) -> list[dict] | None:
        """Extract JSON from the Gemini text and validate with Pydantic.

        Gemini may wrap the JSON in markdown code fences or add prose. We try
        the strictest parse first, then progressively relax.
        """
        if not text:
            return None

        candidates = [text.strip()]
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fenced:
            candidates.insert(0, fenced.group(1))
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace >= 0 and last_brace > first_brace:
            candidates.append(text[first_brace : last_brace + 1])

        for raw in candidates:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            try:
                validated = GeminiRecipeList.model_validate(parsed)
            except Exception as e:
                logger.debug("gemini schema validation failed: %s", e)
                continue
            return [r.model_dump() for r in validated.recipes]

        logger.warning("gemini response did not match RecipeList schema")
        return None

    # ----- Fallback normalization -----

    def _fallback_recipe_to_dict(self, recipe: dict, have_index: dict) -> dict | None:
        """Convert a FALLBACK_RECIPES entry to the internal recipe dict shape.

        Returns None if the user has zero products in any of the required
        categories (recipe is irrelevant to this user).
        """
        required = [c.lower() for c in recipe["needs_categories"]]
        matched = [c for c in required if have_index["by_category"].get(c)]
        if not matched:
            return None
        return {
            "name": recipe["name"],
            "description": recipe["description"],
            "needs_categories": recipe["needs_categories"],
            "ingredients": recipe["ingredients"],
            "max_time_minutes": recipe.get("max_time_minutes"),
            "difficulty": recipe.get("difficulty"),
            "dietary": list(recipe.get("dietary", [])),
        }

    # ----- Scoring -----

    def _score_recipe(self, recipe: dict, have_index: dict) -> Recipe:
        """Compute match_pct and waste_rescue_score for a recipe.

        match_pct: % of recipe ingredients the user has in inventory.
        waste_rescue_score: % of (matched) ingredients that are urgent.

        We weight waste_rescue more heavily (60/40) because the whole point
        of the feature is to rescue items about to expire.
        """
        ingredients = recipe.get("ingredients", [])
        if not ingredients:
            return self._build_recipe(recipe, match_pct=0, waste_rescue=0, have=[], need=[])

        have_entries: list[RecipeIngredient] = []
        need_entries: list[RecipeIngredient] = []
        urgent_used = 0

        for ing in ingredients:
            entry = self._match_ingredient(ing, have_index)
            if entry is None:
                need_entries.append(RecipeIngredient(
                    name=ing.get("name", ""),
                    quantity=ing.get("quantity"),
                    unit=ing.get("unit"),
                    is_have=False,
                    is_urgent=False,
                ))
                continue
            is_urgent = entry["is_urgent"]
            have_entries.append(RecipeIngredient(
                name=entry["product"].name,
                quantity=ing.get("quantity"),
                unit=ing.get("unit"),
                is_have=True,
                is_urgent=is_urgent,
            ))
            if is_urgent:
                urgent_used += 1

        total = len(ingredients)
        match_pct = (len(have_entries) / total) * 100 if total else 0
        waste_rescue = (urgent_used / len(have_entries) * 100) if have_entries else 0

        return self._build_recipe(
            recipe,
            match_pct=round(match_pct, 2),
            waste_rescue=round(waste_rescue, 2),
            have=have_entries,
            need=need_entries,
        )

    def _match_ingredient(self, ing: dict, have_index: dict) -> dict | None:
        """Try to find an inventory item that satisfies this ingredient.

        Strategy:
          1. Exact name match (case insensitive).
          2. Category match — pick the first item in that category.
        """
        name = (ing.get("name") or "").lower()
        if name and name in have_index["by_name"]:
            return have_index["by_name"][name]
        cat = (ing.get("category") or "").lower()
        if cat and have_index["by_category"].get(cat):
            return have_index["by_category"][cat][0]
        return None

    def _find_inventory_match(self, ing: RecipeIngredient, have_index: dict) -> dict | None:
        name = (ing.name or "").lower()
        if name in have_index["by_name"]:
            return have_index["by_name"][name]
        for entry in have_index["by_name"].values():
            if name and name in entry["product"].name.lower():
                return entry
        return None

    def _build_recipe(
        self,
        recipe: dict,
        match_pct: float,
        waste_rescue: float,
        have: list[RecipeIngredient],
        need: list[RecipeIngredient],
    ) -> Recipe:
        priority = round(waste_rescue * 0.6 + match_pct * 0.4, 2)
        return Recipe(
            id=str(uuid.uuid4()),
            name=recipe.get("name", "Untitled"),
            description=recipe.get("description"),
            match_pct=match_pct,
            waste_rescue_score=waste_rescue,
            priority_score=priority,
            have_ingredients=have,
            need_ingredients=need,
            source=recipe.get("source", "fallback"),
            max_time_minutes=recipe.get("max_time_minutes"),
            difficulty=recipe.get("difficulty"),
            dietary=list(recipe.get("dietary", [])),
        )

    def _finalize(
        self,
        scored: list[Recipe],
        source: str,
        summary: dict,
    ) -> RecipeListResponse:
        # Sort: priority desc, then match_pct desc, then waste_rescue desc.
        scored.sort(key=lambda r: (r.priority_score, r.match_pct, r.waste_rescue_score), reverse=True)
        for r in scored:
            r.source = source
        return RecipeListResponse(
            recipes=scored,
            source=source,
            inventory_summary=summary,
            total=len(scored),
            limit=len(scored),
            offset=0,
        )

    def _finalize_paginated(
        self,
        scored: list[Recipe],
        source: str,
        summary: dict,
        limit: int,
        offset: int,
    ) -> RecipeListResponse:
        scored.sort(key=lambda r: (r.priority_score, r.match_pct, r.waste_rescue_score), reverse=True)
        for r in scored:
            r.source = source
        total = len(scored)
        window = scored[offset : offset + limit]
        return RecipeListResponse(
            recipes=window,
            source=source,
            inventory_summary=summary,
            total=total,
            limit=limit,
            offset=offset,
        )


def get_recipe_service(db: Session = Depends(get_db)) -> RecipeService:
    return RecipeService(db)
