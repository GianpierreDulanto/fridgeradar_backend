from fastapi import APIRouter, Depends, Query

from app.schemas.inventory import (
    InventoryAction,
    InventoryCreate,
    InventoryListResponse,
    InventoryResponse,
    InventoryUpdate,
)
from app.services.inventory_service import (
    InventoryService,
    get_inventory_service,
)
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/inventory-items", tags=["inventory"])


@router.get("", response_model=InventoryListResponse)
def list_items(
    household_id: str = Query(...),
    zone_id: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
):
    return service.list(
        household_id=household_id,
        zone_id=zone_id,
        status=status,
        limit=limit,
        offset=offset,
        current_user=current_user,
    )


@router.post("", response_model=InventoryResponse)
async def create_item(
    body: InventoryCreate,
    current_user: dict = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
):
    return service.create(
        household_id=body.household_id,
        product_name=body.product_name,
        product_category=body.product_category,
        zone_id=body.zone_id,
        quantity=body.quantity,
        unit=body.unit,
        purchase_date=body.purchase_date.isoformat() if body.purchase_date else None,
        expiry_date=body.expiry_date.isoformat() if body.expiry_date else None,
        current_user=current_user,
        low_stock_threshold=body.low_stock_threshold,
    )


@router.get("/{item_id}", response_model=InventoryResponse)
def get_item(
    item_id: str,
    current_user: dict = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
):
    return service.get(item_id=item_id, current_user=current_user)


@router.patch("/{item_id}", response_model=InventoryResponse)
def update_item(
    item_id: str,
    body: InventoryUpdate,
    current_user: dict = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
):
    return service.update(
        item_id=item_id,
        updates=body.model_dump(exclude_none=True),
        current_user=current_user,
    )


@router.post("/{item_id}/consume", response_model=InventoryResponse)
def consume_item(
    item_id: str,
    body: InventoryAction,
    current_user: dict = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
):
    return service.consume(
        item_id=item_id,
        quantity=body.quantity,
        current_user=current_user,
    )


@router.post("/{item_id}/discard", response_model=InventoryResponse)
def discard_item(
    item_id: str,
    current_user: dict = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
):
    return service.discard(item_id=item_id, current_user=current_user)


@router.post("/{item_id}/restock", response_model=InventoryResponse)
def restock_item(
    item_id: str,
    body: InventoryAction,
    current_user: dict = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
):
    return service.restock(
        item_id=item_id,
        quantity=body.quantity,
        current_user=current_user,
    )
