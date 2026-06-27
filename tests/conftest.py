"""Pytest configuration and shared fixtures (RF-COM-006).

Strategy
--------
The project targets PostgreSQL (UUIDs, JSONB, native ENUMs), so we cannot
use SQLite. We create a dedicated test database `fridge_inventory_test`
on the local Postgres, run all tests against it, and drop it at exit.

If you want to override the connection string, set `TEST_DATABASE_URL`
in the environment or in a `.env.test` file.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Force the test database URL BEFORE importing the app, so every
# `app.core.config.settings.database_url` reads this value.
os.environ.setdefault(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:portugal@localhost:5432/fridge_inventory_test",
)
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
# Disable scheduler + rate limits during tests.
os.environ.setdefault("ENABLE_SCHEDULER", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("GEMINI_API_KEY", "")  # always fallback path

from app.core.config import settings  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402

import app.models  # noqa: E402,F401  - register all models with Base
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    Household,
    HouseholdMember,
    InventoryItem,
    Product,
    Refrigerator,
    User,
    Zone,
)

TEST_DB_NAME = "fridge_inventory_test"
ADMIN_URL = settings.database_url.replace(f"/{TEST_DB_NAME}", "/postgres")


def _ensure_test_database() -> None:
    admin_engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"),
            {"n": TEST_DB_NAME},
        ).first()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_database():
    _ensure_test_database()
    engine = create_engine(settings.database_url)
    # Drop & recreate to start from a known state.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    yield
    # Leave the DB in place for debugging; comment the next line in if you
    # want a clean slate after every test run.
    # engine = create_engine(settings.database_url)
    # Base.metadata.drop_all(bind=engine)
    # engine.dispose()


@pytest.fixture()
def engine(_bootstrap_database):
    eng = create_engine(settings.database_url)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    """Yield a SQLAlchemy session wrapped in a transaction that is rolled
    back at the end of each test, so the database stays clean."""
    connection = engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session):
    """FastAPI test client that uses the per-test transactional session."""

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app = fastapi_app
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# High-level fixtures: a fully provisioned household ready to use in tests.
# ---------------------------------------------------------------------------


@pytest.fixture()
def household_setup(db_session, client):
    """Create alice + a household with one refrigerator and one zone. Returns
    a dict of useful IDs and the access token to use with `client`."""
    alice = User(
        id=uuid.uuid4(),
        email="alice.test@example.com",
        password_hash=hash_password("password123"),
        full_name="Alice Test",
    )
    db_session.add(alice)
    db_session.flush()

    # Use the API path so the test exercises the real router and the data
    # is committed/visible to the TestClient through the override.
    token = _login(db_session, alice.email, "password123")
    res = client.post(
        "/api/households",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Alice's Test Kitchen", "timezone": "UTC"},
    )
    assert res.status_code == 200, res.text
    household = res.json()

    # The create endpoint auto-provisions refrigerators + zones.
    zones = client.get(
        f"/api/zones?household_id={household['id']}",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    refrigerators = client.get(
        f"/api/refrigerators?household_id={household['id']}",
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    return {
        "user_id": str(alice.id),
        "household_id": household["id"],
        "token": token,
        "refrigerator_id": refrigerators[0]["id"] if refrigerators else None,
        "zone_id": zones[0]["id"] if zones else None,
    }


def _login(db_session: Session, email: str, password: str) -> str:
    from app.core.security import create_access_token

    user = db_session.query(User).filter_by(email=email).first()
    assert user is not None
    return create_access_token({"sub": str(user.id)})


@pytest.fixture()
def auth_headers(household_setup):
    return {"Authorization": f"Bearer {household_setup['token']}"}
