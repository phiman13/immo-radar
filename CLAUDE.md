# immo-radar

Immobilien-Aggregator für Tutzing (PLZ 82327 + 5 km). Scrapt Portale, bewertet Objekte per Claude, sendet Alerts via Telegram.

**VPS:** `root@89.167.67.26` | **Dashboard (Tailscale):** `http://100.115.184.3:8001` | Login: admin / tutzing2026!

---

## Struktur

```
app/
  sources/        Scraper: immoscout24.py, immowelt.py, kleinanzeigen.py, makler_*.py
  scoring/        ai_match.py (Claude Haiku), lage.py (regelbasiert), risk.py
  notify/         telegram.py
  pipeline.py     Haupt-Pipeline (run_all, run_profile)
  scheduler.py    APScheduler — Interval aus DB, ändert sich ohne Container-Restart
  db.py           SQLAlchemy + SQLite
  config.py       Pydantic Settings (aus .env)
scripts/
  verify_source.py   Selektoren testen ohne DB-Schreibzugriff
  run_once.py        Einzelner Crawl-Durchlauf (schreibt in DB)
  run_web.py         Dashboard lokal starten
```

## Key Commands

```bash
# Lokales Setup
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium

# Selektoren prüfen (read-only, kein DB-Write) — VOR Prod-Lauf!
python -m scripts.verify_source immoscout24
python -m scripts.verify_source kleinanzeigen

# Linting
ruff check .

# Dashboard lokal
python -m scripts.run_web   # → http://localhost:8000

# Deploy auf VPS
bash scripts/deploy.sh

# Logs auf VPS
ssh root@89.167.67.26 "cd /opt/immo-radar && docker-compose logs -f worker"
```

## Stack

Python 3.11 · FastAPI · Playwright (Chromium) · SQLite/SQLAlchemy · APScheduler · anthropic SDK · Telegram Bot API · Docker

## Besonderheiten

- Selektoren sind fragil — bei Änderungen zuerst `verify_source` prüfen, nie blind editieren
- `kleinanzeigen.py` nutzt Playwright (headless Chromium), die anderen sind HTTP-basiert (httpx + BS4)
- Scoring zweistufig: Lage-Score (regelbasiert) → AI-Match (Claude Haiku, nur bei Score ≥ Threshold)
- Docker-Image enthält Chromium → ~1 GB, Build dauert
- `.env` nie committen — Telegram-Token + Dashboard-Passwort drin
- `scripts/deploy.sh` nutzt rsync + SSH direkt auf 89.167.67.26 (kein Tailscale nötig)
