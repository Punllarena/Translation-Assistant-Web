from fastapi import FastAPI

from api.config import get_settings
from api.routers import auth, credentials, invites, profiles, settings
from api.routing import CommitOnResponseRoute


def create_app() -> FastAPI:
    get_settings()  # fail fast: refuses to start without TA_SECRET_KEY
    app = FastAPI(title="ta-web", version="0.1.0")
    app.router.route_class = CommitOnResponseRoute  # for routes declared on the app itself

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(invites.router)
    app.include_router(profiles.router)
    app.include_router(settings.router)
    app.include_router(credentials.router)

    return app


app = create_app()
