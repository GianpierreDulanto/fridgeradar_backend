"""Schemas for RF-CAD-014: /expiry grouped view + timeline."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


ExpiryBucketKey = Literal["expired", "today", "this_week", "this_month", "later", "no_date"]


class ExpiryItem(BaseModel):
    """Minimal projection of an inventory item for the expiry views."""
    id: str
    product_id: str
    product_name: str
    product_category: str | None = None
    image_url: str | None = None
    zone_id: str
    zone_name: str
    zone_type: str
    refrigerator_name: str | None = None
    quantity: float
    unit: str | None = None
    expiry_date: date | None = None
    days_left: int | None = None
    expiry_status: str | None = None
    priority_score: float = 0
    is_low_stock: bool = False

    class Config:
        from_attributes = True


class ExpirySummary(BaseModel):
    expired: int = 0
    today: int = 0
    this_week: int = 0       # 1-7 days
    this_month: int = 0      # 8-30 days
    later: int = 0           # > 30 days
    no_date: int = 0
    total: int = 0


class ExpiryBuckets(BaseModel):
    expired: list[ExpiryItem] = []
    today: list[ExpiryItem] = []
    this_week: list[ExpiryItem] = []
    this_month: list[ExpiryItem] = []
    later: list[ExpiryItem] = []
    no_date: list[ExpiryItem] = []


class ExpiryTimelineDay(BaseModel):
    date: date
    items: list[ExpiryItem]
    count: int


class ExpiryResponse(BaseModel):
    household_id: str
    generated_at: datetime
    range_start: date | None = None
    range_end: date | None = None
    summary: ExpirySummary
    buckets: ExpiryBuckets
    timeline: list[ExpiryTimelineDay] = Field(
        default_factory=list,
        description="Only populated when ?start_date and ?end_date are provided.",
    )
