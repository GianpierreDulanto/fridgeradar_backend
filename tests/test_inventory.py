"""Pareja A — Inventario: CRUD + validation (RF-INV, RF-INV-017)."""
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import InventoryItem, Product


def _create_product(db_session: Session, household_id: str, zone_id: str, *, name: str = "Whole Milk", category: str = "Dairy") -> str:
    p = Product(household_id=household_id, name=name, category=category, default_unit="lt")
    db_session.add(p)
    db_session.flush()
    return str(p.id)


def test_create_inventory_item_happy_path(client, auth_headers, household_setup, db_session):
    h = household_setup
    product_id = _create_product(db_session, h["household_id"], h["zone_id"])
    res = client.post(
        "/api/inventory-items",
        headers=auth_headers,
        json={
            "household_id": h["household_id"],
            "product_name": "Whole Milk",
            "product_category": "Dairy",
            "zone_id": h["zone_id"],
            "quantity": 2,
            "unit": "lt",
            "purchase_date": str(date.today()),
            "expiry_date": str(date.today() + timedelta(days=5)),
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["product_name"] == "Whole Milk"
    assert body["expiry_status"] == "attention"
    assert body["days_left"] == 5


def test_create_inventory_item_rejects_negative_quantity(client, auth_headers, household_setup, db_session):
    h = household_setup
    res = client.post(
        "/api/inventory-items",
        headers=auth_headers,
        json={
            "household_id": h["household_id"],
            "product_name": "Eggs",
            "zone_id": h["zone_id"],
            "quantity": -1,
        },
    )
    assert res.status_code in (400, 422)


def test_create_inventory_item_rejects_expiry_before_purchase(client, auth_headers, household_setup, db_session):
    """RF-INV-017: expiry_date must be on or after purchase_date."""
    h = household_setup
    res = client.post(
        "/api/inventory-items",
        headers=auth_headers,
        json={
            "household_id": h["household_id"],
            "product_name": "Yogurt",
            "zone_id": h["zone_id"],
            "quantity": 1,
            "purchase_date": str(date.today()),
            "expiry_date": str(date.today() - timedelta(days=1)),
        },
    )
    assert res.status_code in (400, 422), res.text
    assert "expiry_date" in res.text.lower()


def test_create_inventory_item_allows_expiry_equal_to_purchase(client, auth_headers, household_setup, db_session):
    h = household_setup
    today = date.today()
    res = client.post(
        "/api/inventory-items",
        headers=auth_headers,
        json={
            "household_id": h["household_id"],
            "product_name": "Bread",
            "zone_id": h["zone_id"],
            "quantity": 1,
            "purchase_date": str(today),
            "expiry_date": str(today),
        },
    )
    assert res.status_code == 200, res.text


def test_list_inventory_items_pagination(client, auth_headers, household_setup, db_session):
    h = household_setup
    # Seed 5 items.
    for i in range(5):
        client.post(
            "/api/inventory-items",
            headers=auth_headers,
            json={
                "household_id": h["household_id"],
                "product_name": f"Item {i}",
                "zone_id": h["zone_id"],
                "quantity": 1,
            },
        )
    res = client.get(
        f"/api/inventory-items?household_id={h['household_id']}&limit=2&offset=0",
        headers=auth_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 0


def test_consume_decrements_quantity_and_marks_consumed(client, auth_headers, household_setup, db_session):
    h = household_setup
    res = client.post(
        "/api/inventory-items",
        headers=auth_headers,
        json={
            "household_id": h["household_id"],
            "product_name": "Apples",
            "zone_id": h["zone_id"],
            "quantity": 3,
        },
    )
    item_id = res.json()["id"]

    res = client.post(
        f"/api/inventory-items/{item_id}/consume",
        headers=auth_headers,
        json={"quantity": 1},
    )
    assert res.status_code == 200, res.text
    assert res.json()["quantity"] == 2

    # Drain it
    res = client.post(
        f"/api/inventory-items/{item_id}/consume",
        headers=auth_headers,
        json={"quantity": 2},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "consumed"


def test_discard_marks_item_discarded(client, auth_headers, household_setup, db_session):
    h = household_setup
    res = client.post(
        "/api/inventory-items",
        headers=auth_headers,
        json={
            "household_id": h["household_id"],
            "product_name": "Lettuce",
            "zone_id": h["zone_id"],
            "quantity": 1,
        },
    )
    item_id = res.json()["id"]
    res = client.post(f"/api/inventory-items/{item_id}/discard", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "discarded"
