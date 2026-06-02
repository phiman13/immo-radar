from __future__ import annotations

import asyncio
import json
from datetime import datetime

import httpx
from anthropic import Anthropic
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import app.db as db_module


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


router = APIRouter()

DEFAULT_SOURCES = [
    # blocked: bot-protected on all endpoints incl. RSS (401/404)
    {"name": "immoscout24", "display_name": "ImmoScout24", "source_type": "blocked"},
    {"name": "immowelt", "display_name": "Immowelt", "source_type": "blocked"},
    {"name": "sparkasse_immo", "display_name": "Sparkasse Immobilien", "source_type": "blocked"},
    # active scrapers
    {"name": "kleinanzeigen", "display_name": "Kleinanzeigen"},
    {"name": "bs_immo", "display_name": "BS Immo"},
    {"name": "riedel", "display_name": "Riedel Immobilien"},
    {"name": "starnberg_bader", "display_name": "Starnberg Immo"},
    {"name": "tutzing24", "display_name": "Tutzing24"},
]

# Registry names changed — migrate existing DB rows so last_run lookup works.
_NAME_MIGRATIONS = {
    "makler_bsimmo": "bs_immo",
    "makler_riedel": "riedel",
    "makler_starnberg_immo": "starnberg_bader",
}


def _seed_sources(session) -> None:
    """Upsert default sources; handles name migrations and blocked-status updates."""
    for old, new in _NAME_MIGRATIONS.items():
        row = session.query(db_module.Source).filter(db_module.Source.name == old).first()
        if row:
            row.name = new
    session.flush()

    for src in DEFAULT_SOURCES:
        existing = session.query(db_module.Source).filter(db_module.Source.name == src["name"]).first()
        if existing is None:
            session.add(db_module.Source(**src))
        elif "source_type" in src:
            existing.source_type = src["source_type"]
    session.commit()


class SourceOut(BaseModel):
    id: int
    name: str
    display_name: str
    enabled: bool
    last_run: datetime | None
    listing_count: int
    url: str | None
    source_type: str = "builtin"

    model_config = {"from_attributes": True}


class SourcePatch(BaseModel):
    enabled: bool | None = None
    display_name: str | None = None


@router.get("/", response_model=list[SourceOut])
def get_sources():
    from sqlalchemy import func  # noqa: PLC0415
    from sqlalchemy import select as sa_select

    with db_module.SessionLocal() as session:
        _seed_sources(session)
        sources = session.query(db_module.Source).order_by(db_module.Source.name).all()

        last_runs = dict(
            session.execute(
                sa_select(db_module.FetchRun.source, func.max(db_module.FetchRun.finished_at)).group_by(
                    db_module.FetchRun.source
                )
            ).fetchall()
        )
        listing_counts = dict(
            session.execute(
                sa_select(db_module.Listing.source, func.count())
                .where(db_module.Listing.is_active.is_(True))
                .group_by(db_module.Listing.source)
            ).fetchall()
        )

        return [
            SourceOut(
                id=s.id,
                name=s.name,
                display_name=s.display_name,
                enabled=s.enabled,
                last_run=last_runs.get(s.name),
                listing_count=listing_counts.get(s.name, 0),
                url=s.url,
                source_type=s.source_type or "builtin",
            )
            for s in sources
        ]


@router.patch("/{source_id}", response_model=SourceOut)
def patch_source(source_id: int, body: SourcePatch):
    with db_module.SessionLocal() as session:
        source = session.get(db_module.Source, source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        if body.enabled is not None:
            source.enabled = body.enabled
        if body.display_name is not None:
            source.display_name = body.display_name
        session.commit()
        session.refresh(source)
        return SourceOut.model_validate(source)


class AnalyzeRequest(BaseModel):
    url: str


class FieldDetection(BaseModel):
    price: bool
    qm: bool
    rooms: bool
    address: bool
    images: bool


class AnalyzeResult(BaseModel):
    url: str
    listing_count: int
    example_title: str | None
    example_price: str | None
    fields: FieldDetection
    error: str | None


@router.post("/analyze", response_model=AnalyzeResult)
async def analyze_source(body: AnalyzeRequest) -> AnalyzeResult:
    # 1. Fetch the URL
    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; immo-radar/1.0)"},
            follow_redirects=True,
        ) as client:
            resp = await client.get(body.url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        return AnalyzeResult(
            url=body.url,
            listing_count=0,
            example_title=None,
            example_price=None,
            fields=FieldDetection(price=False, qm=False, rooms=False, address=False, images=False),
            error=f"Seite nicht erreichbar: {e}",
        )

    # 2. Truncate HTML to avoid token overflow
    html_excerpt = html[:12_000]

    # 3. Ask Claude
    from app.config import settings as _settings  # noqa: PLC0415

    anthropic_client = Anthropic(api_key=_settings.anthropic_api_key)
    prompt = f"""Du analysierst eine deutsche Immobilien-Website.

HTML-Ausschnitt:
<html>
{html_excerpt}
</html>

Antworte NUR mit einem JSON-Objekt (kein Markdown, kein Text drumherum):
{{
  "listing_count": <Schätzung wie viele Inserate auf der Seite zu sehen sind, 0 wenn keine>,
  "example_title": <Titel des ersten Inserats oder null>,
  "example_price": <Preis des ersten Inserats als String z.B. "450.000 €" oder null>,
  "fields": {{
    "price": <true wenn Preise erkennbar>,
    "qm": <true wenn m² erkennbar>,
    "rooms": <true wenn Zimmeranzahl erkennbar>,
    "address": <true wenn Adresse/Ort erkennbar>,
    "images": <true wenn Bilder vorhanden>
  }}
}}"""

    try:
        msg = anthropic_client.messages.create(
            model=_settings.ai_model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        from app.usage import log_usage  # noqa: PLC0415

        log_usage(
            model=_settings.ai_model,
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            purpose="analyze",
        )
        text = msg.content[0].text.strip() if msg.content else ""
        # Claude wraps JSON sometimes in ```-blocks — extract the object
        import re as _re  # noqa: PLC0415

        m = _re.search(r"\{.*\}", text, _re.DOTALL)
        data = json.loads(m.group() if m else text)
        return AnalyzeResult(
            url=body.url,
            listing_count=data.get("listing_count", 0),
            example_title=data.get("example_title"),
            example_price=data.get("example_price"),
            fields=FieldDetection(**data.get("fields", {})),
            error=None,
        )
    except Exception as e:
        return AnalyzeResult(
            url=body.url,
            listing_count=0,
            example_title=None,
            example_price=None,
            fields=FieldDetection(price=False, qm=False, rooms=False, address=False, images=False),
            error=f"Claude-Analyse fehlgeschlagen: {e}",
        )


class DiscoverResult(BaseModel):
    suggestions: list[dict]  # [{name, url, description}]
    error: str | None


@router.post("/discover", response_model=DiscoverResult)
async def discover_sources() -> DiscoverResult:
    from app.config import settings as _settings  # noqa: PLC0415

    anthropic_client = Anthropic(api_key=_settings.anthropic_api_key)
    prompt = (
        "Schlage Immobilien-Portale und Makler-Websites für die Region"
        " Tutzing / Starnberger See (Bayern, Deutschland) vor,"
        " die noch NICHT in dieser Liste sind:\n"
        "- ImmoScout24 (immoscout24.de)\n"
        "- Immowelt (immowelt.de)\n"
        "- Kleinanzeigen (kleinanzeigen.de)\n"
        "- BS Immo (bsimmo.de)\n"
        "- Riedel Immobilien\n"
        "- Starnberg Immo\n"
        "- Sparkasse Immobilien\n"
        "- Tutzing24\n\n"
        "Antworte NUR mit einem JSON-Array (kein Markdown):\n"
        "[\n"
        '  {"name": "<Anzeigename>", "url": "<URL>", "description": "<1 Satz warum relevant>"},\n'
        "  ...\n"
        "]\n"
        "Maximal 6 Vorschläge. Nur echte, existierende Websites."
    )

    try:
        msg = anthropic_client.messages.create(
            model=_settings.ai_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        from app.usage import log_usage  # noqa: PLC0415

        log_usage(
            model=_settings.ai_model,
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            purpose="discover",
        )
        text = msg.content[0].text.strip()
        # Claude sometimes wraps JSON in ```-blocks — extract the array
        import re as _re  # noqa: PLC0415

        m = _re.search(r"\[.*\]", text, _re.DOTALL)
        suggestions = json.loads(m.group() if m else text)
        # Nur Vorschläge mit URL behalten, dann Erreichbarkeit prüfen
        with_url = [s for s in suggestions if s.get("url")]
        flags = await asyncio.gather(*[_url_reachable(s["url"]) for s in with_url])
        suggestions = [s for s, ok in zip(with_url, flags, strict=True) if ok]
        return DiscoverResult(suggestions=suggestions, error=None)
    except Exception as e:
        return DiscoverResult(suggestions=[], error=str(e))


class SourceCreate(BaseModel):
    name: str
    display_name: str
    url: str | None = None
    source_type: str = "suggested"


@router.post("/", response_model=SourceOut, status_code=201)
def create_source(body: SourceCreate):
    with db_module.SessionLocal() as session:
        existing = session.query(db_module.Source).filter(db_module.Source.name == body.name).first()
        if existing:
            raise HTTPException(status_code=409, detail="Quelle bereits vorhanden")
        source = db_module.Source(
            name=body.name,
            display_name=body.display_name,
            url=body.url,
            source_type=body.source_type,
            enabled=False,
        )
        session.add(source)
        session.commit()
        session.refresh(source)
        return SourceOut.model_validate(source)
