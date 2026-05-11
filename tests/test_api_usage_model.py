import os

os.environ.setdefault("DB_PATH", "/tmp/immo_test_usage.db")

from datetime import datetime, timedelta

import pytest


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db)
    import importlib

    import app.config
    import app.db

    importlib.reload(app.config)
    importlib.reload(app.db)

    from app.db import init_db  # fresh import after reload

    init_db()
    yield


def test_api_usage_insert():
    from app.db import ApiUsage, SessionLocal  # fresh imports after fixture reload

    with SessionLocal() as s:
        row = ApiUsage(
            ts=datetime.utcnow(),
            model="claude-haiku-4-5-20251001",
            input_tokens=500,
            output_tokens=80,
            purpose="enrichment",
        )
        s.add(row)
        s.commit()
        assert row.id is not None


def test_api_usage_query_by_ts():
    from app.db import ApiUsage, SessionLocal  # fresh imports after fixture reload

    now = datetime.utcnow()
    with SessionLocal() as s:
        s.add(
            ApiUsage(
                ts=now,
                model="m",
                input_tokens=100,
                output_tokens=10,
                purpose="analyze",
            )
        )
        s.add(
            ApiUsage(
                ts=now - timedelta(days=2),
                model="m",
                input_tokens=200,
                output_tokens=20,
                purpose="enrichment",
            )
        )
        s.commit()

    cutoff = now - timedelta(hours=25)
    with SessionLocal() as s:
        recent = s.query(ApiUsage).filter(ApiUsage.ts >= cutoff).all()
    assert len(recent) == 1
    assert recent[0].purpose == "analyze"
