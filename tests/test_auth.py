"""RF-AUT + RF-HOG happy paths: registration, login, and household creation."""
import uuid

import pytest


def test_register_login_me_flow(client):
    # Disable the auth rate limit for this test (conftest already turned it
    # off, but be explicit).
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    res = client.post(
        "/api/auth/register",
        json={"email": email, "password": "password123", "full_name": "Tester"},
    )
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    assert token

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email


def test_register_rejects_duplicate_email(client):
    email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
    payload = {"email": email, "password": "password123", "full_name": "Dup"}
    assert client.post("/api/auth/register", json=payload).status_code == 200
    res = client.post("/api/auth/register", json=payload)
    assert res.status_code == 409


def test_register_rejects_short_password(client):
    res = client.post(
        "/api/auth/register",
        json={"email": f"x-{uuid.uuid4().hex[:6]}@example.com", "password": "short", "full_name": "X"},
    )
    # Validation is at Pydantic level (min_length=8 in auth schema)
    assert res.status_code in (400, 422)


def test_login_with_wrong_password_returns_401(client):
    email = f"login-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "password123", "full_name": "L"},
    )
    res = client.post("/api/auth/login", json={"email": email, "password": "WRONG"})
    assert res.status_code == 401


def test_create_household_auto_provisions_refrigerator_and_zone(household_setup):
    # The fixture already creates the household + 1 refrigerator + 1 zone.
    assert household_setup["refrigerator_id"]
    assert household_setup["zone_id"]


def test_create_household_requires_auth(client):
    res = client.post("/api/households", json={"name": "X", "timezone": "UTC"})
    assert res.status_code == 401
