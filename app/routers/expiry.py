"""
RF-CAD-014: Expiry timeline / grouped view.

GET /api/expiry?household_id=...&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD

Returns a structured payload that lets the UI render either a grouped
list (expired / today / this_week / this_month / later / no_date) or a
day-by-day calendar strip (when start_date + end_date are supplied).

The grouping reuses the same rules as the rest of the app:
  expired    -> expiry_date < today
  today      -> expiry_date == today
  this_week  -> 1..7 days left
  this_month -> 8..30 days left
  later      -> > 30 days
  no_date    -> expiry_date IS NULL

Each item carries the same `expiry_status`, `days_left`, `priority_score`
and `is_low_stock` already exposed by the inventory endpoint, so the
client can sort/filter without recomputing.
"""
from __future__ import annotations

from datetime import date as date_cls, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.database import get_db
from app.models import InventoryItem
from app.repositories.household_repository import HouseholdRepository
from app.repositories.inventory_repository import InventoryRepository
from app.schemas.expiry import (
    ExpiryBuckets,
    ExpiryItem,
    ExpiryResponse,
    ExpirySummary,
    ExpiryTimelineDay,
)
from app.services.auth_service import get_current_user
from app.services.expiry_service import (
    compute_expiry,
    compute_low_stock_priority,
    resolve_low_stock_threshold,
)
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/expiry", tags=["expiry"])


def _to_expiry_item(item: InventoryItem) -> ExpiryItem:
    """Project an InventoryItem into the slim ExpiryItem shape with all the
    pre-computed fields the client needs to render the timeline."""
    zone = item.zone
    refrigerator = zone.refrigerator if zone else None
    product = item.product
    quantity = float(item.quantity) if item.quantity is not None else 0.0
    threshold = resolve_low_stock_threshold(product)
    is_low_stock = quantity < threshold
    low_stock_priority = compute_low_stock_priority(quantity, threshold) if is_low_stock else 0
    expiry_info = compute_expiry(item.expiry_date)
    return ExpiryItem(
        id=str(item.id),
        product_id=str(item.product_id),
        product_name=product.name if product else "",
        product_category=product.category if product else None,
        image_url=product.image_url if product else None,
        zone_id=str(item.zone_id),
        zone_name=zone.name if zone else "",
        zone_type=zone.type if zone else "",
        refrigerator_name=refrigerator.name if refrigerator else None,
        quantity=quantity,
        unit=item.unit,
        expiry_date=item.expiry_date,
        days_left=expiry_info["days_left"],
        expiry_status=expiry_info["status"],
        priority_score=max(expiry_info["priority_score"], low_stock_priority),
        is_low_stock=is_low_stock,
    )


def _bucket_for(days_left: int | None) -> str:
    if days_left is None:
        return "no_date"
    if days_left < 0:
        return "expired"
    if days_left == 0:
        return "today"
    if days_left <= 7:
        return "this_week"
    if days_left <= 30:
        return "this_month"
    return "later"


@router.get("", response_model=ExpiryResponse)
def get_expiry(
    household_id: Annotated[str, Query(...)],
    start_date: Annotated[date_cls | None, Query(description="Include timeline from this date (inclusive)")] = None,
    end_date: Annotated[date_cls | None, Query(description="Include timeline up to this date (inclusive)")] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Membership check (same as everywhere else)
    hh_repo = HouseholdRepository(db)
    members = hh_repo.get_members(household_id)
    if not any(str(m.user_id) == current_user["id"] for m, _ in members):
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this household",
        )

    items = InventoryRepository(db).list_by_household(household_id, status="active")

    today = date_cls.today()
    buckets: dict[str, list[ExpiryItem]] = {
        "expired": [],
        "today": [],
        "this_week": [],
        "this_month": [],
        "later": [],
        "no_date": [],
    }
    for item in items:
        proj = _to_expiry_item(item)
        key = _bucket_for(proj.days_left)
        buckets[key].append(proj)

    # Stable order inside each bucket: most urgent first
    for key in buckets:
        buckets[key].sort(key=lambda it: (-it.priority_score, it.days_left if it.days_left is not None else 10**9))

    summary = ExpirySummary(
        expired=len(buckets["expired"]),
        today=len(buckets["today"]),
        this_week=len(buckets["this_week"]),
        this_month=len(buckets["this_month"]),
        later=len(buckets["later"]),
        no_date=len(buckets["no_date"]),
        total=sum(len(v) for v in buckets.values()),
    )

    # Optional calendar/timeline: only when both bounds are given
    timeline: list[ExpiryTimelineDay] = []
    if start_date and end_date and end_date >= start_date:
        by_day: dict[date_cls, list[ExpiryItem]] = {}
        for key in ("expired", "today", "this_week", "this_month", "later"):
            for proj in buckets[key]:
                if proj.expiry_date is None:
                    continue
                # include expired items that fell into the window too
                if start_date <= proj.expiry_date <= end_date:
                    by_day.setdefault(proj.expiry_date, []).append(proj)
        cursor = start_date
        while cursor <= end_date:
            day_items = by_day.get(cursor, [])
            day_items.sort(key=lambda it: -it.priority_score)
            timeline.append(
                ExpiryTimelineDay(date=cursor, items=day_items, count=len(day_items))
            )
            from datetime import timedelta
            cursor = cursor + timedelta(days=1)

    return ExpiryResponse(
        household_id=household_id,
        generated_at=datetime.now(timezone.utc),
        range_start=start_date,
        range_end=end_date,
        summary=summary,
        buckets=ExpiryBuckets(**buckets),
        timeline=timeline,
    )
