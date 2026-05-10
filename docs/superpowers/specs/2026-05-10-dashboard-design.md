# immo-radar Dashboard — Design Spec
**Datum:** 2026-05-10  
**Status:** Approved — v2 (überarbeitet 2026-05-10)  
**Autor:** Philipp Herrlich + Claude

---

## Kontext

immo-radar ist ein persönlicher Immobilien-Aggregator für die Region Tutzing am Starnberger See (PLZ 82327, ~5–10 km Radius). Das Tool scrapt 8+ Portale, bewertet Objekte per Claude Haiku und sendet Telegram-Alerts. Der einzige User ist Philipp selbst, der geduldig und methodisch eine Kauf-Immobilie sucht.

**Primäres Problem heute:** Kein nutzbares UI. Das existierende FastAPI/Jinja2-Dashboard ist zu rudimentär für echten Gebrauch. Suchprofil nur per `.env` änderbar. Keine Karte. Kein Preis/m². Keine Quellenverwaltung.

**Ziel:** Ein vollständig selbst-konfigurierbares, visuell hochwertiges Web-Dashboard als Single Point of Control — kein Code oder `.env`-Editing mehr nötig.

---

## Architektur

### Stack

| Schicht | Technologie |
|---|---|
| Backend | FastAPI (bestehend), erweitert um JSON-Endpoints |
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS v3 |
| State | TanStack Query (Server State) + Zustand (UI State) |
| Karte | Leaflet + react-leaflet |
| Charts | Recharts |
| Icons | Phosphor Icons |
| Animation | Framer Motion |
| DB | SQLite + SQLAlchemy (bestehend), neue Tabellen: `app_settings`, `sources` |

### Deployment

- Frontend wird per `vite build` in `app/web/static/dist/` gebaut
- Docker Build-Step führt `npm run build` aus (neues `frontend/` Verzeichnis)
- FastAPI serviert den Build als Static Files unter `/`
- API-Endpoints unter `/api/v1/`
- Keine zusätzlichen Container, kein nginx

### Settings-Persistenz

- Suchprofil und App-Einstellungen in neuer DB-Tabelle `app_settings` (Key-Value mit JSON-Values)
- Beim ersten Start: `.env`-Werte als Defaults importieren
- Danach: DB ist Source of Truth, `.env` dient nur als Fallback bei fehlendem Datenbankwert
- Kein Container-Restart nötig nach Einstellungsänderung — Scheduler liest Einstellungen live

---

## Design Direction

### Ästhetik: "Präzises Feldtagebuch"

Der User ist kein gehetzter Investor. Er sucht methodisch, lokal, geduldig. Das Interface soll sich anfühlen wie ein gut gemachtes persönliches Kartierungswerkzeug — präzise, ruhig, vertrauenswürdig. Nicht Business-Dashboard. Nicht Marketing-Website.

**3 Brand-Wörter:** methodisch · lokal · geduldig

### Theme

Hell. Property-Fotos brauchen weißen Hintergrund. Der User browsed tagsüber / am Wochenende mit Kaffee.

### Farben (OKLCH)

```css
--bg:          oklch(97% 0.006 120);   /* Warmweißes Papier */
--fg:          oklch(18% 0.010 240);   /* Tiefes Schiefer, kein Reinweiß */
--accent:      oklch(45% 0.130 150);   /* Tannenzapfen-Grün, geerdet */
--accent-muted:oklch(90% 0.040 150);   /* Accent-Tint für Backgrounds */
--border:      oklch(87% 0.010 120);   /* Subtile Linie */
--muted:       oklch(60% 0.008 240);   /* Sekundärtext */

/* Status */
--status-new:       oklch(58% 0.160 145);  /* Interessiert/Neu: Grün */
--status-maybe:     oklch(72% 0.150  75);  /* Vielleicht: Amber */
--status-rejected:  oklch(52% 0.180  25);  /* Abgelehnt: Rot */
--status-seen:      oklch(60% 0.008 240);  /* Gesehen: Grau */

/* AI Score */
--score-high:   oklch(55% 0.160 145);
--score-mid:    oklch(70% 0.150  75);
--score-low:    oklch(55% 0.160  25);
```

### Typografie

| Rolle | Font | Verwendung |
|---|---|---|
| Überschriften | **Bricolage Grotesque** | Seiten-Titel, Listing-Titel |
| Body | **Schibsted Grotesk** | Labels, Fließtext, UI |
| Zahlen/Preise | **Azeret Mono** | Preise, m², Score — immer tabellarisch |

Alle drei via Google Fonts. Kein Inter, Space Grotesk, DM Sans.

### Layout

- Schmale linke Sidebar (220px) + Hauptbereich + Slide-in Detailpanel (420px)
- Detailpanel öffnet sich ÜBER den Hauptbereich (kein Page-Wechsel, kein Modal)
- Mobile: Sidebar collapst zu Bottom Navigation

---

## Screen-Struktur

### 1. Listings (Hauptansicht `/`)

**Filterleiste** (sticky oben):
- Preis-Range Slider (Min/Max)
- m²-Range Slider
- Zimmer-Min (Segmented Control)
- AI-Score Threshold (0 / 50 / 70 / 80)
- Status-Filter (Chips: Alle / Neu / Interessant / Vielleicht / Gesehen / Abgelehnt)
- Quellen-Filter (Multi-Select Dropdown)
- Sortierung: Erst gesehen ↓, Preis ↑↓, Score ↓, Preis/m² ↑↓

**Listing-Karte** (asymmetrisches 2-Spalten-Layout):
- Links: Bild (16:9, lazy loaded) — "Neu"-Dot wenn seit letztem Besuch neu
- Rechts oben: Titel (Bricolage Grotesque), Lage-Pill (Tutzing / Feldafing etc.), Quelle-Badge
- Rechts Mitte: `2.450 €/m²` (Azeret Mono, prominent), `890.000 €`, `145 m²`, `4 Zi.`
- Rechts unten: AI-Score-Badge (Kreis mit Zahl + Farbe), Status-Chip, **"seit 12 Tagen"** (Time on Market)
- Hover: Quick-Actions erscheinen (Interessant / Abgelehnt / Exposé öffnen)
- Click: Detailpanel öffnet sich

**Karten-Ansicht** (Toggle zwischen Grid und Karte, oben rechts):
- Leaflet-Karte mit Pins für alle gefilterten Listings
- Pin-Farbe = Status (grün/amber/rot/grau)
- Pin-Klick → Detailpanel öffnet sich (gleiche Interaktion wie Grid)
- Listings ohne Koordinaten werden in einer Sidebar-Liste neben der Karte aufgelistet

**Detailpanel** (slide-in von rechts, 420px):
- Header: Titel + Preis + Preis/m² + **"seit X Tagen online"**
- Bild-Galerie (horizontal scroll)
- Adresse mit Karten-Minimap (Leaflet, nicht klickbar) — nur wenn Koordinaten vorhanden
- Alle Felder: Baujahr, Hausgeld, Energie-Klasse, Zimmer, m², Objekttyp
- **Duplikat-Hinweis** (falls gleiches Objekt auf anderen Portalen): "Auch bei ImmobilienScout24 und Riedel gesehen" (verlinkt)
- AI-Reasoning-Box (Text, nicht editierbar)
- Risiko-Flags (rote Pills) + Positiv-Flags (grüne Pills)
- Preishistorie (Recharts LineChart, nur wenn Änderungen vorhanden)
- Notizen-Textarea (auto-save nach 1s Debounce)
- Status-Selector (5 Optionen)
- CTA-Button: "→ Exposé öffnen" (öffnet URL im neuen Tab)

**Empty State:** Wenn Filter zu restriktiv → "Keine Objekte gefunden. Filter anpassen?" mit Reset-Link.

---

### 2. Suchprofil & Einstellungen (`/settings`)

**Tab-Navigation:** Suchprofil | Benachrichtigungen | Mechanik | Quellen

#### Tab: Suchprofil

- **Ort & Radius:** Leaflet-Karte mit draggablem Center-Pin + Radius-Kreis (Slider 1–20 km)
  - Adress-Suche (Nominatim/OpenStreetMap Geocoding, kein Google Maps API-Key nötig)
  - Automatische Aktualisierung der Erlaubten-Orte-Liste basierend auf Radius
  - Manuelle Whitelist-Erweiterung: "Weitere Orte / PLZ zulassen" (Tags-Input)
- **Budget:** Dual-Handle-Slider (0 – 5.000.000 €) mit Direkteingabe
- **Größe:** Dual-Handle-Slider (m²)
- **Zimmer:** Stepper (0.5er Schritte)
- **Objekttypen:** Checkboxes (Wohnung, Haus, DHH, Reihenhaus, Grundstück)
- **Baujahr ab:** Slider (1900 – 2030)

#### Tab: Benachrichtigungen

- Telegram Bot Token (masked Input + "Verbindung testen"-Button)
- Telegram Chat ID (masked Input)
- Score-Threshold für Alerts (Slider: 0 = alle, 70 = nur gute)
- Benachrichtigungs-Vorschau: zeigt wie eine Telegram-Nachricht aussehen würde
- "Test-Nachricht senden"-Button

#### Tab: Mechanik

- Poll-Intervall (Slider: 5 / 10 / 15 / 30 / 60 Minuten)
- Enrichment-Intervall (Slider: 30 / 60 / 120 Minuten)
- Junk-Keywords verwalten (Tag-Editor: Keywords die Inserate ausschließen)
- Duplikat-Fenster (wie viele Tage bis ein Inserat als "neu" gilt)

#### Tab: Quellen

Zweigeteilt:

**Aktive Quellen** (Tabelle):
| Quelle | Status | Letzter Crawl | Gefunden | Aktiv |
|---|---|---|---|---|
| ImmobilienScout24 | ✓ OK | vor 8 Min | 42 | Toggle |
| kleinanzeigen.de | ✓ OK | vor 8 Min | 54 | Toggle |
| Riedel Immobilien | ✓ OK | vor 8 Min | 226 | Toggle |
| … | | | | |

- Toggle: deaktiviert Quelle (wird beim nächsten Crawl übersprungen)
- "Jetzt crawlen"-Button pro Quelle

**Neue Quelle hinzufügen:**

```
┌─────────────────────────────────────────────────────────┐
│  URL eingeben:  [ https://makler-xyz.de/immobilien ]    │
│                                              [Analysieren] │
│                                                          │
│  Oder:  [✨ Neue Quellen für meine Region entdecken]    │
└─────────────────────────────────────────────────────────┘
```

**Ablauf "URL analysieren":**
1. User gibt URL ein → klickt "Analysieren"
2. Loading-State: "Claude analysiert die Seite…" (Skeleton)
3. Preview: "5 Inserate gefunden. Beispiel: 'Doppelhaushälfte Tutzing, 890.000 €, 145 m²'"
4. Qualitätsindikator: Welche Felder erkannt (Preis ✓, m² ✓, Adresse ✗, Bilder ✓)
5. User gibt Quelle einen Namen → klickt "Aufnehmen"
6. Adapter-Code wird generiert, in DB gespeichert, Quelle aktiv

**Ablauf "Region entdecken":**
1. Klick auf Button → Claude-Agent startet
2. Live-Log: "Suche nach Maklern in Tutzing… 3 gefunden. Prüfe starnberg-immobilien.de…"
3. Ergebnisliste: 3–8 vorgeschlagene Quellen mit Preview-Count
4. User wählt aus (Checkboxes) → "Ausgewählte aufnehmen"

---

### 3. System-Status (`/system`)

- **Crawl-History:** Tabelle der letzten 20 FetchRuns (Quelle, Start, Dauer, Gefunden, Neue, Fehler)
- **Fehler-Log:** Letzte 10 Fehler mit Quelle + Message (rot, aufklappbar)
- **Statistiken:** Gesamt-Listings, Aktive Listings, Notified, Durchschn. Score, Listings heute
- **Scheduler-Status:** Nächster Poll in X Minuten (Live-Countdown)
- **"Jetzt alles crawlen"-Button** (triggert `poll_and_notify` sofort via API-Endpoint)
- **DB-Größe** und letztes Backup-Datum (nice to have)

---

## Feature-Backlog (priorisiert)

### Pre-Phase 1 — Bugfixes (sofort, vor Dashboard-Bau)
| # | Bug | Aufwand | Auswirkung |
|---|---|---|---|
| B1 | `enrich_pending` Endlosschleife: Listings mit `ai_score=NULL` werden stündlich re-enriched weil API-Call scheitert ohne Retry-Limit — `enriched_attempts`-Zähler oder `enriched_at`-Timestamp einführen | S | API-Kosten-Verschwendung |
| B2 | `deploy.sh` nutzt `docker-compose` (V1, auf VPS kaputt) → auf `docker compose` (V2) umstellen | XS | Deploy-Prozess |
| B3 | AI-Enrichment-Ursache debuggen: Warum schlägt `score_listing` trotz gesetztem API-Key fehl? (Vermutlich Model-Name oder API-Quota) | S | AI-Scoring inaktiv |

### Phase 1 — Core Dashboard (Pflicht)
| # | Feature | Aufwand | Wert |
|---|---|---|---|
| 1.1 | React/Vite-Setup + FastAPI JSON-Endpoints | M | Basis |
| 1.2 | Listings-Ansicht mit Filterleiste | L | Hoch |
| 1.3 | Listing-Detailpanel (Slide-in) | M | Hoch |
| 1.4 | Preis/m² Berechnung überall | S | Hoch |
| 1.5 | **"Time on Market"** — `first_seen_at` als "seit X Tagen" auf Karte + Detail | S | Hoch |
| 1.6 | **"Neu seit letztem Besuch"-Badge** — localStorage-Timestamp, Dot auf neuen Listings | S | Hoch |
| 1.7 | Status-Management (5 Stufen) | S | Hoch |
| 1.8 | Settings: Suchprofil-Editor | M | Hoch |
| 1.9 | Settings: **Score-Threshold für Telegram** (hier, nicht Phase 2 — Spam-Risiko ohne!) | S | Kritisch |
| 1.10 | Settings: Telegram-Konfiguration + Test | S | Mittel |
| 1.11 | Settings: Quellen-Toggle (aktiv/inaktiv) | S | Mittel |
| 1.12 | System-Status-Seite | S | Mittel |
| 1.13 | Auth: bestehende HTTP-Basic-Auth erhalten | S | Pflicht |

### Phase 2 — Intelligenz (nach Phase 1)
| # | Feature | Aufwand | Wert |
|---|---|---|---|
| 2.1 | **Karten-Toggle in Listings** — Leaflet-Karte mit allen aktiven Listings als Pins (neben/statt Grid-Ansicht) | M | Hoch |
| 2.2 | Leaflet-Minimap im Detailpanel | S | Hoch |
| 2.3 | Ort/Radius-Picker mit Karte in Settings (Nominatim, mit 1s Debounce wegen Rate-Limit) | M | Hoch |
| 2.4 | Preishistorie-Chart (Recharts LineChart) | S | Mittel |
| 2.5 | **Cross-Portal-Duplikate** — semantisches Dedup (gleicher Titel + Preis ±5% = gleiche Immobilie), Hinweis im Detail-Panel: "Auch auf ImmobilienScout24 gesehen" | M | Mittel |
| 2.6 | Junk-Keyword-Editor | S | Mittel |
| 2.7 | **Keyboard-Navigation** — `j`/`k` Listings, `e` Exposé, `1`–`5` Status, `Esc` Panel schließen | S | Hoch |
| 2.8 | Manuelle Quelle hinzufügen (URL-Analyse via Claude) | L | Hoch |

### Phase 3 — Innovation (ambitioniert)
| # | Feature | Aufwand | Wert |
|---|---|---|---|
| 3.1 | Autonome Quellen-Entdeckung (Claude Agent) | XL | Hoch |
| 3.2 | Markt-Trendanalyse (Preis/m² über Zeit in Region) | M | Mittel |
| 3.3 | S-Bahn-Pendeldauer nach München (ÖPNV API) | S | Mittel |
| 3.4 | Bodenrichtwert auto-fetch (BORIS-Schnittstelle) | M | Mittel |
| 3.5 | Tägliche Digest-Telegram-Zusammenfassung | S | Mittel |
| 3.6 | Vergleichsansicht (2–3 Listings nebeneinander) | M | Mittel |
| 3.7 | Export als PDF-Report (für Bankgespräch) | M | Niedrig |

---

## Keyboard-Shortcuts (Phase 2)

| Taste | Aktion |
|---|---|
| `j` / `k` | Nächstes / vorheriges Listing |
| `e` | Exposé im neuen Tab öffnen |
| `1` – `5` | Status setzen (Neu / Interessant / Vielleicht / Gesehen / Abgelehnt) |
| `Esc` | Detailpanel schließen |
| `/` | Fokus auf Suchfeld / Filter |
| `m` | Zwischen Grid- und Kartenansicht wechseln |

---

## API-Endpoints (neu)

```
GET  /api/v1/listings          — gefilterte Listings (Query-Params: status, min_score, source, ...)
GET  /api/v1/listings/:id      — Listing-Detail
PATCH /api/v1/listings/:id     — Status, Notes updaten
GET  /api/v1/fetch-runs        — Crawl-History
POST /api/v1/crawl/trigger     — Sofort-Crawl anstoßen

GET  /api/v1/settings          — alle Settings als JSON
PATCH /api/v1/settings         — Settings updaten (live, kein Restart)

GET  /api/v1/sources           — alle konfigurierten Quellen
PATCH /api/v1/sources/:id      — Quelle aktivieren/deaktivieren
POST /api/v1/sources/analyze   — URL analysieren (Claude-Agent)
POST /api/v1/sources/discover  — Quellen für Region entdecken (Claude-Agent)

POST /api/v1/telegram/test     — Test-Nachricht senden

GET  /api/v1/listings/:id/duplicates  — Semantisch ähnliche Listings (cross-portal)
GET  /api/v1/stats                    — Aggregierte Statistiken für System-Status
WS   /api/v1/ws/events                — WebSocket für Live-Updates (neue Listings, Crawl-Ende)
```

---

## Neue DB-Tabellen

```python
class AppSetting(Base):
    __tablename__ = "app_settings"
    key: str           # z.B. "price_max", "telegram_score_threshold"
    value: str         # JSON-encoded
    updated_at: datetime

class Source(Base):
    __tablename__ = "sources"
    id: int
    name: str           # "Makler XYZ"
    url: str            # "https://makler-xyz.de/immobilien"
    adapter_code: str   # generierter Python-Code (für KI-Quellen)
    adapter_type: str   # "builtin" | "generated"
    is_active: bool
    last_crawl_at: datetime
    last_error: str | None
    created_at: datetime
    # Sicherheit: generierter Code wird vor Aktivierung dem User zur Bestätigung gezeigt
    # und im UI als "ungeprüft" markiert bis manuell freigegeben

# Listings-Tabelle: neues Feld
# enrich_attempts: int = 0  — verhindert Endlosschleife bei API-Fehlern (max. 3 Versuche)
# Duplikat-Verknüpfung via neue Join-Tabelle:

class ListingDuplicate(Base):
    __tablename__ = "listing_duplicates"
    listing_id_a: int   # FK → listings.id
    listing_id_b: int   # FK → listings.id
    similarity: float   # 0.0–1.0
    detected_at: datetime
```

---

## Design-Constraints (aus aktiven Skills)

- **Keine Emojis als Icons** — ausschließlich Phosphor Icons (SVG)
- **Keine border-left Stripe-Cards** — Status via Background-Tint oder Badge
- **Kein Gradient-Text**
- **Keine reinen Schwarz-/Weiß-Werte** — immer OKLCH mit leichter Tönung
- **Tabellarische Zahlen** — Azeret Mono für alle Preise/Metriken
- **min-h-[100dvh]** statt h-screen für Full-Height-Sections
- **whileInView mit once: true** für alle Scroll-Animationen
- **prefers-reduced-motion** respektieren
- **WCAG AA** — Kontrast ≥ 4.5:1 für Body-Text

---

## Offene Fragen (geklärt)

- ✅ Stack: React + Vite + FastAPI (kein Next.js)
- ✅ Theme: Hell
- ✅ Auth: bestehende HTTP-Basic bleibt
- ✅ Deployment: Static Files aus FastAPI, kein extra Container
- ✅ Settings: DB statt .env, live ohne Restart
- ✅ Quellen-Discovery: Claude-Agent-Ansatz (generierter Code wird vor Aktivierung angezeigt)
- ✅ Ort: Leaflet-Picker mit Nominatim Geocoding (kein Google API-Key, 1s Debounce)
- ✅ Score-Threshold: Phase 1 (nicht 2) — kritisch gegen Telegram-Spam
- ✅ Karten-Toggle: Phase 2a — Leaflet-Karte mit allen Listings als Pins
- ✅ Duplikat-Detection: Phase 2 — semantisch, cross-portal
- ✅ Keyboard-Navigation: Phase 2 — j/k/e/1-5/Esc/m
