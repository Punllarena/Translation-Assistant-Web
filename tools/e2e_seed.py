"""Reset the Playwright database and seed one user and one chapter.

    TA_DATABASE_URL=postgresql+psycopg://ta:ta@localhost:5432/ta_e2e python -m tools.e2e_seed
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from tools.seed_admin import create_admin

EMAIL, PASSWORD = "e2e@example.com", "e2e-password-123"
TM_LINE = "記憶語です。"
LINES = ["一行目です。", "二行目です。", "三行目です。"]


def main() -> None:
    url = make_url(os.environ["TA_DATABASE_URL"])
    if not (url.database or "").endswith("_e2e"):
        raise SystemExit(f"refusing to reset {url.database!r}: the name must end in _e2e")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()
    root = Path(__file__).resolve().parent.parent
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, cwd=root)

    from api.db import SessionLocal
    from api.library import write_lines
    from api.models import Document, Series

    with SessionLocal() as db:
        user = create_admin(db, EMAIL, PASSWORD)
        doc = Document(user_id=user.id, title="E2E chapter")
        db.add(doc)
        db.flush()
        write_lines(db, doc.id, [
            {"line_number": i, "prefix": "%", "raw_text": raw, "translated_text": ""}
            for i, raw in enumerate(LINES)
        ])
        # tm.spec's own chapter pair: they share TM_LINE, and 記憶語 occurs nowhere else, so the
        # profile-wide glossary entry that spec adds cannot change any other spec's text
        for title, translated in (("Memory source", "Remembered translation."), ("TM target", "")):
            other = Document(user_id=user.id, title=title)
            db.add(other)
            db.flush()
            write_lines(db, other.id, [
                {"line_number": 0, "prefix": "%", "raw_text": TM_LINE,
                 "translated_text": translated},
            ])
        # series spec: 太郎 occurs only here, so its glossary entry cannot change other specs' text
        series = Series(user_id=user.id, title="E2E series")
        db.add(series)
        db.flush()
        for order, (title, raw, translated) in enumerate((
            ("Series one", "太郎が来た。", "Tarou came."),
            ("Series two", "太郎が笑った。", "Tarou laughed."),
        )):
            ch = Document(user_id=user.id, title=title, series_id=series.id, series_order=order)
            db.add(ch)
            db.flush()
            write_lines(db, ch.id, [
                {"line_number": 0, "prefix": "%", "raw_text": raw, "translated_text": translated},
            ])
        db.commit()


if __name__ == "__main__":
    main()
