"""Shared pytest fixtures for immo-radar tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.db import Base


@pytest.fixture()
def test_db(monkeypatch, tmp_path):
    """Isolated SQLite DB per test — patches db_module globals.

    Consistent with the per-test session fixtures in test_db_models.py and
    test_settings_service.py, but exposed at conftest level so it can be
    shared across modules (e.g. the client fixture below).
    """
    test_engine = create_engine(
        f"sqlite:///{tmp_path}/test.db",
        connect_args={"check_same_thread": False},
        echo=False,
        future=True,
    )
    Base.metadata.create_all(test_engine)
    TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)

    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSessionLocal)

    yield test_engine

    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture()
def client(test_db):
    """FastAPI TestClient wired to the test DB.

    - Patches db_module globals before the app is imported into the client.
    - Overrides require_auth so tests don't need Basic-Auth headers.
    - Uses TestClient as context manager to trigger startup/shutdown events.
    """
    from app.web.auth import require_auth
    from app.web.server import app

    app.dependency_overrides[require_auth] = lambda: "testuser"

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()
