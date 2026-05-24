# Design: Discover — URL-Validierung + URL-Link im Frontend

**Datum:** 2026-05-24  
**Status:** Approved  
**Scope:** `app/web/api/sources.py` (Backend) + `frontend/src/components/settings/SourcesTab.tsx` (Frontend)

---

## Problem

1. **Halluzination:** `/api/sources/discover` fragt Claude nach Immobilien-Portalen für die Region Tutzing/Starnberger See. Claude gibt URLs aus dem Trainings-Wissen zurück — diese können falsch geschrieben, nicht mehr aktiv oder schlicht erfunden sein. Die Vorschläge werden nie validiert bevor sie dem User angezeigt werden.

2. **Fehlender URL-Link:** Die `DiscoverFlow`-Komponente zeigt `name` und `description` jedes Vorschlags, aber die `url` wird nur intern für `createSource()` verwendet — nie angezeigt. Der User kann vor dem Hinzufügen nicht prüfen, welche URL er gerade akzeptiert.

---

## Entscheidungen

- **Nicht erreichbare URLs:** Still rausfiltern — nicht mit Warnung anzeigen. User sieht nur verifizierte Vorschläge.
- **Validierungsmethode:** HTTP HEAD (Fallback GET), Timeout 5 s, Redirect-Follow. Nicht erreichbar = alles außer Status < 400.
- **Parallelisierung:** `asyncio.gather()` — alle URLs gleichzeitig prüfen, kein sequentielles Warten.

---

## Backend — `app/web/api/sources.py`

### Änderung an `discover_sources()`

Nach dem Claude-Call und JSON-Parse wird jeder Vorschlag mit einer URL-Validierungsfunktion geprüft:

```python
async def _url_reachable(url: str) -> bool:
    try:
        async with httpx.AsyncClient(
            timeout=5.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; immo-radar/1.0)"},
            follow_redirects=True,
        ) as client:
            resp = await client.head(url)
            if resp.status_code < 400:
                return True
            # Some servers reject HEAD — retry with GET
            resp = await client.get(url)
            return resp.status_code < 400
    except Exception:
        return False
```

In `discover_sources()`, nach `json.loads(...)`:

```python
reachable_flags = await asyncio.gather(*[_url_reachable(s["url"]) for s in suggestions])
suggestions = [s for s, ok in zip(suggestions, reachable_flags) if ok]
return DiscoverResult(suggestions=suggestions, error=None)
```

`asyncio` ist in Python stdlib, kein neuer Import nötig außer `import asyncio`.

### Kein Schema-Change, keine DB-Änderung

`DiscoverResult` und `DiscoverSuggestion` bleiben unverändert.

---

## Frontend — `frontend/src/components/settings/SourcesTab.tsx`

### Änderung in `DiscoverFlow` Render

Jeder Vorschlag bekommt unter der Description eine klickbare URL-Zeile:

**Vorher:**
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
    className="text-xs text-[--accent] hover:underline truncate block"
    onClick={e => e.stopPropagation()}
  >
    {s.url.replace(/^https?:\/\/(www\.)?/, '')}
  </a>
</div>
```

Die URL wird display-seitig auf `domain.de/pfad` gekürzt (Schema und `www.` entfernt) — der Link öffnet aber die vollständige URL.

---

## Nicht im Scope

- Kein Caching der Validierungsergebnisse (Discover wird selten aufgerufen)
- Kein Retry-Mechanismus wenn alle URLs ungültig sind (leere Liste ist valides Ergebnis)
- Kein Dark Mode (per DESIGN.md: noch nicht definiert)
- Keine Änderung am Prompt an Claude

---

## Teststrategie

- Backend: `verify_source`-Script kann nicht direkt genutzt werden (kein Scraper-Test). Manuell: Dashboard öffnen → Sources-Tab → "Neue Quellen entdecken" → prüfen ob nur erreichbare URLs zurückkommen.
- Frontend: Browser-Test — URL sichtbar, Link öffnet neue Tab, URL korrekt gekürzt.
