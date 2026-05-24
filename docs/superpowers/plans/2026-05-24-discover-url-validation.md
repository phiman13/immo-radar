# Discover URL-Validierung + Frontend-Link — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Halluzinierte Quellen-Vorschläge aus `/discover` filtern durch HTTP-Validierung, und jede Vorschlags-Karte im Frontend mit klickbarer URL versehen.

**Architecture:** Backend-`discover_sources()` validiert nach dem Claude-Call jede vorgeschlagene URL parallel per HTTP HEAD (Fallback GET, Timeout 5 s) und filtert nicht erreichbare Vorschläge still aus. Frontend zeigt die URL als klickbaren Link in jeder Vorschlags-Karte.

**Tech Stack:** Python asyncio + httpx (bereits im Projekt), React/TypeScript + Tailwind CSS

---

## Dateien

| Datei | Änderung |
|---|---|
| `app/web/api/sources.py` | `import asyncio` ergänzen; `_url_reachable()` Helper hinzufügen; `discover_sources()` validiert + filtert nach Claude-Call |
| `tests/test_url_reachable.py` | Neu — pytest-Tests für `_url_reachable` mit gemocktem httpx |
| `frontend/src/components/settings/SourcesTab.tsx` | `DiscoverFlow` Render: URL-Link unter Description |

---

## Task 1: Backend — `_url_reachable` helper

**Files:**
- Modify: `app/web/api/sources.py` (Zeilen 1–11: Imports)
- Create: `tests/test_url_reachable.py`

- [ ] **Schritt 1: Test-Datei anlegen**

```python
# tests/test_url_reachable.py
from __future__ import annotations

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock


# Wir importieren die Funktion, nachdem sie in Task 1 implementiert ist
from app.web.api.sources import _url_reachable


@pytest.mark.asyncio
async def test_url_reachable_200():
    """HEAD 200 → reachable."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("app.web.api.sources.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await _url_reachable("https://example.de")
        assert result is True


@pytest.mark.asyncio
async def test_url_reachable_head_404_get_200():
    """HEAD 404 → retry GET → 200 → reachable."""
    head_resp = MagicMock()
    head_resp.status_code = 404
    get_resp = MagicMock()
    get_resp.status_code = 200

    with patch("app.web.api.sources.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(return_value=head_resp)
        mock_client.get = AsyncMock(return_value=get_resp)
        mock_client_cls.return_value = mock_client

        result = await _url_reachable("https://example.de")
        assert result is True


@pytest.mark.asyncio
async def test_url_reachable_both_fail():
    """HEAD 404 → GET 404 → not reachable."""
    fail_resp = MagicMock()
    fail_resp.status_code = 404

    with patch("app.web.api.sources.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(return_value=fail_resp)
        mock_client.get = AsyncMock(return_value=fail_resp)
        mock_client_cls.return_value = mock_client

        result = await _url_reachable("https://ghost-site.de")
        assert result is False


@pytest.mark.asyncio
async def test_url_reachable_connection_error():
    """Netzwerkfehler → not reachable (kein Exception-Propagation)."""
    with patch("app.web.api.sources.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client_cls.return_value = mock_client

        result = await _url_reachable("https://nowhere.invalid")
        assert result is False
```

- [ ] **Schritt 2: Tests laufen lassen — erwartet FAIL (ImportError)**

```bash
cd /Users/philippherrlich/Code/immo-radar
source .venv/bin/activate
pip install pytest pytest-asyncio --quiet
pytest tests/test_url_reachable.py -v 2>&1 | head -30
```

Erwartet: `ImportError: cannot import name '_url_reachable'`

- [ ] **Schritt 3: `asyncio` import + `_url_reachable` in `sources.py` hinzufügen**

Zeile 1–11 von `app/web/api/sources.py` — `import asyncio` ergänzen:

```python
from __future__ import annotations

import asyncio
import json
from datetime import datetime

import httpx
from anthropic import Anthropic
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import app.db as db_module
```

Dann nach Zeile 12 (`import app.db as db_module`) und vor `router = APIRouter()` — `_url_reachable` als neue Funktion einfügen:

```python
async def _url_reachable(url: str) -> bool:
    """Prüft per HTTP HEAD (Fallback GET) ob eine URL erreichbar ist."""
    try:
        async with httpx.AsyncClient(
            timeout=5.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; immo-radar/1.0)"},
            follow_redirects=True,
        ) as client:
            resp = await client.head(url)
            if resp.status_code < 400:
                return True
            # Manche Server lehnen HEAD ab (405) — mit GET nochmal versuchen
            resp = await client.get(url)
            return resp.status_code < 400
    except Exception:
        return False
```

- [ ] **Schritt 4: Tests nochmal laufen — erwartet PASS**

```bash
pytest tests/test_url_reachable.py -v
```

Erwartet:
```
PASSED tests/test_url_reachable.py::test_url_reachable_200
PASSED tests/test_url_reachable.py::test_url_reachable_head_404_get_200
PASSED tests/test_url_reachable.py::test_url_reachable_both_fail
PASSED tests/test_url_reachable.py::test_url_reachable_connection_error
4 passed
```

- [ ] **Schritt 5: Commit**

```bash
git add app/web/api/sources.py tests/test_url_reachable.py
git commit -m "feat(sources): _url_reachable helper mit Tests"
```

---

## Task 2: Backend — Validierung in `discover_sources()`

**Files:**
- Modify: `app/web/api/sources.py` (Zeilen 279–280: nach `json.loads`)

- [ ] **Schritt 1: `discover_sources` anpassen**

In `app/web/api/sources.py`, die Zeilen nach dem JSON-Parse ändern.

**Vorher (Zeilen 278–280):**
```python
        m = _re.search(r"\[.*\]", text, _re.DOTALL)
        suggestions = json.loads(m.group() if m else text)
        return DiscoverResult(suggestions=suggestions, error=None)
```

**Nachher:**
```python
        m = _re.search(r"\[.*\]", text, _re.DOTALL)
        suggestions = json.loads(m.group() if m else text)
        # Nur Vorschläge mit URL behalten, dann Erreichbarkeit prüfen
        with_url = [s for s in suggestions if s.get("url")]
        flags = await asyncio.gather(*[_url_reachable(s["url"]) for s in with_url])
        suggestions = [s for s, ok in zip(with_url, flags) if ok]
        return DiscoverResult(suggestions=suggestions, error=None)
```

- [ ] **Schritt 2: Ruff-Check**

```bash
ruff check app/web/api/sources.py
```

Erwartet: keine Ausgabe (keine Fehler)

- [ ] **Schritt 3: Lokaler Smoke-Test (optional, braucht .env)**

```bash
python -m scripts.run_web
# In anderem Terminal:
curl -s -X POST http://localhost:8000/api/sources/discover | python3 -m json.tool
```

Erwartet: JSON-Array mit Vorschlägen, jede URL ist tatsächlich erreichbar.

- [ ] **Schritt 4: Commit**

```bash
git add app/web/api/sources.py
git commit -m "feat(sources): discover filtert nicht erreichbare URLs per HTTP-Validierung"
```

---

## Task 3: Frontend — URL-Link in `DiscoverFlow`

**Files:**
- Modify: `frontend/src/components/settings/SourcesTab.tsx` (Zeilen 215–217)

- [ ] **Schritt 1: URL-Link in die Suggestion-Karte einbauen**

In `SourcesTab.tsx`, den Info-Block jeder Suggestion-Zeile ändern.

**Vorher (Zeilen 215–217):**
```tsx
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-[--fg]">{s.name}</p>
                <p className="text-xs text-[--muted] truncate">{s.description}</p>
              </div>
```

**Nachher:**
```tsx
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-[--fg]">{s.name}</p>
                <p className="text-xs text-[--muted] truncate">{s.description}</p>
                <a
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-[--accent] hover:underline truncate block mt-0.5"
                  onClick={e => e.stopPropagation()}
                >
                  {s.url.replace(/^https?:\/\/(www\.)?/, '')}
                </a>
              </div>
```

- [ ] **Schritt 2: TypeScript-Check**

```bash
cd /Users/philippherrlich/Code/immo-radar/frontend
npx tsc --noEmit
```

Erwartet: keine Ausgabe (kein Fehler)

- [ ] **Schritt 3: Frontend bauen**

```bash
npm run build
```

Erwartet: Build erfolgreich, kein Fehler.

- [ ] **Schritt 4: Manueller Browser-Test**

```bash
# Backend starten (anderes Terminal):
cd /Users/philippherrlich/Code/immo-radar && python -m scripts.run_web

# Frontend Dev-Server:
cd frontend && npm run dev
```

Öffne `http://localhost:5173` → Settings → Sources-Tab → "Neue Quellen für meine Region entdecken" klicken.

Prüfen:
- [ ] Jede Suggestion-Karte zeigt einen URL-Link unter der Description
- [ ] URL ist auf `domain.de/pfad` gekürzt (kein `https://www.`)
- [ ] Klick öffnet neuen Tab mit der richtigen URL
- [ ] "Aufnehmen"-Button funktioniert weiterhin

- [ ] **Schritt 5: Commit + Push**

```bash
cd /Users/philippherrlich/Code/immo-radar
git add frontend/src/components/settings/SourcesTab.tsx
git commit -m "feat(frontend): Discover-Vorschläge zeigen klickbaren URL-Link"
git push
```

---

## Task 4: Deploy

- [ ] **Deploy auf VPS**

```bash
bash scripts/deploy.sh
```

Erwartet: rsync + Docker build + `docker compose up --build` ohne Fehler.

- [ ] **Produktions-Smoke-Test**

```bash
curl -s -u admin:tutzing2026! -X POST https://immo.herrlich.dev/api/sources/discover | python3 -m json.tool
```

Erwartet: JSON-Array, alle URLs erreichbar (manuell stichprobenartig im Browser prüfen).
