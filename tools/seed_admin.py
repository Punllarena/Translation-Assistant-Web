"""Create the first admin account: python -m tools.seed_admin --email ..."""

import argparse
import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db import SessionLocal
from api.models import Profile, User
from api.security import hash_password

MIN_PASSWORD = 12


def create_admin(db: Session, email: str, password: str) -> User:
    email = email.strip().lower()
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise ValueError(f"user {email} already exists")
    user = User(email=email, password_hash=hash_password(password), is_admin=True)
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id, name="default", is_default=True))
    db.flush()
    return user


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
