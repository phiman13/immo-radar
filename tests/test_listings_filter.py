from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.db import Listing
from app.web.server import app


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    # Patch the module-level engine/session after env change
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.db as db_mod

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    db_mod.engine = engine
    db_mod.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_mod.Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with db_mod.SessionLocal() as s:
        for i, (price, qm, rooms) in enumerate(
            [
                (500_000, 80.0, 3.0),
                (900_000, 140.0, 5.0),
                (300_000, 60.0, 2.0),
            ]
        ):
            s.add(
                Listing(
                    source_id=f"t{i}",
                    source="test",
                    title=f"T{i}",
                    url=f"http://t{i}",
                    price_eur=price,
                    qm=qm,
                    rooms=rooms,
                    status="neu",
                    first_seen_at=now,
                    last_seen_at=now,
                    is_active=True,
                    dedup_hash=f"hash{i}",
                )
            )
        s.commit()


client = TestClient(app)


def test_price_filter():
    r = client.get("/api/listings/?price_min=400000&price_max=700000")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["price_eur"] == 500_000


def test_qm_filter():
    r = client.get("/api/listings/?qm_min=70&qm_max=150")
    assert r.status_code == 200
    for item in r.json():
        assert 70 <= item["qm"] <= 150


def test_rooms_filter():
    r = client.get("/api/listings/?rooms_min=3")
    assert r.status_code == 200
    for item in r.json():
        assert item["rooms"] >= 3


def test_sort_price_asc():
    r = client.get("/api/listings/?sort=price_asc")
    assert r.status_code == 200
    prices = [item["price_eur"] for item in r.json()]
    assert prices == sorted(prices)


def test_sort_price_desc():
    r = client.get("/api/listings/?sort=price_desc")
    assert r.status_code == 200
    prices = [item["price_eur"] for item in r.json()]
    assert prices == sorted(prices, reverse=True)


def test_sort_ppm_asc():
    r = client.get("/api/listings/?sort=ppm_asc")
    assert r.status_code == 200
    data = r.json()
    ppms = [item["price_per_sqm"] for item in data if item["price_per_sqm"] is not None]
    assert ppms == sorted(ppms)


def test_sort_ppm_desc():
    r = client.get("/api/listings/?sort=ppm_desc")
    assert r.status_code == 200
    data = r.json()
    ppms = [item["price_per_sqm"] for item in data if item["price_per_sqm"] is not None]
    assert ppms == sorted(ppms, reverse=True)
