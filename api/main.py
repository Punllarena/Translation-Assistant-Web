import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from api import jobs, tadb_uploads, yomitan_job
from api.backup import restore, state, uploads
from api.config import get_settings
from api.ollama import runner, schedule, store  # noqa: F401  store registers ollama_cleanup
from api.routers import (
    admin,
    auth,
    backup,
    covers,
    credentials,
    dictionary,
    documents,
    epub,
    exports,
    gallery,
    glossary,
    images,
    invites,
    lines,
    memory,
    mt,
    ollama_editor,
    readings,
    scrape,
    series,
    settings,
    setup,
    spell,
    stats,
    tadb,
    transfer,
    volumes,
    words,
    wp,
)
from api.routers import (
    jobs as jobs_routes,
)
from api.routers import ollama as ollama_routes
from api.routing import CommitOnResponseRoute

# The only routes answered while a restore runs (they have to be: the SPA polls the first).
MAINTENANCE_ALLOWED = frozenset({"/restore/status", "/healthz"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A restore interrupted after its commit left dict.ready/: complete that swap now.
    await run_in_threadpool(restore.recover_dictionaries)
    if not get_settings().run_jobs_worker:
        yield
        await ollama_editor.stop()
        return
    await run_in_threadpool(jobs.fail_interrupted)
    await run_in_threadpool(tadb_uploads.sweep)
    await run_in_threadpool(uploads.sweep)
    await run_in_threadpool(yomitan_job.sweep)
    jobs.stopping.clear()
    stop = asyncio.Event()
    task = asyncio.create_task(jobs.worker(stop))
    ollama_task = asyncio.create_task(runner.runner(stop))
    tick_task = asyncio.create_task(schedule.ticker(stop))
    yield
    jobs.stopping.set()  # a running job stops at its next progress point
    stop.set()
    await task
    await ollama_task
    await tick_task
    await ollama_editor.stop()  # by-hand chunks in flight


def create_app() -> FastAPI:
    get_settings()  # fail fast: refuses to start without TA_SECRET_KEY
    app = FastAPI(title="ta-web", version="0.1.0", lifespan=lifespan)
    app.router.route_class = CommitOnResponseRoute  # for routes declared on the app itself

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.middleware("http")
    async def maintenance(request: Request, call_next):
        if state.active() and request.url.path not in MAINTENANCE_ALLOWED:
            return JSONResponse({"detail": state.IN_PROGRESS}, status_code=503)
        return await call_next(request)

    app.include_router(auth.router)
    app.include_router(setup.router)
    app.include_router(admin.router)
    app.include_router(backup.router)
    app.include_router(dictionary.router)
    app.include_router(invites.router)
    app.include_router(glossary.router)
    app.include_router(series.router)
    app.include_router(scrape.router)  # literal paths under /documents/{id}
    app.include_router(tadb.router)
    app.include_router(transfer.router)  # before documents: literal POST path
    app.include_router(exports.router)  # before documents: literal POST path
    app.include_router(documents.router)
    app.include_router(volumes.router)
    app.include_router(covers.router)
    app.include_router(lines.router)
    app.include_router(memory.router)
    app.include_router(readings.router)
    app.include_router(spell.router)
    app.include_router(words.router)
    app.include_router(images.router)
    app.include_router(gallery.router)
    app.include_router(settings.router)
    app.include_router(credentials.router)
    app.include_router(mt.router)
    app.include_router(jobs_routes.router)
    app.include_router(ollama_routes.router)
    app.include_router(ollama_editor.router)
    app.include_router(epub.router)
    app.include_router(wp.router)
    app.include_router(stats.router)

    return app


app = create_app()
