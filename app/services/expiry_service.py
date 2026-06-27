"""
Pure functions for computing expiry status, days_left, and priority_score.

Single source of truth for caducidad rules. Consumed by:
  - inventory_service._to_response  (computes fields for InventoryResponse)
  - alert_service.scan_and_generate  (decides whether to emit an alert)
  - alert_service.snooze            (decide when due_at should move to)
  - workers/scheduler.py            (cron-driven scan)
  - scripts/verify_db.py            (debug/test)
  - frontend useExpiryStatus hook   (eventually)

The functions are deliberately stateless so they can be tested in isolation
and reused in any context (HTTP, scheduler, CLI).
"""

from datetime import date, timedelta
from typing import NamedTuple

DEFAULT_LOW_STOCK_THRESHOLD = 1.0


class ExpiryInfo(NamedTuple):
    status: str | None
    days_left: int | None
    priority_score: int


def compute_expiry(expiry_date: date | None, today: date | None = None) -> dict:
    """Compute expiry info for an inventory item.

    status:
      None                 -> no expiry_date set
      "expired"            -> expiry_date < today
      "today"              -> expiry_date == today
      "urgent"             -> 1..3 days left
      "attention"          -> 4..7 days left
      "safe"               -> >7 days left

    priority_score: 0..100, higher = more urgent. Designed so that sorting
    inventory_items by priority_score desc surfaces the most urgent first.
      expired   -> 100
      today     -> 90
      1..3 days -> 70..72
      4..7 days -> 40..60
      8..14 d   -> 20..34
      15..30 d  -> 0..9
      >30 d     -> 0
    """
    if expiry_date is None:
        return ExpiryInfo(None, None, 0)._asdict()

    if today is None:
        today = date.today()

    diff = (expiry_date - today).days

    if diff < 0:
        return ExpiryInfo("expired", diff, 100)._asdict()
    if diff == 0:
        return ExpiryInfo("today", 0, 90)._asdict()
    if diff <= 3:
        return ExpiryInfo("urgent", diff, 70 + (3 - diff))._asdict()
    if diff <= 7:
        return ExpiryInfo("attention", diff, 40 + (7 - diff) * 5)._asdict()
    if diff <= 14:
        return ExpiryInfo("safe", diff, 20 + (14 - diff) * 2)._asdict()
    if diff <= 30:
        return ExpiryInfo("safe", diff, max(0, 10 - (diff - 14) // 2))._asdict()
    return ExpiryInfo("safe", diff, 0)._asdict()


def compute_low_stock_priority(quantity: float | None, threshold: float | None) -> int:
    """Priority score for low_stock. 100 if qty=0, 0 if qty >= threshold.

    Linear interpolation in between. Returns 0 if either value is None/0
    (caller should treat None as "no threshold configured").
    """
    if quantity is None or threshold is None or threshold <= 0:
        return 0
    qty = float(quantity)
    if qty <= 0:
        return 100
    if qty >= threshold:
        return 0
    return int(100 * (1 - qty / threshold))


def resolve_low_stock_threshold(product, default: float = DEFAULT_LOW_STOCK_THRESHOLD) -> float:
    """Return the product's low_stock_threshold if set, otherwise the default."""
    if product is not None and getattr(product, "low_stock_threshold", None) is not None:
        return float(product.low_stock_threshold)
    return default


def next_due_at(current_due_at, duration_hours: int) -> "datetime | None":
    """Compute the new due_at for a snoozed alert.

    If the alert has a due_at, move it forward by duration_hours. If it has
    no due_at (e.g. low_stock), use now() + duration_hours.
    """
    from datetime import datetime, timezone

    base = current_due_at or datetime.now(timezone.utc)
    return base + timedelta(hours=duration_hours)


EXPIRY_STATUSES = ("expired", "today", "urgent", "attention", "safe")
