"""CLI: python -m tools.import_tadb --db ta.db --user you@example.com [--dry-run] [--force]"""

import argparse
from pathlib import Path

from sqlalchemy import select

from api.core.tadb_import import import_tadb
from api.db import SessionLocal
from api.models import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a desktop ta.db into ta-web")
    parser.add_argument("--db", required=True, type=Path, help="path to a copy of ta.db")
    parser.add_argument("--user", required=True, help="email of the destination account")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report counts, write nothing; allowed even when the account already has "
             "documents, so a second import can be inspected first",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="import even if this file was imported before or the account already has "
             "documents; chapters already present (same series and title) are skipped",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.user))
        if user is None:
            raise SystemExit(f"no such user: {args.user}")
        report = import_tadb(
            db, args.db, user.id, dry_run=args.dry_run, force=args.force
        )
        if args.dry_run:
            print("DRY RUN - nothing written")
        else:
            db.commit()
        print(report.summary())
        for message in report.messages:
            print(f"  ! {message}")
        if any(report.skipped.values()):
            raise SystemExit("incomplete: some rows were skipped (see messages above)")


if __name__ == "__main__":
    main()
