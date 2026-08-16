"""Generischer, DB-getriebener Adapter für die agents-Tabelle.

Tritt NEBEN die statische REGISTRY, ersetzt sie nicht (Vollabdeckung-Spec
§5.3). Verteilt jede agents-Zeile mit coverage_status == "auto-harvested" an
die in EXTRACTION_METHODS registrierte Methode. Phase 2b registriert hier die
Kaskaden-Handler aus app.sources.agent_handlers: `vendor:<x>` (alle Einträge
aus app.agent_cascade_detect.VENDORS) und `detail_links` teilen sich EINEN
generischen Crawl+Extraktions-Handler (Phase 0 lieferte nur Vendor-
Fingerprints, keine Vendor-spezifischen Selektoren — `vendor:<x>` bleibt nur
Herkunfts-Tag), `sitemap_objekte`/`structured_data`/`feed_adapter` haben je
eigene Handler.

Zweistufiger Selbsttest (Vollabdeckung-Spec §7): das Ergebnis eines Handlers
wird gepuffert (Objektzahl pro Makler ist klein) und geprüft, bevor es
weitergereicht wird.
- Lieferte ein Makler NOCH NIE etwas (last_nonempty_at ist None) und der
  aktuelle Lauf liefert nichts Verwertbares, wird die optimistische, rein
  klassifikationsbasierte `auto-harvested`-Einstufung aus Phase 2a
  (app.agent_onboarding) sofort auf `needs-manual-watch` zurückgestuft
  ("Selbsttest vor Aktivierung").
- War der Makler zuvor erfolgreich, zählt `consecutive_empty_runs` (Phase 2c)
  aufeinanderfolgende Läufe ohne Selbsttest-Erfolg. Erst beim ZWEITEN Lauf in
  Folge (Spec §7) erfolgt der Downgrade auf `needs-manual-watch`; der erste
  Fehlschlag aktualisiert nur `last_checked` + den Zähler. Zwei Fälle werden
  im Log unterschieden: Handler lieferte 0 Objekte (Fall a, `log.info`,
  vermutlich transient) vs. Handler lieferte Objekte, aber keins bestand den
  Selbsttest (Fall b, `log.warning`, vermutlich echter Rezept-Bruch, z.B.
  Website-Relaunch).
Auf dem Erfolgspfad werden `last_checked`/`last_nonempty_at`/
`last_listing_count` geschrieben — vorher waren diese Spalten nur auf den
Fehlerpfaden gepflegt, für funktionierende Agents also tot.

Crawl-Frequenz-Guard (UX-Entscheidung nach Nutzer-Rückfrage): AgentSiteSource
hat bewusst KEIN eigenes Poll-Intervall-Setting — ein zweites Dashboard-Feld
nur für Makler-Sites wäre für den Nutzer schwer einzuordnen. Stattdessen
erzwingt fetch() strukturell (nicht nur per UI-Warnung), dass ein einzelner
Agent höchstens alle MIN_RECRAWL_INTERVAL neu gecrawlt wird — unabhängig vom
gewählten poll_interval_minutes (Dashboard-Presets: 6 Std. bis 3 Tage). Die
schnellste UI-Option (6 Std.) würde ohne diesen Guard Makler-Sites 4x
häufiger crawlen als Spec §3 "Täglich" vorsieht. Portal-Quellen sind davon
nicht betroffen und folgen weiterhin exakt dem gewählten Intervall.

Agent-Status-Writes (last_checked/coverage_status/…) laufen über
AgentSiteSource._write_agent(), das self.session (von pipeline.run_source()
gesetzt, solange dessen Transaktion offen ist) wiederverwendet statt eine
zweite, konkurrierende SQLite-Schreib-Session zu öffnen — sonst blockiert die
für die gesamte Laufzeit des Harvest-Laufs offene Aufrufer-Transaktion jeden
Schreibversuch hier ("database is locked", real reproduziert 2026-08-12)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select

import app.db as db_module
from app.agent_cascade_detect import VENDORS
from app.db import Agent, Listing
from app.logging_setup import log
from app.models import RawListing
from app.robots import is_allowed
from app.sources import agent_handlers
from app.sources.base import SourceAdapter

ExtractionMethod = Callable[
    [Agent, httpx.AsyncClient, "dict[str, datetime] | None"], AsyncIterator[RawListing]
]

# Höflichkeits-Guard (Spec §3/§8): unabhängig vom gewählten poll_interval_minutes
# wird ein einzelner Agent höchstens alle 20 Stunden neu gecrawlt (etwas unter
# 24h, um Scheduler-Jitter zu tolerieren, ohne einen Tag ganz auszulassen).
# Bewusst kein DB-Setting — das ist eine Höflichkeits-/Rechtsgrenze, kein
# Produkt-Feature, das der Nutzer versehentlich lockern können soll.
MIN_RECRAWL_INTERVAL = timedelta(hours=20)


def _default_extraction_methods() -> dict[str, ExtractionMethod]:
    methods: dict[str, ExtractionMethod] = {
        "detail_links": agent_handlers.crawl_and_extract,
        "sitemap_objekte": agent_handlers.sitemap_objekte_handler,
        "structured_data": agent_handlers.structured_data_handler,
        "feed_adapter": agent_handlers.feed_adapter_handler,
    }
    methods.update({f"vendor:{vendor}": agent_handlers.crawl_and_extract for vendor in VENDORS})
    return methods


EXTRACTION_METHODS: dict[str, ExtractionMethod] = _default_extraction_methods()


def _passes_self_test(listings: list[RawListing]) -> bool:
    """Vollabdeckung-Spec §7: ein Rezept wird aktiv, wenn es mindestens ein
    Objekt mit Titel, Detail-Link UND mindestens einem Sachattribut (Preis
    ODER Fläche) liefert. Fehlende Preise allein sind KEIN Fehlschlag — viele
    Seeobjekte tragen grundsätzlich "Preis auf Anfrage"."""
    for raw in listings:
        if not raw.title or not raw.url:
            continue
        if raw.price_eur is not None or raw.qm is not None:
            return True
    return False


class AgentSiteSource(SourceAdapter):
    """Ein Adapter-Objekt repräsentiert alle Makler-eigenen Websites
    zusammen — jede agents-Zeile wird einzeln isoliert verarbeitet, ein
    fehlschlagender Makler bricht nie den Gesamtlauf ab (Spec §7)."""

    name = "agents"

    def _write_agent(self, agent_id: int, **fields: object) -> None:
        """Schreibt Statusfelder auf eine Agent-Zeile.

        Läuft fetch() innerhalb einer offenen Aufrufer-Transaktion
        (self.session von pipeline.run_source() gesetzt), wird DIESE Session
        wiederverwendet und nur geflusht, nicht committet — der Aufrufer
        besitzt Commit/Rollback. Eine zweite, separat committende Session
        würde für die gesamte Laufzeit der offenen Aufrufer-Transaktion
        blockieren (derselbe Lock-Mechanismus, den geocode()'s Session-Reuse
        für den Geocoding-Cache bereits löst — siehe SourceAdapter.session).
        Ohne Aufrufer-Session (Standalone-Nutzung, Tests) öffnet/committet die
        Methode wie bisher selbst."""
        if self.session is not None:
            db_agent = self.session.get(Agent, agent_id)
            if db_agent is not None:
                for key, value in fields.items():
                    setattr(db_agent, key, value)
                self.session.flush()
            return
        with db_module.SessionLocal() as session:
            db_agent = session.get(Agent, agent_id)
            if db_agent is not None:
                for key, value in fields.items():
                    setattr(db_agent, key, value)
                session.commit()

    def _known_urls_for_agent(self, agent_id: int) -> dict[str, datetime]:
        """Change-Gate-Fingerprint (Vollabdeckung-Spec Phase 2c §3): liest
        bestehende Listing-URLs + deren last_seen_at für diesen Agenten aus
        der Listing-Tabelle -- kein neues Schema, jede Agent-Listing trägt
        das schon. Nutzt self.session (offene Aufrufer-Transaktion) wenn
        vorhanden, sonst eine kurzlebige eigene Session -- analog zu
        _write_agent(). Der literale Bindestrich direkt nach der Agent-ID im
        source_id-Format (f"agent-{agent_id}-{hash}", siehe
        app.sources.agent_handlers._source_id) verhindert Präfix-Kollisionen
        zwischen z.B. Agent 1 und Agent 12."""
        stmt = select(Listing.url, Listing.last_seen_at).where(
            Listing.source == "agents",
            Listing.source_id.like(f"agent-{agent_id}-%"),
        )
        if self.session is not None:
            rows = self.session.execute(stmt).all()
            return {url: last_seen for url, last_seen in rows}
        with db_module.SessionLocal() as session:
            rows = session.execute(stmt).all()
            return {url: last_seen for url, last_seen in rows}

    async def fetch(self) -> AsyncIterator[RawListing]:
        assert self.client is not None
        with db_module.SessionLocal() as session:
            agents = list(session.scalars(select(Agent).where(Agent.coverage_status == "auto-harvested")))

        # `agents` sind detachte ORM-Instanzen — die Session ist schon zu. In
        # dieser Schleife nur lesend verwenden (inkl. agent.last_nonempty_at,
        # bereits Teil des initialen SELECTs); wer in die Agent-Zeile
        # zurückschreiben will, öffnet eine frische Session und lädt die Zeile
        # neu (wie die robots-disallowed-/Selbsttest-/Erfolgs-Zweige unten),
        # statt die detachte Instanz zu mutieren.
        for agent in agents:
            since_last_check = agent.last_checked and datetime.utcnow() - agent.last_checked
            # Finding 4: der Höflichkeits-Guard darf einen Agent, der noch NIE
            # erfolgreich geharvestet wurde (last_nonempty_at is None), nicht
            # bremsen — sonst wartet der Selbsttest aus Phase 2a ("optimistische
            # Klassifikation braucht Validierung vor Aktivierung") bis zu
            # MIN_RECRAWL_INTERVAL, obwohl app.agent_onboarding last_checked
            # schon beim Onboarding selbst setzt (vor jedem Harvest-Versuch).
            if (
                since_last_check is not None
                and since_last_check < MIN_RECRAWL_INTERVAL
                and agent.last_nonempty_at is not None
            ):
                # Höflichkeits-Guard: unabhängig vom Poll-Intervall max. ~1x/Tag
                # pro Agent (siehe Modul-Docstring "Crawl-Frequenz-Guard") —
                # gilt nur für Agents, die schon mindestens einmal erfolgreich
                # geharvestet wurden.
                log.debug("agents_adapter.recrawl_too_soon", agent_id=agent.id)
                continue

            method_name = (agent.extraction or {}).get("method")
            if not method_name:
                log.warning("agents_adapter.no_method", agent_id=agent.id, agent_name=agent.name)
                continue
            handler = EXTRACTION_METHODS.get(method_name)
            if handler is None:
                log.warning("agents_adapter.unknown_method", agent_id=agent.id, method=method_name)
                continue
            # HER-726: feed_adapter braucht keine listing_url, sondern
            # extraction["feed_url"] — das Gate darf ihn deshalb nicht mehr
            # unbedingt an listing_url binden.
            feed_url = (agent.extraction or {}).get("feed_url")
            if not agent.listing_url and not feed_url:
                log.warning("agents_adapter.no_listing_url", agent_id=agent.id)
                continue

            try:
                robots_check_url = agent.listing_url or feed_url
                if not await is_allowed(self.client, robots_check_url):
                    log.info("agents_adapter.robots_disallowed", agent_id=agent.id, url=robots_check_url)
                    self._write_agent(
                        agent.id,
                        coverage_status="robots-disallowed",
                        coverage_reason=f"robots.txt verbietet Zugriff auf {robots_check_url}",
                        last_checked=datetime.utcnow(),
                    )
                    continue

                known_urls = self._known_urls_for_agent(agent.id)
                harvested = [raw async for raw in handler(agent, self.client, known_urls)]
                now = datetime.utcnow()

                if not _passes_self_test(harvested):
                    if agent.last_nonempty_at is None:
                        # Nie zuvor erfolgreich -> die optimistische
                        # Phase-2a-Klassifikation war falsch, sofort
                        # zurückstufen (Spec §7: Selbsttest vor Aktivierung).
                        # Kein Streak nötig -- Erstaktivierungs-Selbsttest.
                        log.info("agents_adapter.self_test_failed", agent_id=agent.id, count=len(harvested))
                        self._write_agent(
                            agent.id,
                            coverage_status="needs-manual-watch",
                            coverage_reason=(
                                f"Selbsttest fehlgeschlagen: Handler {method_name!r} lieferte "
                                "keine verwertbaren Objekte (Titel, Detail-Link und mind. ein "
                                "Sachattribut nötig)."
                            ),
                            last_checked=now,
                        )
                        continue

                    # War zuvor erfolgreich -> Zwei-Läufe-Zähler (Phase 2c,
                    # Spec §4): ein einzelner leerer/selbsttest-untauglicher
                    # Lauf ist noch kein Rezept-Bruch (Spec §7: Bruch erst
                    # nach ZWEI aufeinanderfolgenden Läufen).
                    empty_runs = (agent.consecutive_empty_runs or 0) + 1
                    if len(harvested) == 0:
                        # Fall (a): Handler lieferte 0 Objekte -- vermutlich
                        # transienter Netzwerkfehler oder Blockade.
                        log.info(
                            "agents_adapter.empty_run_case_a_zero_objects",
                            agent_id=agent.id,
                            consecutive_empty_runs=empty_runs,
                        )
                        case_reason = "Handler lieferte 0 Objekte"
                    else:
                        # Fall (b): Handler lieferte N>0 Objekte, aber keins
                        # bestand den Selbsttest -- vermutlich echter
                        # Rezept-Bruch (z.B. Website-Relaunch entfernte
                        # Preis/Fläche aus dem Markup). Höheres Log-Level als
                        # Fall (a), wie im Phase-2b-Plan als Grundlage für
                        # diesen Zähler vorgezeichnet.
                        log.warning(
                            "agents_adapter.empty_run_case_b_all_failed_self_test",
                            agent_id=agent.id,
                            count=len(harvested),
                            consecutive_empty_runs=empty_runs,
                        )
                        case_reason = (
                            f"Handler lieferte {len(harvested)} Objekte, keins bestand den Selbsttest"
                        )

                    if empty_runs >= 2:
                        self._write_agent(
                            agent.id,
                            coverage_status="needs-manual-watch",
                            coverage_reason=(
                                f"Zwei aufeinanderfolgende Läufe ohne Selbsttest-Erfolg. "
                                f"Letzter Lauf: {case_reason}."
                            ),
                            consecutive_empty_runs=empty_runs,
                            last_checked=now,
                        )
                    else:
                        self._write_agent(agent.id, consecutive_empty_runs=empty_runs, last_checked=now)
                    continue

                self._write_agent(
                    agent.id,
                    last_checked=now,
                    last_nonempty_at=now,
                    last_listing_count=len(harvested),
                    consecutive_empty_runs=0,
                )

                for raw in harvested:
                    yield raw
            except Exception as e:
                log.error(
                    "agents_adapter.agent_failed",
                    agent_id=agent.id,
                    agent_name=agent.name,
                    error=str(e),
                )
                # Finding 2b: last_checked auch hier schreiben — ohne das
                # bleibt es für einen dauerhaft fehlschlagenden Agent
                # eingefroren, MIN_RECRAWL_INTERVAL greift dann nie, der Agent
                # wird bei jedem Poll-Zyklus erneut (und unhöflich oft)
                # angefasst. coverage_status bleibt bewusst unverändert — hier
                # ist unklar, ob der Fehler transient oder rezeptbedingt ist.
                self._write_agent(agent.id, last_checked=datetime.utcnow())
                continue
