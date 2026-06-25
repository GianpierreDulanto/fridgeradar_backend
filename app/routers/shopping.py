from fastapi import APIRouter, Depends, Query

from app.schemas.shopping import (
    ShoppingItemCreate,
    ShoppingItemUpdate,
    ShoppingItemResponse,
)
from app.services.shopping_service import (
    ShoppingService,
    get_shopping_service,
)
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/shopping-lists", tags=["shopping"])


@router.get("/current", response_model=list[ShoppingItemResponse])
def get_current(
    household_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
    service: ShoppingService = Depends(get_shopping_service),
):
    return service.get_current(household_id=household_id, current_user=current_user)


@router.post("/items", response_model=ShoppingItemResponse)
def add_item(
    body: ShoppingItemCreate,
    current_user: dict = Depends(get_current_user),
    service: ShoppingService = Depends(get_shopping_service),
):
    return service.add_item(
        household_id=body.household_id,
        product_name=body.product_name,
        quantity=body.quantity,
        unit=body.unit,
        current_user=current_user,
    )


@router.patch("/items/{item_id}", response_model=ShoppingItemResponse)
def update_item(
    item_id: str,
    body: ShoppingItemUpdate,
    current_user: dict = Depends(get_current_user),
    service: ShoppingService = Depends(get_shopping_service),
):
    return service.update_item(
        item_id=item_id,
        updates=body.model_dump(exclude_none=True),
        current_user=current_user,
    )


@router.delete("/items/{item_id}")
def delete_item(
    item_id: str,
    current_user: dict = Depends(get_current_user),
    service: ShoppingService = Depends(get_shopping_service),
):
    service.delete_item(item_id=item_id, current_user=current_user)
    return {"message": "Item deleted"}
