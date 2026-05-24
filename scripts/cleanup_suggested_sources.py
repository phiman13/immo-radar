"""Einmalige Bereinigung: Entfernt suggested-Quellen, deren URL nicht erreichbar ist."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import app.db as db_module
from app.web.api.sources import _url_reachable


async def main(yes: bool = False) -> None:
    with db_module.SessionLocal() as session:
        suggested = session.query(db_module.Source).filter(db_module.Source.source_type == "suggested").all()

        if not suggested:
            print("Keine suggested-Quellen in der DB.")
            return

        print(f"{len(suggested)} suggested-Quelle(n) gefunden. Prüfe Erreichbarkeit...")

        no_url = [s for s in suggested if not s.url]
        with_url = [s for s in suggested if s.url]

        if with_url:
            flags = await asyncio.gather(*[_url_reachable(s.url) for s in with_url])
            unreachable = [s for s, ok in zip(with_url, flags, strict=True) if not ok]
        else:
            unreachable = []

        to_delete = no_url + unreachable

        reachable_count = len(with_url) - len(unreachable)
        print(f"  ✓ Erreichbar:     {reachable_count}")
        print(f"  ✗ Nicht erreichbar / keine URL: {len(to_delete)}")

        if not to_delete:
            print("\nAlle Quellen erreichbar — nichts zu löschen.")
            return

        print("\nWird gelöscht:")
        for s in to_delete:
            print(f"  - {s.display_name!r:30s}  {s.url or '(keine URL)'}")

        if not yes:
            answer = input("\nLöschen? [j/N] ").strip().lower()
            if answer != "j":
                print("Abgebrochen.")
                return

        for s in to_delete:
            session.delete(s)
        session.commit()
        print(f"\n{len(to_delete)} Quelle(n) gelöscht.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", "-y", action="store_true", help="Nicht interaktiv fragen — direkt löschen")
    args = parser.parse_args()
    asyncio.run(main(yes=args.yes))
