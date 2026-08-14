"""Tests für app.scheduler — insbesondere, dass DB-persistente
Intervall-Settings tatsächlich wirken.

Regression: build_scheduler() nahm die Poll-/Enrich-Intervalle bisher aus
app.config.settings (statisch, .env-Wert bei Prozessstart) statt aus den
DB-persistenten Dashboard-Settings -- eine Intervalländerung im Dashboard
hatte dadurch NULL Effekt bis zum nächsten Container-Neustart, obwohl
CLAUDE.md genau das Gegenteil dokumentiert ("Interval ... aus DB, ändert
sich ohne Container-Restart"). Real bemerkt 2026-08-14: die DB stand auf
poll_interval_minutes=10 (ein liegen gebliebener Default), der laufende
Scheduler pollte aber tatsächlich alle 10 Minuten aus dem .env-Wert --
eine anschliessende DB-Änderung auf 720 hätte am laufenden Prozess nichts
geändert."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.db import Base
from app.scheduler import build_scheduler, reconcile_intervals
from app.settings_service import set_setting


@pytest.fixture()
def session(monkeypatch, tmp_path):
    """Isolated SQLite DB per test — patches db_module globals."""
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


def _job_interval_minutes(scheduler: AsyncIOScheduler, job_id: str) -> float:
    return scheduler.get_job(job_id).trigger.interval.total_seconds() / 60


def test_build_scheduler_uses_db_persisted_poll_interval(session):
    """Scheduler wird nie gestartet (kein .start()) -- add_job() legt Jobs
    und deren next_run_time bereits auf einem ruhenden Scheduler an, ganz
    ohne echten Hintergrund-Thread. shutdown() ist deshalb weder nötig noch
    zulässig (wirft SchedulerNotRunningError auf einem nie gestarteten
    Scheduler)."""
    set_setting("poll_interval_minutes", 42)
    set_setting("detail_fetch_interval_minutes", 17)

    scheduler = build_scheduler()
    assert _job_interval_minutes(scheduler, "poll_and_notify") == 42
    assert _job_interval_minutes(scheduler, "enrich_pending") == 17


def test_reconcile_intervals_reschedules_job_when_db_value_changed(session):
    set_setting("poll_interval_minutes", 10)
    scheduler = build_scheduler()
    assert _job_interval_minutes(scheduler, "poll_and_notify") == 10

    set_setting("poll_interval_minutes", 720)
    reconcile_intervals(scheduler)

    assert _job_interval_minutes(scheduler, "poll_and_notify") == 720


def test_reconcile_intervals_leaves_job_untouched_when_db_value_unchanged(session, monkeypatch):
    """Kein Reschedule bei unveränderten Werten -- sonst würde der
    1-Minuten-Watchdog jeden Job permanent neu starten und damit dessen
    eigentliches Intervall nie erreichen lassen."""
    set_setting("poll_interval_minutes", 720)
    scheduler = build_scheduler()

    reschedule_spy = MagicMock(wraps=scheduler.reschedule_job)
    monkeypatch.setattr(scheduler, "reschedule_job", reschedule_spy)

    reconcile_intervals(scheduler)

    reschedule_spy.assert_not_called()
