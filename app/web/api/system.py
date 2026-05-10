from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import func

import app.db as db_module
from app.db import Listing

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


@router.post("/crawl/trigger")
async def trigger_crawl(request: Request):
    """Trigger an immediate poll_and_notify run in the background."""
    import asyncio

    from app.scheduler import poll_and_notify

    asyncio.create_task(poll_and_notify())
    return {"status": "triggered"}
