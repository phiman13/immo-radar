#!/usr/bin/env python3
"""Reset enrich_attempts to 0 for all listings. Run once on VPS after deploying the enrich_attempts fix."""

from app.db import Listing, SessionLocal

with SessionLocal() as session:
    count = session.query(Listing).update({"enrich_attempts": 0})
    session.commit()
    print(f"Reset enrich_attempts for {count} listings.")
