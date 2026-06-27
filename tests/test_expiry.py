"""Pareja B — Caducidad: tests for the pure expiry helpers (RF-CAD)."""
from datetime import date, timedelta

from app.services.expiry_service import (
    compute_expiry,
    compute_low_stock_priority,
    resolve_low_stock_threshold,
)


def test_compute_expiry_no_date():
    assert compute_expiry(None) == {"status": None, "days_left": None, "priority_score": 0}


def test_compute_expiry_expired():
    today = date(2026, 6, 26)
    info = compute_expiry(today - timedelta(days=3), today)
    assert info["status"] == "expired"
    assert info["days_left"] == -3
    assert info["priority_score"] == 100


def test_compute_expiry_today():
    today = date(2026, 6, 26)
    info = compute_expiry(today, today)
    assert info["status"] == "today"
    assert info["days_left"] == 0
    assert info["priority_score"] == 90


def test_compute_expiry_urgent_1_to_3_days():
    today = date(2026, 6, 26)
    for d in (1, 2, 3):
        info = compute_expiry(today + timedelta(days=d), today)
        assert info["status"] == "urgent"
        assert 70 <= info["priority_score"] <= 72


def test_compute_expiry_attention_4_to_7_days():
    today = date(2026, 6, 26)
    for d in (4, 5, 6, 7):
        info = compute_expiry(today + timedelta(days=d), today)
        assert info["status"] == "attention"
        assert 40 <= info["priority_score"] <= 60


def test_compute_expiry_safe_beyond_7_days():
    today = date(2026, 6, 26)
    info = compute_expiry(today + timedelta(days=14), today)
    assert info["status"] == "safe"
    assert info["priority_score"] < 40


def test_compute_low_stock_priority_zero_at_or_above_threshold():
    assert compute_low_stock_priority(5, 5) == 0
    assert compute_low_stock_priority(10, 5) == 0


def test_compute_low_stock_priority_critical_at_zero():
    assert compute_low_stock_priority(0, 5) == 100


def test_compute_low_stock_priority_linear_between():
    # 50% of threshold -> 50 priority
    assert compute_low_stock_priority(2.5, 5) == 50


def test_resolve_low_stock_threshold_uses_product_value():
    class FakeProduct:
        low_stock_threshold = 3.5

    assert resolve_low_stock_threshold(FakeProduct()) == 3.5


def test_resolve_low_stock_threshold_uses_default_when_none():
    class FakeProduct:
        low_stock_threshold = None

    assert resolve_low_stock_threshold(FakeProduct(), default=2.0) == 2.0
