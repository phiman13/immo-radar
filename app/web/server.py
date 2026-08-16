from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.db import init_db
from app.web.api import listings, settings, sources, system
from app.web.api import telegram as telegram_api

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Immo-Radar Tutzing")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://100.115.184.3:8001"],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

app.include_router(listings.router, prefix="/api/listings", tags=["listings"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(sources.router, prefix="/api/sources", tags=["sources"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(telegram_api.router, prefix="/api/telegram", tags=["telegram"])

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

_dist_dir = BASE_DIR / "static" / "dist"
if _dist_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_dist_dir / "assets")), name="spa-assets")

# HER-820: index.html referenziert bei jedem Build neu gehashte /assets/*-
# Dateien; ohne explizites no-cache kann ein Browser (heuristisches Caching
# via Last-Modified/ETag) nach einem Deploy ein altes index.html
# weiterverwenden, das auf inzwischen gelöschte Asset-Hashes zeigt (404).
# Die gehashten Assets selbst bleiben unbefristet cachebar -- ihr Dateiname
# ändert sich ja bei jeder inhaltlichen Änderung.
_SPA_INDEX_HEADERS = {"Cache-Control": "no-cache"}


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/", include_in_schema=False)
async def index():
    # HER-816: die frühere Jinja2-Fallback-Ansicht (index.html/detail.html,
    # eigene /listing/{id}-Routen mit eigenem require_auth-Check) war seit
    # dem SPA-Umbau ungepflegt und wurde von nichts im neuen Frontend mehr
    # verlinkt (React Router kennt keine /listing/:id-Route). Fällt der SPA-
    # Build, gilt derselbe simple Hinweis wie im Catch-all (spa_fallback).
    spa_index = BASE_DIR / "static" / "dist" / "index.html"
    if spa_index.exists():
        return FileResponse(str(spa_index), headers=_SPA_INDEX_HEADERS)
    return JSONResponse({"status": "API running, SPA not built yet"}, status_code=200)


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("static/"):
        raise HTTPException(status_code=404)
    spa_index = BASE_DIR / "static" / "dist" / "index.html"
    if spa_index.exists():
        return FileResponse(str(spa_index), headers=_SPA_INDEX_HEADERS)
    return JSONResponse({"status": "API running, SPA not built yet"}, status_code=200)
