from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, select

from app.db import FetchRun, Listing, SessionLocal, init_db
from app.web.api import listings, settings, sources, system
from app.web.api import telegram as telegram_api
from app.web.auth import require_auth

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

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


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/", include_in_schema=False)
async def index(
    request: Request,
    status_filter: str = "",
    min_score: int = 0,
):
    # Serve SPA if built
    spa_index = BASE_DIR / "static" / "dist" / "index.html"
    if spa_index.exists():
        return FileResponse(str(spa_index))
    # Fallback: legacy Jinja2 dashboard
    with SessionLocal() as session:
        q = select(Listing).where(Listing.is_active.is_(True))
        if status_filter:
            q = q.where(Listing.status == status_filter)
        if min_score > 0:
            q = q.where(Listing.ai_score >= min_score)
        q = q.order_by(desc(Listing.first_seen_at)).limit(200)
        listings_data = session.scalars(q).all()
        runs = session.scalars(select(FetchRun).order_by(desc(FetchRun.started_at)).limit(10)).all()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "listings": listings_data,
            "runs": runs,
            "status_filter": status_filter,
            "min_score": min_score,
        },
    )


@app.get("/listing/{listing_id}", response_class=HTMLResponse)
def detail(listing_id: int, request: Request, _: str = Depends(require_auth)):
    with SessionLocal() as session:
        listing = session.get(Listing, listing_id)
        if listing is None:
            raise HTTPException(404)
    return templates.TemplateResponse("detail.html", {"request": request, "listing": listing})


@app.post("/listing/{listing_id}/status")
def set_status(
    listing_id: int,
    new_status: str = Form(...),
    _: str = Depends(require_auth),
):
    with SessionLocal() as session:
        listing = session.get(Listing, listing_id)
        if listing is None:
            raise HTTPException(404)
        listing.status = new_status
        session.commit()
    return RedirectResponse(f"/listing/{listing_id}", status_code=303)


@app.post("/listing/{listing_id}/notes")
def set_notes(
    listing_id: int,
    notes: str = Form(""),
    _: str = Depends(require_auth),
):
    with SessionLocal() as session:
        listing = session.get(Listing, listing_id)
        if listing is None:
            raise HTTPException(404)
        listing.notes = notes
        session.commit()
    return RedirectResponse(f"/listing/{listing_id}", status_code=303)


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("static/"):
        raise HTTPException(status_code=404)
    spa_index = BASE_DIR / "static" / "dist" / "index.html"
    if spa_index.exists():
        return FileResponse(str(spa_index))
    return JSONResponse({"status": "API running, SPA not built yet"}, status_code=200)
