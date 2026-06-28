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

import hashlib
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
from app.services.gemini_throttle import (
    GeminiThrottle,
    _GeminiRateLimited,
    gemini_throttle,
)
from app.services.expiry_service import (
    DEFAULT_LOW_STOCK_THRESHOLD,
    compute_expiry,
    compute_low_stock_priority,
    resolve_low_stock_threshold,
)

logger = logging.getLogger(__name__)

GEMINI_TIMEOUT_SECONDS = 15


def _gemini_url(model: str) -> str:
    return (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )


def _stable_recipe_id(name: str, source: str = "fallback") -> str:
    """Deterministic id for a recipe based on its name + source.

    The frontend uses this id as a React key and to address the same recipe
    across pages. We use a SHA-1 of `name|source` (truncated to 16 chars) so:
      * the same recipe always gets the same id (stable React keys, real
        pagination/dedup),
      * AI and fallback variants of the same name don't collide.
    """
    raw = f"{(name or '').strip().lower()}|{source}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


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
        "name": "Tazón de Cereal",
        "description": "Desayuno rápido con lácteos y granos.",
        "needs_categories": ["Lácteos", "Granos"],
        "max_time_minutes": 5,
        "difficulty": "easy",
        "dietary": ["vegetarian"],
        "ingredients": [
            {"name": "Leche Entera", "category": "Lácteos", "quantity": 0.25, "unit": "lt"},
            {"name": "Arroz Blanco", "category": "Granos", "quantity": 0.05, "unit": "kg"},
        ],
    },
    {
        "name": "Salteado de Verduras",
        "description": "Salteado rápido con tus verduras y carne.",
        "needs_categories": ["Verduras", "Carne"],
        "max_time_minutes": 25,
        "difficulty": "medium",
        "dietary": ["high_protein"],
        "ingredients": [
            {"name": "Espinaca Fresca", "category": "Verduras", "quantity": 0.2, "unit": "kg"},
            {"name": "Bistec de Res", "category": "Carne", "quantity": 0.15, "unit": "kg"},
        ],
    },
    {
        "name": "Ensalada de Frutas",
        "description": "Ensalada de frutas frescas para un snack saludable.",
        "needs_categories": ["Frutas"],
        "max_time_minutes": 10,
        "difficulty": "easy",
        "dietary": ["vegetarian", "vegan", "gluten_free", "dairy_free"],
        "ingredients": [
            {"name": "Plátanos", "category": "Frutas", "quantity": 1, "unit": "units"},
            {"name": "Manzanas Rojas", "category": "Frutas", "quantity": 1, "unit": "units"},
        ],
    },
    {
        "name": "Pasta con Salsa de Tomate",
        "description": "Comida clásica reconfortante, lista en 15 minutos.",
        "needs_categories": ["Pasta", "Salsas"],
        "max_time_minutes": 15,
        "difficulty": "easy",
        "dietary": ["vegetarian", "vegan"],
        "ingredients": [
            {"name": "Espagueti", "category": "Pasta", "quantity": 0.2, "unit": "kg"},
            {"name": "Salsa de Tomate", "category": "Salsas", "quantity": 0.15, "unit": "lt"},
        ],
    },
    {
        "name": "Pollo con Arroz",
        "description": "Pollo con arroz en una sola sartén.",
        "needs_categories": ["Aves", "Granos"],
        "max_time_minutes": 35,
        "difficulty": "medium",
        "dietary": ["gluten_free", "dairy_free", "high_protein"],
        "ingredients": [
            {"name": "Pechuga de Pollo", "category": "Aves", "quantity": 0.2, "unit": "kg"},
            {"name": "Arroz Blanco", "category": "Granos", "quantity": 0.1, "unit": "kg"},
        ],
    },
    {
        "name": "Tostadas Francesas",
        "description": "Desayuno dulce con huevos y pan.",
        "needs_categories": ["Aves", "Pan"],
        "max_time_minutes": 15,
        "difficulty": "easy",
        "dietary": ["vegetarian"],
        "ingredients": [
            {"name": "Huevos de Campo", "category": "Aves", "quantity": 2, "unit": "units"},
            {"name": "Pan Integral", "category": "Pan", "quantity": 2, "unit": "units"},
        ],
    },
    {
        "name": "Omelette de Verduras",
        "description": "Omelette rápido con verduras.",
        "needs_categories": ["Aves", "Verduras"],
        "max_time_minutes": 12,
        "difficulty": "easy",
        "dietary": ["vegetarian", "gluten_free", "high_protein", "low_carb"],
        "ingredients": [
            {"name": "Huevos de Campo", "category": "Aves", "quantity": 3, "unit": "units"},
            {"name": "Espinaca Fresca", "category": "Verduras", "quantity": 0.1, "unit": "kg"},
        ],
    },
    {
        "name": "Tostada con Queso",
        "description": "Pan tostado con queso derretido.",
        "needs_categories": ["Lácteos", "Pan"],
        "max_time_minutes": 8,
        "difficulty": "easy",
        "dietary": ["vegetarian"],
        "ingredients": [
            {"name": "Queso Cheddar", "category": "Lácteos", "quantity": 0.05, "unit": "kg"},
            {"name": "Pan Integral", "category": "Pan", "quantity": 2, "unit": "units"},
        ],
    },
    {
        "name": "Bowl de Arroz con Verduras",
        "description": "Bowl de arroz cargado con verduras frescas.",
        "needs_categories": ["Granos", "Verduras"],
        "max_time_minutes": 25,
        "difficulty": "easy",
        "dietary": ["vegetarian", "vegan", "gluten_free", "dairy_free"],
        "ingredients": [
            {"name": "Arroz Blanco", "category": "Granos", "quantity": 0.15, "unit": "kg"},
            {"name": "Espinaca Fresca", "category": "Verduras", "quantity": 0.15, "unit": "kg"},
            {"name": "Manzanas Rojas", "category": "Frutas", "quantity": 1, "unit": "units"},
        ],
    },
    {
        "name": "Tacos de Res",
        "description": "Tacos rellenos de res sazonada y salsa fresca.",
        "needs_categories": ["Carne", "Verduras", "Panadería"],
        "max_time_minutes": 30,
        "difficulty": "medium",
        "dietary": ["dairy_free"],
        "ingredients": [
            {"name": "Bistec de Res", "category": "Carne", "quantity": 0.2, "unit": "kg"},
            {"name": "Espinaca Fresca", "category": "Verduras", "quantity": 0.1, "unit": "kg"},
            {"name": "Pan Integral", "category": "Panadería", "quantity": 2, "unit": "units"},
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
        """Ask Gemini for personalized recipe suggestions.

        The call is gated by `gemini_throttle` (process-wide):
          * cache hit -> instant return (no network)
          * cooldown (after a 429) -> returns None so the caller falls back
          * rate-limit (4s between calls) -> same
          * 429 during the call -> enters exponential cooldown (1m, 2m, 4m, ...)
            so we stop hammering the API while the quota recovers.
          * 4xx (e.g. 422: model not available, bad request format) -> logs the
            full response body once and tries the configured fallback model
            once before giving up. No cooldown (a bad-request error doesn't
            rate-limit future calls).
        """
        api_key = settings.gemini_api_key
        if not api_key:
            return None

        # Stable cache key: same inventory snapshot -> same recipes. The model
        # is part of the key so swapping models in dev doesn't return stale
        # results from the previous model.
        product_names = sorted(have_index["by_name"].keys())[:30]
        cache_key = gemini_throttle.make_key(
            "recipes.suggest", settings.gemini_model, product_names
        )

        models_to_try = [settings.gemini_model]
        if settings.gemini_fallback_model and settings.gemini_fallback_model != settings.gemini_model:
            models_to_try.append(settings.gemini_fallback_model)

        for model in models_to_try:
            payload = {
                "contents": [{"role": "user", "parts": [{"text": self._build_gemini_prompt(product_names)}]}],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 1024,
                    "responseMimeType": "application/json",
                },
            }

            # Bind `model` and `payload` as default args to avoid the
            # late-binding closure trap. Each loop iteration creates a new
            # function with its own bound values.
            def _do_call(model=model, payload=payload) -> list[dict] | None:
                with httpx.Client(timeout=GEMINI_TIMEOUT_SECONDS) as client:
                    resp = client.post(
                        f"{_gemini_url(model)}?key={api_key}",
                        json=payload,
                    )
                    if resp.status_code == 429:
                        raise _GeminiRateLimited(f"HTTP 429: {resp.text[:200]}")
                    if resp.status_code >= 400:
                        # Log the FULL response body so we can see exactly
                        # what Gemini is complaining about (model not found,
                        # bad format, quota issue, etc.).
                        logger.warning(
                            "gemini %s returned %d for model=%s: %s",
                            _gemini_url(model), resp.status_code, model,
                            resp.text[:500],
                        )
                        resp.raise_for_status()
                    data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return self._parse_gemini_response(text)

            result = gemini_throttle.acquire_and_call(
                cache_key,
                f"recipe_service._generate_with_gemini[{model}]",
                _do_call,
            )
            if result is not None:
                return result
            # 4xx or parse failure: try the next model.
            next_idx = models_to_try.index(model) + 1
            next_model = models_to_try[next_idx] if next_idx < len(models_to_try) else "none"
            logger.info(
                "gemini model=%s unavailable or returned no recipes, "
                "falling back (next: %s)",
                model, next_model,
            )

        return None

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
        source = recipe.get("source", "fallback")
        return Recipe(
            id=_stable_recipe_id(recipe.get("name", ""), source),
            name=recipe.get("name", "Untitled"),
            description=recipe.get("description"),
            match_pct=match_pct,
            waste_rescue_score=waste_rescue,
            priority_score=priority,
            have_ingredients=have,
            need_ingredients=need,
            source=source,
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
