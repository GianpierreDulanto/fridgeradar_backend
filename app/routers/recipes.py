from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.schemas.recipe import Recipe, RecipeCookRequest, RecipeListResponse
from app.services.auth_service import get_current_user
from app.services.recipe_service import RecipeService, get_recipe_service

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


@router.get("/suggest", response_model=RecipeListResponse)
def suggest_recipes(
    household_id: Annotated[str, Query(...)],
    max_time: Annotated[int | None, Query(ge=1, le=600, description="Max prep time in minutes")] = None,
    difficulty: Annotated[
        str | None,
        Query(description="Recipe difficulty: easy | medium | hard"),
    ] = None,
    dietary: Annotated[
        list[str] | None,
        Query(description="Dietary tags (repeatable). Must all be present."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    current_user: dict = Depends(get_current_user),
    service: RecipeService = Depends(get_recipe_service),
):
    return service.suggest(
        household_id=household_id,
        current_user=current_user,
        max_time=max_time,
        difficulty=difficulty,
        dietary=dietary,
        limit=limit,
        offset=offset,
    )


@router.get("/daily", response_model=Recipe)
def recipe_of_the_day(
    household_id: Annotated[str, Query(...)],
    current_user: dict = Depends(get_current_user),
    service: RecipeService = Depends(get_recipe_service),
):
    """Return the recipe of the day (RF-REC-019). Deterministic per day."""
    return service.daily(household_id=household_id, current_user=current_user)


@router.get("/{recipe_name}/missing")
def missing_ingredients(
    recipe_name: str,
    household_id: Annotated[str, Query(...)],
    current_user: dict = Depends(get_current_user),
    service: RecipeService = Depends(get_recipe_service),
):
    """Return the ingredients the household is missing for the given recipe.

    Used by the frontend before adding them to the shopping list (RF-REC-015).
    """
    return service.missing_ingredients_for_recipe(
        household_id=household_id, recipe_name=recipe_name, current_user=current_user
    )


@router.post("/cook")
def cook_recipe(
    body: RecipeCookRequest,
    current_user: dict = Depends(get_current_user),
    service: RecipeService = Depends(get_recipe_service),
):
    return service.cook(
        household_id=body.household_id,
        recipe_name=body.recipe_name,
        consume_ingredients=body.consume_ingredients,
        current_user=current_user,
    )
