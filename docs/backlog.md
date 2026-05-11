# immo-radar — Feature Backlog

Zuletzt aktualisiert: 2026-05-11

---

## Legende

| Symbol | Bedeutung |
|---|---|
| ✅ | Fertig |
| 🔧 | Vereinfacht / teilweise fertig |
| ⏳ | In Arbeit |
| ☐ | Offen |

---

## Pre-Phase 1 — Bugfixes

| # | Feature | Status | Aufwand |
|---|---|---|---|
| B1 | `enrich_attempts`-Zähler gegen AI-Endlosschleife | ✅ | S |
| B2 | `docker-compose` → `docker compose` (V2) | ✅ | XS |
| B3 | AI-Enrichment-Fehlerursache debuggen | ✅ | S |
| B4 | UTC-Timestamps im Frontend korrekt parsen (`parseUTC()` + `Z`-Suffix) | ✅ | XS |
| B5 | DB-Quellnamen migrieren (`makler_bsimmo` → `bs_immo` etc.) → `last_run` funktioniert | ✅ | XS |

---

## Phase 1 — Core Dashboard

| # | Feature | Status | Aufwand |
|---|---|---|---|
| 1.1 | React/Vite-Setup + FastAPI JSON-Endpoints | ✅ | M |
| 1.2 | Listings-Ansicht mit Filterleiste | 🔧 | L |
| 1.3 | Listing-Detailpanel (Slide-in von rechts, 420px) | ✅ | M |
| 1.4 | Preis/m² Berechnung überall | ✅ | S |
| 1.5 | "Time on Market" — `first_seen_at` als "seit X Tagen" | ✅ | S |
| 1.6 | "Neu seit letztem Besuch"-Badge via localStorage | ✅ | S |
| 1.7 | Status-Management (5 Stufen) | ✅ | S |
| 1.8 | Settings: Suchprofil-Editor | ✅ | M |
| 1.9 | Settings: Score-Threshold für Telegram | ✅ | S |
| 1.10 | Settings: Telegram-Konfiguration + Test | ✅ | S |
| 1.11 | Settings: Quellen-Toggle + Status (aktiv/gesperrt/Vorschlag) + `last_run` live | ✅ | S |
| 1.12 | System-Status-Seite (Crawl-History, Stats, Trigger) | ✅ | S |
| 1.13 | Auth: Caddy basicauth + `immo.herrlich.dev` live | ✅ | S |

### 1.2 Filterleiste — fehlende Teile

| Sub-Feature | Status |
|---|---|
| Status-Chips | ✅ |
| AI-Score Threshold | ✅ |
| Quellen-Filter (Select) | ✅ |
| Preis-Range Slider (Min/Max) | ☐ |
| m²-Range Slider (Min/Max) | ☐ |
| Zimmer-Min (Stepper/Select) | ☐ |
| Sortierung (Erst gesehen / Preis / Score / Preis/m²) | ☐ |

### 1.8 Suchprofil-Tab — alle Teile

| Sub-Feature | Status |
|---|---|
| Radius-Slider (km) | ✅ |
| Budget-Inputs (Min/Max) | ✅ |
| Zimmer-Min Select | ✅ |
| Leaflet-Karte mit draggablem Pin + Radius-Kreis | ✅ |
| Nominatim-Geocoding (Adresssuche) | ✅ |
| Baujahr-Slider ab 1850 | ✅ |
| Objekttypen-Checkboxen (Wohnung, Haus, DHH, …) | ✅ |
| KI-Ausstattungs-Präferenzen (Chips: Balkon, Terrasse, Garten, …) | ✅ |
| Multi-Ortsauswahl (mehrere Zentren + Radien) | ✅ |

---

## Phase 1.5 — Domain & Auth

| # | Feature | Status | Aufwand |
|---|---|---|---|
| D1 | Domain `immo.herrlich.dev` via Caddy (HTTPS + TLS) | ✅ | XS |
| D2 | Caddy basicauth (wie `h5.herrlich.dev`) | ✅ | XS |
| D3 | Docker-Container auf `127.0.0.1:8001` (kein Tailscale-Direktzugriff) | ✅ | XS |
| D4 | `deploy.sh` aktualisieren (Caddy-Config automatisch updaten) | ✅ | S |

---

## Phase 2 — Intelligenz

| # | Feature | Status | Aufwand |
|---|---|---|---|
| 2.1 | Karten-Toggle in Listings (Leaflet + Pins nach Status) | ☐ | M |
| 2.2 | Leaflet-Minimap im Detailpanel (wenn Koordinaten vorhanden) | ☐ | S |
| 2.3 | Ort/Radius-Picker mit Karte in Settings (Nominatim, 1s Debounce) | ✅ | M |
| 2.4 | Preishistorie-Chart (Recharts LineChart, wenn Änderungen vorhanden) | ☐ | S |
| 2.5 | Cross-Portal-Duplikat-Hinweis im Detailpanel | ☐ | M |
| 2.6 | Junk-Keyword-Editor in MechanicsTab | ☐ | S |
| 2.7 | Keyboard-Navigation (j/k/e/1–5/Esc/m) | ☐ | S |
| 2.8 | Manuelle Quelle per URL-Analyse (Claude-Agent) + Discover | ✅ | L |
| 2.9 | API-Kosten-Tracking (Token-Logging + Anzeige in MechanicsTab) | ✅ | M |
| 2.10 | Multi-Ortsauswahl im Suchprofil (mehrere Zentren + Radien) | ✅ | L |
| 2.11 | Poll-Interval + Enrich-Toggle in MechanicsTab (DB-persistent, kein Restart) | ✅ | M |
| 2.12 | IS24 RSS-Adapter (attempted — IS24 blockiert RSS ohne Auth; `source_type=blocked`) | ✅ | S |

---

## Phase 3 — Innovation

| # | Feature | Status | Aufwand |
|---|---|---|---|
| 3.1 | Autonome Quellen-Entdeckung (Claude Agent) | ✅ (Discover-Button) | XL |
| 3.2 | Markt-Trendanalyse (Preis/m² über Zeit in Region) | ☐ | M |
| 3.3 | S-Bahn-Pendeldauer nach München (ÖPNV API) | ☐ | S |
| 3.4 | Bodenrichtwert auto-fetch (BORIS-Schnittstelle) | ☐ | M |
| 3.5 | Tägliche Digest-Telegram-Zusammenfassung | ☐ | S |
| 3.6 | Vergleichsansicht (2–3 Listings nebeneinander) | ☐ | M |
| 3.7 | Export als PDF-Report (für Bankgespräch) | ☐ | M |

---

## Aktuelle Priorität

1. **Phase 1 Completion** — Filterleiste vervollständigen (Preis/m²-Slider, Sortierung)
2. **Phase 2** — Leaflet Karten-Toggle (2.1) + Minimap (2.2), Keyboard Nav (2.7)
3. **Phase 3** — Preishistorie-Chart (2.4), Trendanalyse (3.2)
