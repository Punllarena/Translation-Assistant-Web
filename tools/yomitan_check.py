"""Local check of real Yomitan dictionaries (never writes to the repo).

    python -m tools.yomitan_check <zip>... [--line TEXT]

Prints read stats and sample glosses per zip. With TA_DATABASE_URL (a scratch database,
migrated), installs every zip and times ``jparser.run`` over 20 runs. Only for local use:
the zips are untrusted data and their text must never be committed.
"""

import argparse
import statistics
import sys
import time

from api.core import yomitan_read

SAMPLE_KEYS = ("食べる", "取る", "気", "猫")
DEFAULT_LINE = (
    "彼女は静かな夜の街を歩きながら、遠い昔に聞いた物語のことをぼんやりと思い出していた。"
    "それでも、あの人の声だけは忘れられなかった。"
)


def _samples(terms: dict, n: int = 15) -> list[str]:
    keys = [k for k in SAMPLE_KEYS if k in terms]
    keys += [k for k in terms if k not in keys][: n - len(keys)]
    return keys[:n]


def _read(path: str):
    start = time.perf_counter()
    try:
        parsed = yomitan_read.read(path)
    except yomitan_read.YomitanError as exc:
        print(f"{path}\n  refused: {exc}")
        return None
    secs = time.perf_counter() - start
    print(f"{path}\n  title={parsed.meta.title!r} entries={parsed.entry_count} "
          f"skipped_rows={parsed.skipped_rows} read={secs:.1f}s")
    for key in _samples(parsed.terms):
        e = parsed.terms[key]
        print(f"  {key}\t{sorted(e.pos)}\t{e.gloss}")
    return parsed


def _time_lookup(parsed_list: list, line: str) -> None:
    from api import yomitan_store
    from api.db import SessionLocal
    from api.mt import jparser

    with SessionLocal() as db:
        for parsed in parsed_list:
            yomitan_store.install(db, parsed)
        db.commit()
    print(f"timing jparser.run on {len(line)} chars")
    jparser.run(line)  # warm caches
    times = []
    for _ in range(20):
        start = time.perf_counter()
        jparser.run(line)
        times.append((time.perf_counter() - start) * 1000)
    print(f"  median={statistics.median(times):.1f} ms max={max(times):.1f} ms")


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("zips", nargs="+")
    ap.add_argument("--line", default=DEFAULT_LINE)
    args = ap.parse_args(argv)
    parsed = [p for p in (_read(z) for z in args.zips) if p is not None]
    import os

    if parsed and os.environ.get("TA_DATABASE_URL"):
        _time_lookup(parsed, args.line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
