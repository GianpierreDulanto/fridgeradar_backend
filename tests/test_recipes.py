"""Pareja C — Recetas + IA: filters, pagination, daily, add-to-shopping (RF-REC)."""
from datetime import date, timedelta

import pytest

from app.models import Product


def _seed_inventory(client, auth_headers, h_id, zone_id, items):
    """items: list of (name, category, days_left_or_None)"""
    today = date.today()
    for name, category, days in items:
        if days is None:
            payload = {
                "household_id": h_id,
                "product_name": name,
                "product_category": category,
                "zone_id": zone_id,
                "quantity": 2,
            }
        else:
            payload = {
                "household_id": h_id,
                "product_name": name,
                "product_category": category,
                "zone_id": zone_id,
                "quantity": 2,
                "purchase_date": str(today - timedelta(days=1)),
                "expiry_date": str(today + timedelta(days=days)),
            }
        client.post("/api/inventory-items", headers=auth_headers, json=payload)


def test_suggest_fallback_with_categories_present(client, auth_headers, household_setup):
    h = household_setup
    _seed_inventory(
        client,
        auth_headers,
        h["household_id"],
        h["zone_id"],
        [
            ("Leche Entera",     "Lácteos",   5),
            ("Arroz Blanco",     "Granos",    30),
            ("Espinaca Fresca",  "Verduras",  2),
            ("Bistec de Res",    "Carne",     3),
        ],
    )
    res = client.get(
        f"/api/recipes/suggest?household_id={h['household_id']}",
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] in ("ai", "fallback")
    assert body["total"] >= 1
    assert "limit" in body and "offset" in body
    for r in body["recipes"]:
        assert 0 <= r["match_pct"] <= 100
        assert 0 <= r["waste_rescue_score"] <= 100
        assert r["priority_score"] >= 0


def test_suggest_filters_by_max_time(client, auth_headers, household_setup):
    h = household_setup
    _seed_inventory(
        client,
        auth_headers,
        h["household_id"],
        h["zone_id"],
        [("Leche Entera", "Lácteos", 5), ("Arroz Blanco", "Granos", 30)],
    )
    res = client.get(
        f"/api/recipes/suggest?household_id={h['household_id']}&max_time=10",
        headers=auth_headers,
    )
    assert res.status_code == 200
    for r in res.json()["recipes"]:
        # Every returned recipe must respect the max_time filter, OR have
        # max_time_minutes == None (only possible if a Gemini recipe came back
        # without that field — with no key we always use fallback which all
        # have the field).
        assert r["max_time_minutes"] is None or r["max_time_minutes"] <= 10


def test_suggest_filters_by_difficulty(client, auth_headers, household_setup):
    h = household_setup
    _seed_inventory(
        client,
        auth_headers,
        h["household_id"],
        h["zone_id"],
        [("Leche Entera", "Lácteos", 5), ("Arroz Blanco", "Granos", 30)],
    )
    res = client.get(
        f"/api/recipes/suggest?household_id={h['household_id']}&difficulty=easy",
        headers=auth_headers,
    )
    assert res.status_code == 200
    for r in res.json()["recipes"]:
        assert r["difficulty"] == "easy"


def test_suggest_filters_by_dietary_all_required(client, auth_headers, household_setup):
    h = household_setup
    _seed_inventory(
        client,
        auth_headers,
        h["household_id"],
        h["zone_id"],
        [("Red Apples", "Fruits", 5), ("Bananas", "Fruits", 5)],
    )
    res = client.get(
        f"/api/recipes/suggest?household_id={h['household_id']}&dietary=vegan&dietary=gluten_free",
        headers=auth_headers,
    )
    assert res.status_code == 200
    for r in res.json()["recipes"]:
        assert "vegan" in r["dietary"]
        assert "gluten_free" in r["dietary"]


def test_suggest_rejects_invalid_difficulty(client, auth_headers, household_setup):
    h = household_setup
    res = client.get(
        f"/api/recipes/suggest?household_id={h['household_id']}&difficulty=impossible",
        headers=auth_headers,
    )
    assert res.status_code == 400


def test_suggest_pagination_limit_and_offset(client, auth_headers, household_setup):
    h = household_setup
    _seed_inventory(
        client,
        auth_headers,
        h["household_id"],
        h["zone_id"],
        [
            ("Leche Entera", "Lácteos", 5),
            ("Arroz Blanco", "Granos", 30),
            ("Espinaca Fresca", "Verduras", 2),
            ("Bistec de Res", "Carne", 3),
            ("Red Apples", "Fruits", 5),
        ],
    )
    page1 = client.get(
        f"/api/recipes/suggest?household_id={h['household_id']}&limit=2&offset=0",
        headers=auth_headers,
    ).json()
    page2 = client.get(
        f"/api/recipes/suggest?household_id={h['household_id']}&limit=2&offset=2",
        headers=auth_headers,
    ).json()
    assert len(page1["recipes"]) <= 2
    assert page1["total"] == page2["total"]
    assert page1["offset"] == 0
    assert page2["offset"] == 2
    # Recipes on page1 and page2 must not overlap.
    page1_ids = {r["id"] for r in page1["recipes"]}
    page2_ids = {r["id"] for r in page2["recipes"]}
    assert page1_ids.isdisjoint(page2_ids)


def test_daily_returns_a_recipe(client, auth_headers, household_setup):
    h = household_setup
    _seed_inventory(
        client,
        auth_headers,
        h["household_id"],
        h["zone_id"],
        [("Leche Entera", "Lácteos", 5), ("Arroz Blanco", "Granos", 30)],
    )
    res = client.get(
        f"/api/recipes/daily?household_id={h['household_id']}",
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["name"]


def test_daily_is_deterministic_for_same_day(client, auth_headers, household_setup):
    h = household_setup
    _seed_inventory(
        client,
        auth_headers,
        h["household_id"],
        h["zone_id"],
        [("Leche Entera", "Lácteos", 5), ("Arroz Blanco", "Granos", 30)],
    )
    a = client.get(
        f"/api/recipes/daily?household_id={h['household_id']}",
        headers=auth_headers,
    ).json()
    b = client.get(
        f"/api/recipes/daily?household_id={h['household_id']}",
        headers=auth_headers,
    ).json()
    assert a["name"] == b["name"]


def test_missing_ingredients_for_recipe(client, auth_headers, household_setup):
    h = household_setup
    # Solo tenemos leche — el bowl de arroz pide arroz, espinaca y manzana.
    _seed_inventory(
        client,
        auth_headers,
        h["household_id"],
        h["zone_id"],
        [("Leche Entera", "Lácteos", 5)],
    )
    res = client.get(
        f"/api/recipes/Bowl%20de%20Arroz%20con%20Verduras/missing?household_id={h['household_id']}",
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    names = {i["name"] for i in body}
    assert "Arroz Blanco" in names
    assert "Espinaca Fresca" in names
    assert "Manzanas Rojas" in names


def test_add_recipe_missing_to_shopping_list(client, auth_headers, household_setup):
    """RF-REC-015."""
    h = household_setup
    _seed_inventory(
        client,
        auth_headers,
        h["household_id"],
        h["zone_id"],
        [("Leche Entera", "Lácteos", 5)],
    )
    res = client.post(
        "/api/shopping-lists/from-recipe",
        headers=auth_headers,
        json={"household_id": h["household_id"], "recipe_name": "Bowl de Arroz con Verduras"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["recipe_name"] == "Bowl de Arroz con Verduras"
    assert body["added"] >= 1
    for it in body["items"]:
        assert it["source"] == "recipe:Bowl de Arroz con Verduras"

    # Calling again should not create duplicates.
    res2 = client.post(
        "/api/shopping-lists/from-recipe",
        headers=auth_headers,
        json={"household_id": h["household_id"], "recipe_name": "Bowl de Arroz con Verduras"},
    )
    assert res2.json()["added"] == 0
    assert res2.json()["skipped"] >= 1


def test_cook_recipe_deducts_inventory(client, auth_headers, household_setup):
    h = household_setup
    _seed_inventory(
        client,
        auth_headers,
        h["household_id"],
        h["zone_id"],
        [("Leche Entera", "Lácteos", 5)],
    )
    res = client.post(
        "/api/recipes/cook",
        headers=auth_headers,
        json={
            "household_id": h["household_id"],
            "recipe_name": "Tazón de Cereal",
            "consume_ingredients": [
                {"name": "Leche Entera", "quantity": 0.25, "unit": "lt", "is_have": True}
            ],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["consumed"][0]["product_name"] == "Leche Entera"
