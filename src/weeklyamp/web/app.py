"""FastAPI web application for the TrueFans AMP Magazine dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from weeklyamp.core.config import load_config
from weeklyamp.core.database import init_db
from weeklyamp.web.routes import (
    dashboard,
    drafts,
    publish,
    research,
    review,
    schedule,
    sections,
    sponsor_blocks,
    sponsors,
    subscribers,
)
from weeklyamp.web.routes import agents as agents_routes
from weeklyamp.web.routes import calendar as calendar_routes
from weeklyamp.web.routes import growth as growth_routes
from weeklyamp.web.routes import guests as guests_routes
from weeklyamp.web.routes import submissions as submissions_routes
from weeklyamp.web.routes import submit as submit_routes

_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "templates"
_STATIC_DIR = _TEMPLATES_DIR / "web" / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="TrueFans AMP Magazine", docs_url=None, redoc_url=None)

    # Auto-initialize database on startup
    @app.on_event("startup")
    def startup_init_db():
        config = load_config()
        init_db(config.db_path)

    # Static files
    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Routes
    app.include_router(dashboard.router)
    app.include_router(research.router, prefix="/research")
    app.include_router(drafts.router, prefix="/drafts")
    app.include_router(review.router, prefix="/review")
    app.include_router(publish.router, prefix="/publish")
    app.include_router(subscribers.router, prefix="/subscribers")
    app.include_router(sections.router, prefix="/sections")
    app.include_router(schedule.router, prefix="/schedule")
    app.include_router(sponsor_blocks.router, prefix="/sponsor-blocks")
    app.include_router(sponsors.router, prefix="/sponsors")
    app.include_router(agents_routes.router, prefix="/agents")
    app.include_router(submissions_routes.router, prefix="/submissions")
    app.include_router(submit_routes.router)
    app.include_router(guests_routes.router, prefix="/guests")
    app.include_router(calendar_routes.router, prefix="/calendar")
    app.include_router(growth_routes.router, prefix="/growth")

    return app
