from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import func

import app.db as db_module
from app.db import ApiUsage, Listing
from app.usage import tokens_to_usd

_background_tasks: set[asyncio.Task] = set()

router = APIRouter()


class JobInfo(BaseModel):
    id: str
    next_run: datetime | None = None


class SystemStatus(BaseModel):
    scheduler_running: bool
    jobs: list[JobInfo]
    listing_counts: dict[str, int]


@router.get("/status", response_model=SystemStatus)
def get_status(request: Request) -> SystemStatus:
    """Get system status: scheduler state, jobs, listing counts."""
    # Get scheduler from app state (if available)
    scheduler = getattr(request.app.state, "scheduler", None)

    running = False
    jobs = []
    if scheduler is not None:
        running = scheduler.running
        for job in scheduler.get_jobs():
            jobs.append(JobInfo(id=job.id, next_run=job.next_run_time))
    else:
        # Web container has no scheduler — infer liveness from last FetchRun
        from sqlalchemy import desc

        with db_module.SessionLocal() as _s:
            last_run = _s.query(db_module.FetchRun).order_by(desc(db_module.FetchRun.started_at)).first()
        if last_run is not None:
            age_s = (datetime.now(UTC) - last_run.started_at.replace(tzinfo=UTC)).total_seconds()
            running = age_s < 1800  # worker alive if ran within last 30 min

    # Count listings by status
    with db_module.SessionLocal() as session:
        total = session.query(Listing).count()
        # Count by status grouping
        status_counts = session.query(Listing.status, func.count(Listing.id)).group_by(Listing.status).all()

    listing_counts = {"total": total}
    for status, count in status_counts:
        key = status if status is not None else "neu"
        listing_counts[key] = count

    return SystemStatus(
        scheduler_running=running,
        jobs=jobs,
        listing_counts=listing_counts,
    )


class FetchRunOut(BaseModel):
    id: int
    source: str
    started_at: datetime
    finished_at: datetime | None
    listings_found: int
    listings_new: int
    error: str | None

    model_config = {"from_attributes": True}


@router.get("/fetch-runs", response_model=list[FetchRunOut])
def get_fetch_runs():
    with db_module.SessionLocal() as session:
        from sqlalchemy import desc

        runs = session.query(db_module.FetchRun).order_by(desc(db_module.FetchRun.started_at)).limit(50).all()
        return [FetchRunOut.model_validate(r) for r in runs]


class CostPeriod(BaseModel):
    usd: float
    calls: int
    input_tokens: int
    output_tokens: int


class CostsOut(BaseModel):
    last_24h: CostPeriod
    last_7d: CostPeriod
    breakdown_24h: dict[str, float]  # purpose -> usd


def _aggregate(rows: list) -> CostPeriod:
    if not rows:
        return CostPeriod(usd=0.0, calls=0, input_tokens=0, output_tokens=0)
    total_in = sum(r.input_tokens for r in rows)
    total_out = sum(r.output_tokens for r in rows)
    total_usd = sum(tokens_to_usd(r.model, r.input_tokens, r.output_tokens) for r in rows)
    return CostPeriod(
        usd=round(total_usd, 6),
        calls=len(rows),
        input_tokens=total_in,
        output_tokens=total_out,
    )


@router.get("/costs", response_model=CostsOut)
def get_costs() -> CostsOut:
    now = datetime.now(UTC)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)

    with db_module.SessionLocal() as session:
        rows_24h = session.query(ApiUsage).filter(ApiUsage.ts >= cutoff_24h).all()
        rows_7d = session.query(ApiUsage).filter(ApiUsage.ts >= cutoff_7d).all()

    breakdown: dict[str, float] = {}
    for purpose in ("enrichment", "analyze", "discover"):
        relevant = [r for r in rows_24h if r.purpose == purpose]
        breakdown[purpose] = round(
            sum(tokens_to_usd(r.model, r.input_tokens, r.output_tokens) for r in relevant), 6
        )

    return CostsOut(
        last_24h=_aggregate(rows_24h),
        last_7d=_aggregate(rows_7d),
        breakdown_24h=breakdown,
    )


@router.post("/crawl/trigger")
async def trigger_crawl(request: Request):
    """Trigger an immediate poll_and_notify run in the background."""
    from app.scheduler import poll_and_notify

    task = asyncio.create_task(poll_and_notify())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"status": "triggered"}
