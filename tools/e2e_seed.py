"""Reset the Playwright database and seed one user and one chapter.

    TA_DATABASE_URL=postgresql+psycopg://ta:ta@localhost:5432/ta_e2e python -m tools.e2e_seed
"""

import base64
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from api.accounts import create_admin

EMAIL, PASSWORD = "e2e@example.com", "e2e-password-123"
TM_LINE = "記憶語です。"
LINES = ["一行目です。", "二行目です。", "三行目です。"]
# A 1x1 PNG for series-page.spec's chapter image; nothing in these flows decodes it.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


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

    from sqlalchemy import func, update

    from api.db import SessionLocal
    from api.library import write_lines
    from api.models import Document, DocumentImage, Line, Series, User, Volume
    from api.models.ollama import OllamaChunk, OllamaQueueItem, OllamaSuggestion
    from api.ollama.work import raw_sha
    from api.security import hash_password

    with SessionLocal() as db:
        user = create_admin(db, EMAIL, PASSWORD)
        editor_series = Series(user_id=user.id, title="E2E editor series")
        tm_series = Series(user_id=user.id, title="E2E tm series")
        mt_series = Series(user_id=user.id, title="E2E mt series")
        yomitan_series = Series(user_id=user.id, title="Yomitan spec")
        db.add_all([editor_series, tm_series, mt_series, yomitan_series])
        db.flush()
        doc = Document(user_id=user.id, title="E2E chapter", series_id=editor_series.id)
        db.add(doc)
        db.flush()
        write_lines(db, doc.id, [
            {"line_number": i, "prefix": "%", "raw_text": raw, "translated_text": ""}
            for i, raw in enumerate(LINES)
        ])
        # editor.spec's spellcheck chapter: two misspellings it adds to the series and account lists
        spell_doc = Document(user_id=user.id, title="Spell target", series_id=editor_series.id)
        db.add(spell_doc)
        db.flush()
        write_lines(db, spell_doc.id, [
            {"line_number": 0, "prefix": "%", "raw_text": "綴りです。",
             "translated_text": "zorbleq quuxbarr"},
        ])
        # glossary.spec: its own series, no chapters, so the phrases it saves change no text
        db.add(Series(user_id=user.id, title="E2E glossary series"))
        # tm.spec's own chapter pair: they share TM_LINE, and 記憶語 occurs nowhere else, so the
        # glossary entry that spec adds to the tm series cannot change any other spec's text
        for title, translated in (("Memory source", "Remembered translation."), ("TM target", "")):
            other = Document(user_id=user.id, title=title, series_id=tm_series.id)
            db.add(other)
            db.flush()
            write_lines(db, other.id, [
                {"line_number": 0, "prefix": "%", "raw_text": TM_LINE,
                 "translated_text": translated},
            ])
        # series spec: its glossary entry for 太郎 lands in this series, whose chapters are its own
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
        # mt spec: 猫 occurs only here (JParser's sample dictionary has it)
        mt = Document(user_id=user.id, title="MT target", series_id=mt_series.id)
        db.add(mt)
        db.flush()
        write_lines(db, mt.id, [
            {"line_number": 0, "prefix": "%", "raw_text": "猫です。", "translated_text": ""},
        ])
        # dictionaries spec: ゆもたん語 occurs only here
        yom = Document(user_id=user.id, title="Yomitan target", series_id=yomitan_series.id)
        db.add(yom)
        db.flush()
        write_lines(db, yom.id, [
            {"line_number": 0, "prefix": "%", "raw_text": "ゆもたん語です", "translated_text": ""},
        ])
        # publish spec: its own series, with the WordPress fields already set
        pub = Series(user_id=user.id, title="E2E publish series",
                     wp_series_slug="e2e-publish", wp_series_title_short="E2EP")
        db.add(pub)
        db.flush()
        one = Document(user_id=user.id, title="Publish one", chapter_title="Publish one",
                       series_id=pub.id, series_order=1)
        db.add(one)
        db.flush()
        write_lines(db, one.id, [{"line_number": 0, "prefix": "%", "raw_text": "公開します。",
                                  "translated_text": "We publish."}])
        batch = Document(user_id=user.id, title="Batch target", chapter_title="Batch target",
                         series_id=pub.id, series_order=2)
        db.add(batch)
        db.flush()
        write_lines(db, batch.id, [{"line_number": 0, "prefix": "%", "raw_text": "一括です。",
                                    "translated_text": "In bulk."}])
        # stats spec: one translated line today, in its own series
        st = Series(user_id=user.id, title="E2E stats series")
        db.add(st)
        db.flush()
        stats_doc = Document(user_id=user.id, title="Stats one", series_id=st.id, series_order=1)
        db.add(stats_doc)
        db.flush()
        write_lines(db, stats_doc.id, [{"line_number": 0, "prefix": "%", "raw_text": "統計です。",
                                        "translated_text": "Stats."}])
        db.execute(update(Line).where(Line.document_id == stats_doc.id)
                   .values(translated_at=func.now()))
        # library.spec: a volume with two chapters and one loose chapter; nothing else opens it
        lib = Series(user_id=user.id, title="E2E library series")
        db.add(lib)
        db.flush()
        vol_a = Volume(series_id=lib.id, kind="", subtitle="Vol A", volume_order=1)
        db.add(vol_a)
        db.flush()
        for order, (title, volume_id) in enumerate((
            ("Lib one", vol_a.id), ("Lib two", vol_a.id), ("Lib loose", None),
        )):
            ch = Document(user_id=user.id, title=title, series_id=lib.id, volume_id=volume_id,
                          series_order=order)
            db.add(ch)
            db.flush()
            write_lines(db, ch.id, [{"line_number": 0, "prefix": "%", "raw_text": "図書です。",
                                     "translated_text": ""}])
        # import.spec: New volume → Import EPUB lands the book as a second volume here
        ev = Series(user_id=user.id, title="E2E epub volume series")
        db.add(ev)
        db.flush()
        db.add(Volume(series_id=ev.id, kind="", subtitle="Vol existing", volume_order=1))
        # volumes.spec: three numbered volumes, one chapter each; nothing else opens this series
        vn = Series(user_id=user.id, title="E2E volume naming series")
        db.add(vn)
        db.flush()
        for n in (1, 2, 3):
            v = Volume(series_id=vn.id, kind="Volume", volume_index=Decimal(n), volume_order=n)
            db.add(v)
            db.flush()
            ch = Document(user_id=user.id, title=f"Naming chapter {n}", series_id=vn.id,
                          volume_id=v.id, series_order=n)
            db.add(ch)
            db.flush()
            write_lines(db, ch.id, [{"line_number": 0, "prefix": "%", "raw_text": "巻です。",
                                     "translated_text": ""}])
        # chapter-title.spec: a chapter whose chapter_title (shown) differs from its title
        dt = Series(user_id=user.id, title="E2E display title series")
        db.add(dt)
        db.flush()
        ch = Document(user_id=user.id, title="原題の章", chapter_title="Shown chapter title",
                      series_id=dt.id, series_order=1)
        db.add(ch)
        db.flush()
        write_lines(db, ch.id, [{"line_number": 0, "prefix": "%", "raw_text": "題です。",
                                 "translated_text": ""}])
        # library-filters.spec: two series that differ in status and source, one chapter each
        for fs_title, fs_status, fs_source, fs_url in (
            ("Filter spec ongoing", "ongoing", "syosetu", "https://ncode.syosetu.com/n9999zz/"),
            ("Filter spec dropped", "dropped", "epub", None),
        ):
            fs = Series(user_id=user.id, title=fs_title, status=fs_status, source=fs_source,
                        syosetu_url=fs_url)
            db.add(fs)
            db.flush()
            ch = Document(user_id=user.id, title=f"{fs_title} chapter one", series_id=fs.id,
                          series_order=1)
            db.add(ch)
            db.flush()
            write_lines(db, ch.id, [{"line_number": 0, "prefix": "%", "raw_text": "絞込です。",
                                     "translated_text": ""}])
        # ollama.spec: line 1 is untranslated and holds a suggestion; the others are translated
        # so the card opens no stream. No Ollama credential, so Run now answers with the setup text.
        ol = Series(user_id=user.id, title="E2E ollama series")
        db.add(ol)
        db.flush()
        ol_doc = Document(user_id=user.id, title="Ollama target", series_id=ol.id, series_order=1)
        db.add(ol_doc)
        db.flush()
        ol_lines = ["彼女は笑った。", "二つ目です。", "三つ目です。"]
        write_lines(db, ol_doc.id, [
            {"line_number": i, "prefix": "%", "raw_text": raw,
             "translated_text": "" if i == 0 else f"Done {i}."}
            for i, raw in enumerate(ol_lines)
        ])
        chunk = OllamaChunk(
            user_id=user.id, series_id=ol.id, document_id=ol_doc.id, source="run", ok=True,
            clamped=False, depth=0, model="qwen3:14b", preset="medium", chunk_lines=3,
            context_lines=0, first_line=0, last_line=2, asked=3, prompt_tokens=412,
            output_tokens=331, eval_ms=8620, total_ms=9200,
            reasoning="Because the subject is she",
        )
        db.add(chunk)
        db.flush()
        first = db.query(Line).filter_by(document_id=ol_doc.id, line_number=0).one()
        db.add(OllamaSuggestion(line_id=first.id, chunk_id=chunk.id, text="She laughed.",
                                raw_sha=raw_sha(first.raw_text)))
        db.add(OllamaQueueItem(user_id=user.id, kind="series", series_id=ol.id,
                               document_ids=[], position=1))
        # editor-nav.spec: volume 1 holds two chapters; the first has author ruby and filler lines
        nav = Series(user_id=user.id, title="Nav series")
        db.add(nav)
        db.flush()
        nav_vol = Volume(series_id=nav.id, kind="Volume", volume_index=Decimal(1), volume_order=1)
        db.add(nav_vol)
        db.flush()
        nav_lines = {
            "Nav one": [
                "大(おお)きな夢(ゆめ)を見た。", "STATUS(ステータス)を開く。", "今日は晴れ。",
                *[f"行{n}。" for n in range(1, 21)],
            ],
            "Nav two": ["二話目です。"],
        }
        for order, (title, raws) in enumerate(nav_lines.items(), start=1):
            ch = Document(user_id=user.id, title=title, series_id=nav.id, volume_id=nav_vol.id,
                          series_order=order)
            db.add(ch)
            db.flush()
            write_lines(db, ch.id, [{"line_number": i, "prefix": "%", "raw_text": raw,
                                     "translated_text": ""} for i, raw in enumerate(raws)])
        # ... and volume 2 opens with a chapter that has no lines yet
        nav_vol2 = Volume(series_id=nav.id, kind="Volume", volume_index=Decimal(2), volume_order=2)
        db.add(nav_vol2)
        db.flush()
        db.add(Document(user_id=user.id, title="Nav blank", series_id=nav.id, volume_id=nav_vol2.id,
                        series_order=len(nav_lines) + 1))
        # series-page.spec: one volume, three chapters — a plain one, a 200-character title and
        # one holding an image; nothing else opens this series
        sp = Series(user_id=user.id, title="Series page spec")
        db.add(sp)
        db.flush()
        sp_vol = Volume(series_id=sp.id, kind="", subtitle="Vol 1", volume_order=1)
        db.add(sp_vol)
        db.flush()
        for order, (title, pictures) in enumerate(
            (("Spec one", False), ("長" * 200, False), ("Spec image", True)), start=1
        ):
            ch = Document(user_id=user.id, title=title, series_id=sp.id, volume_id=sp_vol.id,
                          series_order=order)
            db.add(ch)
            db.flush()
            write_lines(db, ch.id, [{"line_number": 0, "prefix": "%", "raw_text": "頁です。",
                                     "translated_text": ""}])
            if pictures:
                db.add(DocumentImage(document_id=ch.id, anchor_position=0,
                                     src_path="spec.png", data=PNG_1X1))
                db.flush()
        # tadb.spec: an empty account, so the dry run is not refused for existing documents
        tadb = User(email="tadb@example.com", password_hash=hash_password("tadb-password-123"))
        db.add(tadb)
        db.commit()

    from tests.fixtures.tadb import desktop_db

    generated = root / "web" / "e2e" / ".generated"
    (generated / "ta.db").unlink(missing_ok=True)  # desktop_db appends to an existing file
    desktop_db(generated)  # tadb.spec uploads this


if __name__ == "__main__":
    main()
