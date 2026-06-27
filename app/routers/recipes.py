from fastapi import APIRouter, Depends, Query

from app.schemas.recipe import RecipeCookRequest, RecipeListResponse
from app.services.auth_service import get_current_user
from app.services.recipe_service import RecipeService, get_recipe_service

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


@router.get("/suggest", response_model=RecipeListResponse)
def suggest_recipes(
    household_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
    service: RecipeService = Depends(get_recipe_service),
):
    return service.suggest(household_id=household_id, current_user=current_user)


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
