"""Download EDICT2 from EDRDG into the data dir (spec §5.2). The URL is fixed and
operator-trusted; redirects are not followed so it can never be steered elsewhere."""

import httpx

from api import dictionary
from api.jobs import JobContext, JobError, handler

EDICT_URL = "https://www.edrdg.org/pub/Nihongo/edict2.gz"
MAX_DOWNLOAD = 32 * 1024 * 1024  # the .gz is ~10 MiB


def http_client() -> httpx.Client:  # the seam tests replace
    return httpx.Client(follow_redirects=False, timeout=60)


@handler("dict_download")
def download_edict(ctx: JobContext) -> dict:
    ctx.progress(0, 2, "Downloading EDICT2 from edrdg.org")
    buf = bytearray()
    try:
        with http_client() as c, c.stream("GET", EDICT_URL) as r:
            if r.status_code != 200:
                raise JobError(f"edrdg.org answered {r.status_code}")
            for chunk in r.iter_bytes():
                buf += chunk
                if len(buf) > MAX_DOWNLOAD:
                    raise JobError(f"the download is larger than {MAX_DOWNLOAD >> 20} MiB")
    except httpx.HTTPError as exc:
        raise JobError(f"could not reach edrdg.org: {exc}") from exc
    ctx.progress(1, 2, "Installing")
    try:
        entries = dictionary.install("edict", dictionary.gunzip_capped(bytes(buf)))
    except ValueError as exc:
        raise JobError(str(exc)) from exc
    return {"entries": entries}
