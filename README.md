# Immo-Radar Tutzing

Aggregator + Alerter für Immobilien-Kaufobjekte in PLZ 82327 + 5 km Radius.

## Quellen (Tier 1)

- ImmoScout24 (Playwright)
- Immowelt (httpx)
- Kleinanzeigen (Playwright, Cloudflare-Schutz)
- Sparkasse Immobilien
- Riedel Immobilien (lokaler Makler Tutzing)

## Lokales Setup

```bash
cd immo-radar
python -m venv .venv && source .venv/bin/activate
pip install -e .
playwright install chromium

cp .env.example .env
# .env editieren — siehe unten

# Eine Crawler-Runde testen
python -m scripts.verify_source kleinanzeigen
python -m scripts.run_once

# Dashboard starten
python -m scripts.run_web
# → http://localhost:8000  (admin / changeme)

# Worker dauerhaft laufen lassen
python -m app.main
```

## .env — wichtige Variablen

```
SEARCH_CENTER_LAT=47.9095          # Tutzing-Zentrum
SEARCH_CENTER_LON=11.2783
SEARCH_RADIUS_KM=5
PRICE_MIN=400000
PRICE_MAX=1500000
QM_MIN=70

TELEGRAM_BOT_TOKEN=                # @BotFather → /newbot
TELEGRAM_CHAT_ID=                  # @userinfobot

ANTHROPIC_API_KEY=                 # console.anthropic.com
AI_MODEL=claude-haiku-4-5-20251001

DASHBOARD_USER=admin
DASHBOARD_PASSWORD=changeme
```

## Deployment auf Hetzner VPS

```bash
# Auf dem VPS (Ubuntu 22.04+):
sudo apt update && sudo apt install -y docker.io docker-compose-v2
git clone <repo> immo-radar && cd immo-radar
cp .env.example .env && nano .env
nano Caddyfile      # Domain eintragen
docker compose up -d --build
docker compose logs -f worker
```

## Architektur

```
[Scheduler alle 10 min]
        │
        ▼
[Source Adapters: immoscout24, immowelt, kleinanzeigen, …]
        │  RawListing
        ▼
[_matches_profile filter]
        │
        ▼
[SQLite upsert mit dedup_hash + History-Tracking]
        │
        ▼
[Enrich: risk_flags, ortsteil, ai_score (Claude Haiku)]
        │
        ▼
[Telegram Push] + [Web Dashboard]
```

## Caveat: Selektoren brauchen Live-Verifikation

Die Source-Adapter wurden gegen typische Markup-Muster geschrieben. Vor erstem Produktiv-Lauf:

```bash
python -m scripts.verify_source immoscout24
```

Wenn die Output-Zeilen leer / `?` sind, müssen die CSS-Selektoren in `app/sources/<name>.py` an das aktuelle Live-HTML angepasst werden.
