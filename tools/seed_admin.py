"""Create the first admin account: python -m tools.seed_admin --email ..."""

import argparse
import getpass

from api.accounts import create_admin
from api.db import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first admin account")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat: "):
        raise SystemExit("passwords do not match")
    with SessionLocal() as db:
        try:
            user = create_admin(db, args.email, password)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        db.commit()
        print(f"created admin {user.email} (id={user.id})")


if __name__ == "__main__":
    main()
