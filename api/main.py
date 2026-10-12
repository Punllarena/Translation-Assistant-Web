import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from api import jobs
from api.config import get_settings
from api.routers import (
    auth,
    credentials,
    documents,
    glossary,
    images,
    invites,
    lines,
    memory,
    mt,
    profiles,
    scrape,
    series,
    settings,
    spell,
    transfer,
    volumes,
)
from api.routers import (
    jobs as jobs_routes,
)
from api.routing import CommitOnResponseRoute


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not get_settings().run_jobs_worker:
        yield
        return
    await run_in_threadpool(jobs.fail_interrupted)
    jobs.stopping.clear()
    stop = asyncio.Event()
    task = asyncio.create_task(jobs.worker(stop))
    yield
    jobs.stopping.set()  # a running job stops at its next progress point
    stop.set()
    await task


def create_app() -> FastAPI:
    get_settings()  # fail fast: refuses to start without TA_SECRET_KEY
    app = FastAPI(title="ta-web", version="0.1.0", lifespan=lifespan)
    app.router.route_class = CommitOnResponseRoute  # for routes declared on the app itself

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(invites.router)
    app.include_router(profiles.router)
    app.include_router(glossary.router)
    app.include_router(series.router)
    app.include_router(scrape.router)  # literal paths under /documents/{id}
    app.include_router(transfer.router)  # before documents: literal POST path
    app.include_router(documents.router)
    app.include_router(volumes.router)
    app.include_router(lines.router)
    app.include_router(memory.router)
    app.include_router(spell.router)
    app.include_router(images.router)
    app.include_router(settings.router)
    app.include_router(credentials.router)
    app.include_router(mt.router)
    app.include_router(jobs_routes.router)

    return app


app = create_app()
