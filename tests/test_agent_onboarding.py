"""Tests für app.agent_onboarding — bildet die klassifizierte Kaskadenstufe
auf das extraction-Schema ab und schreibt sie auf die Agent-Zeile."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.agent_onboarding import onboard_agent
from app.db import Agent, Base


@pytest.fixture()
def session(monkeypatch, tmp_path):
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


def _make_agent(session, **overrides) -> int:
    defaults = dict(name="Test Makler", verified_domain="x.de")
    defaults.update(overrides)
    with session() as s:
        agent = Agent(**defaults)
        s.add(agent)
        s.commit()
        return agent.id


@pytest.mark.asyncio
async def test_onboard_agent_sets_auto_harvested_for_vendor_stage(session, monkeypatch):
    agent_id = _make_agent(session)
    fake_row = {
        "reachable": True,
        "robots_allows_root": True,
        "vendors": ["onoffice"],
        "listing_url": "https://x.de/immobilien/",
        "structured": {"jsonld_types": []},
        "sitemap_object_urls": 0,
        "detail_links": 0,
        "signals": {"prices": 0},
    }
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "auto-harvested"
        assert agent.extraction == {"method": "vendor:onoffice", "vendor": "onoffice"}
        assert agent.listing_url == "https://x.de/immobilien/"
        assert agent.last_checked is not None


@pytest.mark.asyncio
async def test_onboard_agent_resets_consecutive_empty_runs_on_reactivation(session, monkeypatch):
    """Auflage 2 (finale Whole-Branch-Review Phase 2c): eine Reaktivierung
    (z.B. via scripts/onboard_agents.py --agent-id) setzt coverage_status
    zurück auf auto-harvested, muss aber auch consecutive_empty_runs
    zurücksetzen -- sonst kippt ein reaktivierter Agent mit vorherigem
    Zählerstand nach einem einzigen weiteren Fehlschlag sofort wieder auf
    needs-manual-watch zurück, und der dokumentierte Reparaturweg ist
    wirkungslos."""
    agent_id = _make_agent(
        session,
        coverage_status="needs-manual-watch",
        consecutive_empty_runs=2,
    )
    fake_row = {
        "reachable": True,
        "robots_allows_root": True,
        "vendors": ["onoffice"],
        "listing_url": "https://x.de/immobilien/",
        "structured": {"jsonld_types": []},
        "sitemap_object_urls": 0,
        "detail_links": 0,
        "signals": {"prices": 0},
    }
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "auto-harvested"
        assert agent.consecutive_empty_runs == 0


@pytest.mark.asyncio
async def test_onboard_agent_sets_needs_manual_watch_for_js_shell(session, monkeypatch):
    agent_id = _make_agent(session)
    fake_row = {
        "reachable": True,
        "robots_allows_root": True,
        "vendors": [],
        "structured": {"jsonld_types": []},
        "sitemap_object_urls": 0,
        "detail_links": 0,
        "signals": {"prices": 0},
    }
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "needs-manual-watch"
        assert "JS-Shell" in agent.coverage_reason


@pytest.mark.asyncio
async def test_onboard_agent_sets_robots_disallowed(session, monkeypatch):
    agent_id = _make_agent(session)
    fake_row = {"reachable": True, "robots_allows_root": False}
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "robots-disallowed"
        assert agent.robots_status == "disallowed"


@pytest.mark.asyncio
async def test_onboard_agent_sets_bot_blocked_with_needs_browser_hint(session, monkeypatch):
    agent_id = _make_agent(session)
    fake_row = {"reachable": False, "blocked": True}
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "bot-blocked"
        assert agent.extraction == {"needs_browser": True}


@pytest.mark.asyncio
async def test_onboard_agent_sets_sitemap_url_for_sitemap_objekte_stage(session, monkeypatch):
    """Fix 1: extraction['sitemap_url'] muss die tatsächliche Sitemap-URL
    tragen, nicht die erste Objekt-Beispiel-URL aus sitemap_object_sample."""
    agent_id = _make_agent(session)
    fake_row = {
        "reachable": True,
        "robots_allows_root": True,
        "vendors": [],
        "listing_url": "https://x.de/immobilien/",
        "structured": {"jsonld_types": []},
        "sitemap_object_urls": 3,
        "sitemap_url": "https://x.de/sitemap.xml",
        "sitemap_object_sample": [
            "https://x.de/immobilien/haus-poecking-mit-garten",
            "https://x.de/immobilien/villa-am-see-tutzing",
        ],
        "detail_links": 0,
        "signals": {"prices": 0},
    }
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "auto-harvested"
        assert agent.extraction == {
            "method": "sitemap_objekte",
            "sitemap_url": "https://x.de/sitemap.xml",
        }
        assert agent.listing_url == "https://x.de/immobilien/"


@pytest.mark.asyncio
async def test_onboard_agent_vendor_stage_without_listing_url_needs_manual_watch(session, monkeypatch):
    """Fix 2a: ein Vendor-Signal allein von der Startseite (keine gefundene
    Angebotsseite) darf nicht als auto-harvested landen -- sonst überspringt
    agents_adapter.fetch() diesen Agent für immer, während er im Dashboard
    als abgedeckt zählt."""
    agent_id = _make_agent(session)
    fake_row = {
        "reachable": True,
        "robots_allows_root": True,
        "vendors": ["onoffice"],
        "listing_url": None,
        "structured": {"jsonld_types": []},
        "sitemap_object_urls": 0,
        "detail_links": 0,
        "signals": {"prices": 0},
    }
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "needs-manual-watch"
        assert agent.listing_url is None
        assert agent.extraction == {}
        assert "listing_url" in agent.coverage_reason or "Angebotsseite" in agent.coverage_reason


@pytest.mark.asyncio
async def test_onboard_agent_preserves_existing_listing_url_when_reprobe_finds_none(session, monkeypatch):
    """Fix 2b: Re-Onboarding (z.B. via scripts/onboard_agents.py --agent-id)
    darf eine zuvor gute listing_url nicht nullen, nur weil der aktuelle
    Probe (Homepage-Nav geändert?) diesmal keine Angebotsseite findet."""
    agent_id = _make_agent(
        session,
        listing_url="https://x.de/immobilien/",
        coverage_status="auto-harvested",
    )
    fake_row = {
        "reachable": True,
        "robots_allows_root": True,
        "vendors": ["onoffice"],
        "listing_url": None,
        "structured": {"jsonld_types": []},
        "sitemap_object_urls": 0,
        "detail_links": 0,
        "signals": {"prices": 0},
    }
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.listing_url == "https://x.de/immobilien/"
        assert agent.coverage_status == "auto-harvested"
        assert agent.extraction == {"method": "vendor:onoffice", "vendor": "onoffice"}


@pytest.mark.asyncio
async def test_onboard_agent_terminal_stage_extraction_is_not_shared_mutable_dict(session, monkeypatch):
    """Fix 3: agent.extraction für terminale Stufen (z.B. bot-blocked) muss
    eine eigene Kopie sein, nicht dasselbe Dict-Objekt wie das Modul-Konstante
    _TERMINAL_STAGES -- sonst korrumpiert eine künftige In-Place-Mutation den
    ganzen Prozess."""
    from app.agent_onboarding import _TERMINAL_STAGES

    agent_id = _make_agent(session)
    fake_row = {"reachable": False, "blocked": True}
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.extraction == {"needs_browser": True}
        assert agent.extraction is not _TERMINAL_STAGES["blocked (braucht Browser)"][2]


def _resp(status_code=200, text="", url=None):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    r.url = url or "https://vendor-only.de/"
    r.headers = {}
    return r


def _routed_client(routes: dict[str, MagicMock], default=None):
    """Gleiches URL-Routing-Muster wie tests/test_agent_probe.py -- hier
    lokal dupliziert, damit dieses Testfile eigenständig bleibt."""
    client = AsyncMock()

    async def _get(url, *a, **kw):
        if url in routes:
            return routes[url]
        return default or _resp(status_code=404)

    client.get = AsyncMock(side_effect=_get)
    return client


@pytest.mark.asyncio
async def test_onboard_agent_real_probe_vendor_only_homepage_no_listing_page(session):
    """Fix 6: Integrationstest über die echte Schnittstellen-Grenze --
    echtes probe_agent() + echtes onboard_agent(), HTTP über den
    _routed_client-Router gemockt (kein handgeschriebenes probe_agent-Fixture-
    Dict). Homepage trägt ein Vendor-Fingerprint, aber kein <a>-Link erfüllt
    LISTING_HINTS -- find_listing_url() findet also keine Angebotsseite.

    Regressionswächter für Fix 2: das muss als needs-manual-watch mit
    listing_url=None landen, NICHT als auto-harvested mit listing_url=None
    (sonst überspringt agents_adapter.fetch() den Agent für immer, während er
    im Dashboard als abgedeckt zählt). Ein vor Fix 1/2 geschriebener Test mit
    handgestricktem probe_agent-Mock hätte genau diese Lücke nicht gefunden,
    weil solche Fixtures üblicherweise eine bequeme listing_url mitbringen."""
    agent_id = _make_agent(session, verified_domain="vendor-only.de")
    home_html = """
    <html><body>
      <script src="/wp-content/plugins/onoffice-for-wp-websites/app.js"></script>
      <p>Willkommen bei Ihrem Makler.</p>
    </body></html>
    """
    routes = {
        "https://vendor-only.de/": _resp(text=home_html),
        "https://vendor-only.de/robots.txt": _resp(status_code=404),
        "https://vendor-only.de/sitemap.xml": _resp(status_code=404),
        "https://vendor-only.de/wp-sitemap.xml": _resp(status_code=404),
    }
    client = _routed_client(routes)

    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "needs-manual-watch"
        assert agent.listing_url is None
        assert agent.extraction == {}


@pytest.mark.asyncio
async def test_onboard_agent_raises_for_missing_verified_domain(session):
    agent_id = _make_agent(session, verified_domain=None)
    client = AsyncMock()

    with pytest.raises(ValueError, match="verified_domain"):
        with session() as s:
            await onboard_agent(agent_id, client, session=s)


@pytest.mark.asyncio
async def test_onboard_agent_without_explicit_session_commits_itself(session, monkeypatch):
    agent_id = _make_agent(session)
    fake_row = {
        "reachable": True,
        "robots_allows_root": True,
        "vendors": ["onoffice"],
        "listing_url": "https://x.de/immobilien/",
        "structured": {"jsonld_types": []},
        "sitemap_object_urls": 0,
        "detail_links": 0,
        "signals": {"prices": 0},
    }
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    await onboard_agent(agent_id, client)  # keine Session übergeben

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "auto-harvested"
