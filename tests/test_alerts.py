"""Pareja B — Caducidad: alert scan + dedupe (RF-CAD-004..012)."""
from datetime import date, timedelta

import pytest


def _add_item(client, auth_headers, household_id, zone_id, *, name, days_left):
    today = date.today()
    return client.post(
        "/api/inventory-items",
        headers=auth_headers,
        json={
            "household_id": household_id,
            "product_name": name,
            "zone_id": zone_id,
            "quantity": 1,
            "purchase_date": str(today - timedelta(days=1)),
            "expiry_date": str(today + timedelta(days=days_left)),
        },
    )


def test_scan_creates_alerts_for_expiring_items(client, auth_headers, household_setup):
    h = household_setup
    _add_item(client, auth_headers, h["household_id"], h["zone_id"], name="Cheese", days_left=0)
    _add_item(client, auth_headers, h["household_id"], h["zone_id"], name="Yogurt", days_left=2)
    _add_item(client, auth_headers, h["household_id"], h["zone_id"], name="Butter", days_left=20)  # safe

    res = client.post(
        "/api/alerts/run-preview",
        headers=auth_headers,
        params={"household_id": h["household_id"]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["created"] >= 2  # cheese + yogurt, butter should not alert

    listing = client.get(
        f"/api/alerts?household_id={h['household_id']}",
        headers=auth_headers,
    )
    assert listing.status_code == 200
    alerts = listing.json()
    titles = [a["type"] for a in alerts]
    assert "expiring_today" in titles
    assert "expiring_soon" in titles


def test_scan_dedupes_alerts(client, auth_headers, household_setup):
    """RF-CAD-009: scanning twice should not create duplicate alerts."""
    h = household_setup
    _add_item(client, auth_headers, h["household_id"], h["zone_id"], name="Ham", days_left=1)
    for _ in range(2):
        client.post(
            "/api/alerts/run-preview",
            headers=auth_headers,
            params={"household_id": h["household_id"]},
        )
    listing = client.get(
        f"/api/alerts?household_id={h['household_id']}",
        headers=auth_headers,
    )
    alerts = listing.json()
    # Only one open alert of type expiring_soon for "Ham" should exist.
    ham_alerts = [a for a in alerts if a.get("type") == "expiring_soon"]
    assert len(ham_alerts) == 1


def test_mark_alert_as_read(client, auth_headers, household_setup):
    h = household_setup
    _add_item(client, auth_headers, h["household_id"], h["zone_id"], name="Milk", days_left=1)
    client.post(
        "/api/alerts/run-preview",
        headers=auth_headers,
        params={"household_id": h["household_id"]},
    )
    alerts = client.get(
        f"/api/alerts?household_id={h['household_id']}",
        headers=auth_headers,
    ).json()
    assert alerts
    alert_id = alerts[0]["id"]

    res = client.patch(f"/api/alerts/{alert_id}/read", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["read_at"] is not None


def test_snooze_pushes_due_at_forward(client, auth_headers, household_setup):
    h = household_setup
    _add_item(client, auth_headers, h["household_id"], h["zone_id"], name="Cream", days_left=2)
    client.post(
        "/api/alerts/run-preview",
        headers=auth_headers,
        params={"household_id": h["household_id"]},
    )
    alert_id = client.get(
        f"/api/alerts?household_id={h['household_id']}",
        headers=auth_headers,
    ).json()[0]["id"]

    res = client.post(
        f"/api/alerts/{alert_id}/snooze",
        headers=auth_headers,
        json={"duration_hours": 4},
    )
    assert res.status_code == 200, res.text
    assert res.json()["due_at"] is not None


def test_alerts_require_membership(client, household_setup, db_session):
    # Build a second user that does NOT belong to the household.
    from app.core.security import hash_password, create_access_token
    from app.models import User

    other = User(
        email="outsider@example.com",
        password_hash=hash_password("password123"),
        full_name="Outsider",
    )
    db_session.add(other)
    db_session.flush()
    token = create_access_token({"sub": str(other.id)})
    res = client.get(
        f"/api/alerts?household_id={household_setup['household_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
