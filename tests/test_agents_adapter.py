"""Tests für AgentSiteSource — generischer, DB-getriebener Adapter für die
agents-Tabelle. Additiv zur REGISTRY (Vollabdeckung-Spec §5.3)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.db import Agent, Base, FetchRun, Listing
from app.models import PropertyType, RawListing
from app.sources.agent_handlers import _urls_to_fetch
from app.sources.agents_adapter import EXTRACTION_METHODS, AgentSiteSource


@pytest.fixture()
def session(monkeypatch, tmp_path):
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


@pytest.fixture(autouse=True)
def clean_extraction_methods():
    EXTRACTION_METHODS.clear()
    yield
    EXTRACTION_METHODS.clear()


def _make_agent(session, **overrides) -> int:
    defaults = dict(
        name="Test Makler",
        coverage_status="auto-harvested",
        listing_url="https://example.de/angebote/",
        extraction={"method": "fake"},
    )
    defaults.update(overrides)
    with session() as s:
        agent = Agent(**defaults)
        s.add(agent)
        s.commit()
        return agent.id


@pytest.mark.asyncio
async def test_fetch_yields_from_registered_method(session, monkeypatch):
    agent_id = _make_agent(session)

    async def fake_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        yield RawListing(
            source="agents",
            source_id=f"agent-{agent.id}-1",
            url="https://example.de/angebote/1",
            title="Testobjekt",
            price_eur=450000,
            property_type=PropertyType.HAUS,
        )

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert len(results) == 1
    assert results[0].source_id == f"agent-{agent_id}-1"


@pytest.mark.asyncio
async def test_fetch_skips_agents_not_auto_harvested(session, monkeypatch):
    """Strukturelle Garantie der Transparenz-Anforderung: nur
    coverage_status == 'auto-harvested' wird überhaupt angefasst — 'unknown'
    zählt nie als abgedeckt."""
    _make_agent(session, coverage_status="unknown")

    async def fake_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        yield RawListing(source="agents", source_id="x", url="https://x", title="x")

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []


@pytest.mark.asyncio
async def test_fetch_skips_agent_without_method(session, monkeypatch):
    _make_agent(session, extraction={})
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []


@pytest.mark.asyncio
async def test_fetch_skips_unregistered_method(session, monkeypatch):
    _make_agent(session, extraction={"method": "does-not-exist"})
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []


@pytest.mark.asyncio
async def test_fetch_marks_robots_disallowed_and_persists_reason(session, monkeypatch):
    agent_id = _make_agent(session)

    async def fake_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        yield RawListing(source="agents", source_id="x", url="https://x", title="x")

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=False))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []
    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "robots-disallowed"
        assert agent.coverage_reason is not None
        assert agent.last_checked is not None


@pytest.mark.asyncio
async def test_fetch_isolates_a_failing_agent_from_the_rest(session, monkeypatch):
    """Spec §7: 'Ein fehlschlagender Makler bricht nie den Gesamtlauf ab.'"""
    broken_id = _make_agent(session, name="Broken Makler")
    ok_id = _make_agent(session, name="OK Makler", listing_url="https://ok.example.de/angebote/")

    call_count = {"n": 0}

    async def flaky_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        call_count["n"] += 1
        if agent.name == "Broken Makler":
            raise RuntimeError("boom")
        yield RawListing(
            source="agents",
            source_id=f"agent-{agent.id}",
            url=agent.listing_url,
            title="OK",
            price_eur=450000,
        )

    EXTRACTION_METHODS["fake"] = flaky_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert call_count["n"] == 2
    assert len(results) == 1
    assert results[0].source_id == f"agent-{ok_id}"
    # Finding 2b: last_checked wird jetzt auch im Fehlerfall geschrieben,
    # damit MIN_RECRAWL_INTERVAL für dauerhaft fehlschlagende Agents greift
    # statt sie bei jedem Poll-Zyklus erneut (unhöflich) anzufassen.
    with session() as s:
        broken = s.get(Agent, broken_id)
        assert broken.last_checked is not None
        assert broken.coverage_status == "auto-harvested"


@pytest.mark.asyncio
async def test_fetch_isolates_an_is_allowed_exception_from_the_rest(session, monkeypatch):
    """Die robots-Prüfung selbst ist Teil der Pro-Agent-Isolation (Spec §7):
    ein RobotFileParser-Fehler o.ä. für einen Makler darf den Gesamtlauf
    nicht abbrechen — der review-round-1-Fix für agents_adapter.py."""
    broken_id = _make_agent(session, name="Broken Makler", listing_url="https://broken.example.de/angebote/")
    ok_id = _make_agent(session, name="OK Makler", listing_url="https://ok.example.de/angebote/")

    async def fake_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        yield RawListing(
            source="agents",
            source_id=f"agent-{agent.id}",
            url=agent.listing_url,
            title="OK",
            price_eur=450000,
        )

    async def flaky_is_allowed(client, url):
        if url == "https://broken.example.de/angebote/":
            raise ValueError("malformed robots.txt")
        return True

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", flaky_is_allowed)

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert len(results) == 1
    assert results[0].source_id == f"agent-{ok_id}"
    with session() as s:
        broken_agent = s.get(Agent, broken_id)
        # is_allowed() wird INNERHALB desselben try/except aufgerufen wie der
        # Handler (fetch() hat nur einen try/except-Block) -- die Exception
        # landet also im selben Fehlerpfad wie Finding 2b und last_checked
        # WIRD jetzt geschrieben (vorher: kein DB-Write, weil der Fehlerpfad
        # last_checked gar nicht setzte). coverage_status bleibt unverändert
        # -- nur die Isolation (kein Abbruch des Gesamtlaufs) und der
        # Crawl-Frequenz-Beleg sind hier relevant.
        assert broken_agent.coverage_status == "auto-harvested"
        assert broken_agent.last_checked is not None


def test_registry_includes_agents_source_additively(session):
    """`session`-Fixture nötig seit HER-805: get_all_adapters() fragt jetzt
    die `sources`-Tabelle nach deaktivierten Quellen ab."""
    from app.sources import REGISTRY, get_all_adapters
    from app.sources.agents_adapter import AgentSiteSource
    from app.sources.kleinanzeigen import KleinanzeigenSource

    assert REGISTRY["agents"] is AgentSiteSource
    assert REGISTRY["kleinanzeigen"] is KleinanzeigenSource  # unverändert

    adapters = get_all_adapters()
    assert any(isinstance(a, AgentSiteSource) for a in adapters)
    assert len(adapters) == len(REGISTRY)


def test_default_extraction_methods_cover_every_vendor_and_stage_key():
    from app.agent_cascade_detect import VENDORS
    from app.sources import agent_handlers
    from app.sources.agents_adapter import _default_extraction_methods

    methods = _default_extraction_methods()

    assert methods["detail_links"] is agent_handlers.crawl_and_extract
    assert methods["sitemap_objekte"] is agent_handlers.sitemap_objekte_handler
    assert methods["structured_data"] is agent_handlers.structured_data_handler
    assert methods["feed_adapter"] is agent_handlers.feed_adapter_handler
    for vendor in VENDORS:
        assert methods[f"vendor:{vendor}"] is agent_handlers.crawl_and_extract


@pytest.mark.asyncio
async def test_fetch_dispatches_feed_adapter_agent_without_listing_url(session, monkeypatch):
    """HER-726: feed_adapter-Agents haben keine listing_url, nur
    extraction['feed_url'] — das Gate darf sie deshalb nicht mehr blind
    überspringen."""
    agent_id = _make_agent(
        session,
        listing_url=None,
        extraction={"method": "fake", "feed_url": "https://example.de/feed/"},
    )

    async def fake_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        yield RawListing(
            source="agents",
            source_id=f"agent-{agent.id}",
            url="https://example.de/objekte/1",
            title="Feed-Objekt",
            price_eur=450000,
        )

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert len(results) == 1
    assert results[0].source_id == f"agent-{agent_id}"


@pytest.mark.asyncio
async def test_fetch_downgrades_agent_on_first_ever_empty_run(session, monkeypatch):
    """Spec §7 Selbsttest vor Aktivierung: ein Makler, der NIE zuvor etwas
    geliefert hat (last_nonempty_at ist der Default None), wird bei 0
    verwertbaren Objekten sofort auf needs-manual-watch zurückgestuft."""
    agent_id = _make_agent(session)

    async def empty_field_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        # Titel + URL vorhanden, aber weder Preis noch Fläche -> Selbsttest
        # muss das als "nicht verwertbar" werten.
        yield RawListing(source="agents", source_id="x", url="https://example.de/x", title="Ohne Sachdaten")

    EXTRACTION_METHODS["fake"] = empty_field_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []
    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "needs-manual-watch"
        assert "Selbsttest" in agent.coverage_reason


@pytest.mark.asyncio
async def test_fetch_passes_self_test_when_area_present_without_price(session, monkeypatch):
    """Spec §7: fehlender Preis allein ist KEIN Fehlschlag (Seeobjekte:
    "Preis auf Anfrage") — Fläche allein reicht als Sachattribut."""
    _make_agent(session)

    async def qm_only_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        yield RawListing(
            source="agents", source_id="x", url="https://example.de/x", title="Preis auf Anfrage", qm=180.0
        )

    EXTRACTION_METHODS["fake"] = qm_only_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert len(results) == 1


@pytest.mark.asyncio
async def test_fetch_writes_last_checked_and_last_nonempty_at_on_success(session, monkeypatch):
    """Spec §5.1: 'Ein Status gilt nur mit frischem Beleg' -- last_checked/
    last_nonempty_at/last_listing_count müssen auch auf dem Erfolgspfad
    geschrieben werden, nicht nur bei robots-disallowed/Selbsttest-Downgrade
    (Advisor-Fund: waren bisher tote Spalten für funktionierende Agents)."""
    agent_id = _make_agent(session)

    async def fake_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        yield RawListing(
            source="agents", source_id="x", url="https://example.de/x", title="OK", price_eur=450000
        )
        yield RawListing(source="agents", source_id="y", url="https://example.de/y", title="OK2", qm=100.0)

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert len(results) == 2
    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "auto-harvested"
        assert agent.last_checked is not None
        assert agent.last_nonempty_at is not None
        assert agent.last_listing_count == 2


@pytest.mark.asyncio
async def test_fetch_reuses_caller_session_instead_of_opening_a_second_writer(session, monkeypatch):
    """Regression gegen den SQLite-Write-Lock-Deadlock (real reproduziert
    2026-08-12 in Produktion, siehe Modul-Docstring von agents_adapter.py).

    pipeline.run_source() hält während des gesamten fetch()-Laufs eine
    offene, bereits geflushte Schreib-Transaktion (session.add(run) +
    flush()). Schreibt AgentSiteSource intern über eine ZWEITE, eigene
    Session, blockiert das mit 'database is locked' -- SQLite erlaubt nur
    einen Schreiber. self.session (von run_source() gesetzt) muss deshalb
    wiederverwendet werden, exakt wie geocode() es für den Geocoding-Cache
    bereits tut (tests/test_pipeline.py::
    test_run_source_survives_geocode_cache_miss_inside_open_transaction).

    Die Test-Engine hat bewusst KEIN connect_args={'timeout': ...} (wie die
    Produktions-Engine in app/db.py) -- ein echter zweiter Schreiber würde
    hier sofort mit OperationalError scheitern statt erst nach 30s zu warten,
    was den Test schnell und deterministisch macht."""
    agent_id = _make_agent(session)

    async def fake_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        yield RawListing(
            source="agents", source_id="x", url="https://example.de/x", title="OK", price_eur=450000
        )

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    with session() as outer:
        # Simuliert exakt den Zustand von pipeline.run_source(): eine offene,
        # geflushte (aber nicht committete) Schreib-Transaktion.
        outer.add(FetchRun(source="agents"))
        outer.flush()
        adapter.session = outer

        async with adapter:
            results = [raw async for raw in adapter.fetch()]

        assert len(results) == 1
        # Sichtbar innerhalb DERSELBEN, noch offenen Transaktion -- kein
        # zweiter Schreiber, kein Lock.
        agent = outer.get(Agent, agent_id)
        assert agent.last_checked is not None
        assert agent.last_nonempty_at is not None
        assert agent.last_listing_count == 1
        outer.commit()


@pytest.mark.asyncio
async def test_fetch_tolerates_single_empty_run_after_prior_success(session, monkeypatch):
    """Spec §7 Bruch-Erkennung: ein Rezept gilt erst nach ZWEI
    aufeinanderfolgenden leeren Läufen als gebrochen (Zähl-Logik selbst ist
    Change-Gate-Arbeit, Phase 2c) -- ein einzelner transienter Leerlauf
    (z.B. ein 5xx) darf einen zuvor erfolgreichen Agent nicht sofort auf
    needs-manual-watch zurückstufen, sonst fliegt er dauerhaft aus dem Crawl
    (fetch() selektiert nur coverage_status == 'auto-harvested')."""
    agent_id = _make_agent(session, last_nonempty_at=datetime(2026, 8, 1))

    async def empty_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        if False:
            yield RawListing(source="agents", source_id="x", url="https://x", title="x")

    EXTRACTION_METHODS["fake"] = empty_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []
    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "auto-harvested"
        assert agent.last_checked is not None


@pytest.mark.asyncio
async def test_fetch_skips_agent_recrawled_too_recently(session, monkeypatch):
    """UX-Entscheidung (Nutzer-Rückfrage zur Crawl-Frequenz): Makler-Sites
    werden unabhängig vom gewählten Poll-Intervall max. ~1x/Tag pro Agent neu
    gecrawlt. Ein last_checked von vor 2 Stunden ist zu frisch -- der Handler
    darf gar nicht erst aufgerufen werden.

    last_nonempty_at muss hier gesetzt sein (Finding 4): der Guard greift nur
    für Agents, die schon mindestens einmal erfolgreich geharvestet wurden --
    ohne last_nonempty_at würde dieser Test den Skip-Pfad gar nicht mehr
    exercisen."""
    _make_agent(
        session,
        last_checked=datetime.utcnow() - timedelta(hours=2),
        last_nonempty_at=datetime.utcnow() - timedelta(days=1),
    )

    call_count = {"n": 0}

    async def fake_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        call_count["n"] += 1
        yield RawListing(source="agents", source_id="x", url="https://x", title="x", price_eur=1)

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []
    assert call_count["n"] == 0


@pytest.mark.asyncio
async def test_fetch_crawls_freshly_onboarded_agent_despite_recent_last_checked(session, monkeypatch):
    """Finding 4: app.agent_onboarding setzt last_checked schon beim
    Onboarding, bevor je ein Harvest gelaufen ist. Ein Agent, der noch NIE
    erfolgreich geharvestet wurde (last_nonempty_at ist None), muss trotz
    frischem last_checked sofort gecrawlt werden -- sonst wartet der
    Selbsttest aus Phase 2a bis zu MIN_RECRAWL_INTERVAL (20 Std.)."""
    _make_agent(
        session,
        last_checked=datetime.utcnow() - timedelta(minutes=5),
        last_nonempty_at=None,
    )

    call_count = {"n": 0}

    async def fake_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        call_count["n"] += 1
        yield RawListing(source="agents", source_id="x", url="https://x", title="x", price_eur=450000)

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert call_count["n"] == 1
    assert len(results) == 1


@pytest.mark.asyncio
async def test_fetch_crawls_agent_when_last_checked_is_stale_enough(session, monkeypatch):
    """Gegenprobe: last_checked von vor 25 Stunden liegt über der
    MIN_RECRAWL_INTERVAL-Schwelle (20 Std.) -- der Agent wird ganz normal
    gecrawlt."""
    _make_agent(session, last_checked=datetime.utcnow() - timedelta(hours=25))

    async def fake_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        yield RawListing(source="agents", source_id="x", url="https://x", title="x", price_eur=450000)

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert len(results) == 1


def _make_listing(session, **overrides) -> None:
    defaults = dict(
        dedup_hash=f"hash-{overrides.get('url', 'x')}",
        source="agents",
        source_id="agent-1-abc123",
        url="https://x.de/objekt/1",
        title="Testobjekt",
        last_seen_at=datetime.utcnow(),
    )
    defaults.update(overrides)
    with session() as s:
        s.add(Listing(**defaults))
        s.commit()


@pytest.mark.asyncio
async def test_fetch_passes_known_urls_from_existing_listings_to_handler(session, monkeypatch):
    agent_id = _make_agent(session, id=1)
    known_seen_at = datetime.utcnow() - timedelta(days=2)
    _make_listing(
        session,
        dedup_hash="hash-known",
        source_id=f"agent-{agent_id}-known",
        url="https://x.de/objekt/known",
        last_seen_at=known_seen_at,
    )
    captured_known_urls = {}

    async def fake_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        captured_known_urls.update(known_urls or {})
        return
        yield  # pragma: no cover - macht die Funktion zum Async-Generator

    EXTRACTION_METHODS["fake"] = fake_method
    client = AsyncMock()
    monkeypatch.setattr("app.robots.is_allowed", AsyncMock(return_value=True))

    source = AgentSiteSource()
    source.client = client
    [_ async for _ in source.fetch()]

    assert captured_known_urls == {"https://x.de/objekt/known": known_seen_at}


@pytest.mark.asyncio
async def test_fetch_does_not_leak_other_agents_listings_into_known_urls(session, monkeypatch):
    """Regressionstest gegen den literalen Brief-Wortlaut korrigiert: Agent 1
    UND Agent 12 nutzen denselben registrierten 'fake'-Handler und werden
    beide gefetcht (coverage_status='auto-harvested' per _make_agent-Default).
    Ein einziges gemeinsames captured_known_urls-Dict für beide Aufrufe hätte
    Agent 12s korrekten Blick auf SEINE EIGENE Listing (kein Leck, sondern
    erwartetes Verhalten) fälschlich als 'Leck aus Agent 1' gewertet und wäre
    auch bei korrekter Implementierung rot geblieben (nachgewiesen: Lauf
    gegen den unveränderten Brief-Test schlägt mit dem korrekten
    Präfix-Pattern fehl). Fix: pro Agent-ID isoliert erfassen, nur Agent 1s
    Sicht prüfen -- die Diskriminierungskraft gegen die eigentliche
    Präfix-Kollision (Bindestrich-Bug) bleibt erhalten, siehe Task-4-Report."""
    agent_id = _make_agent(session, id=1, name="Agent Eins")
    _make_agent(session, id=12, name="Agent Zwölf")
    _make_listing(
        session,
        dedup_hash="hash-other-agent",
        source_id="agent-12-xyz789",
        url="https://y.de/objekt/other",
        last_seen_at=datetime.utcnow(),
    )
    captured_known_urls_by_agent = {}

    async def fake_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        captured_known_urls_by_agent[agent.id] = known_urls or {}
        return
        yield  # pragma: no cover

    EXTRACTION_METHODS["fake"] = fake_method
    client = AsyncMock()
    monkeypatch.setattr("app.robots.is_allowed", AsyncMock(return_value=True))

    source = AgentSiteSource()
    source.client = client
    [_ async for _ in source.fetch()]

    assert captured_known_urls_by_agent[agent_id] == {}


def test_known_urls_for_agent_returns_naive_datetimes_compatible_with_urls_to_fetch(session):
    """Kritischer Review-Punkt aus Task 2: _urls_to_fetch() rechnet
    `now - known_urls[url]` mit naivem datetime.utcnow(). Käme
    last_seen_at aware aus der DB zurück, würde JEDER Harvest-Lauf mit
    TypeError abbrechen (nicht still ignorieren). SQLite/SQLAlchemy liefert
    bei einer DateTime-Spalte ohne timezone=True normalerweise naive
    Datetimes -- hier explizit verifiziert statt nur angenommen, inkl.
    Direktlauf gegen die echte _urls_to_fetch()-Konsumentin."""
    agent_id = _make_agent(session, id=1)
    _make_listing(
        session,
        dedup_hash="hash-naive-check",
        source_id=f"agent-{agent_id}-naive",
        url="https://x.de/objekt/naive",
        last_seen_at=datetime.utcnow() - timedelta(days=1),
    )

    source = AgentSiteSource()
    known_urls = source._known_urls_for_agent(agent_id)

    assert known_urls
    for last_seen in known_urls.values():
        assert last_seen.tzinfo is None

    # Muss ohne TypeError laufen -- würde sonst jeden Harvest-Lauf abbrechen.
    # (Canary-Regel: bei nur einer einzigen, frischen bekannten URL wird sie
    # trotzdem erzwungen -- siehe _urls_to_fetch()-Docstring; der Punkt hier
    # ist ausschließlich, dass die Subtraktion nicht mit TypeError abbricht.)
    due = _urls_to_fetch(list(known_urls.keys()), known_urls, datetime.utcnow())
    assert due == ["https://x.de/objekt/naive"]
