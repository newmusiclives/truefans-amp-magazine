"""FastAPI web application for the TrueFans AMP Magazine dashboard."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from weeklyamp.core.config import load_config
from weeklyamp.core.database import init_database, seed_sections
from weeklyamp.research.sources import sync_sources_from_config
from weeklyamp.web.security import (
    AuthMiddleware,
    CSRFMiddleware,
    SecurityHeadersMiddleware,
    login_page,
    login_submit,
    logout,
)

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "templates"
_STATIC_DIR = _TEMPLATES_DIR / "web" / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="TrueFans AMP Magazine", docs_url=None, redoc_url=None)

    # Security middleware (order matters: outermost runs first)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(AuthMiddleware)

    # Auth routes
    app.add_api_route("/login", login_page, methods=["GET"])
    app.add_api_route("/login", login_submit, methods=["POST"])
    app.add_api_route("/logout", logout, methods=["GET"])

    # Custom error pages
    _error_404 = (_TEMPLATES_DIR / "web" / "404.html").read_text()
    _error_500 = (_TEMPLATES_DIR / "web" / "500.html").read_text()

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return HTMLResponse(_error_404, status_code=404)
        if exc.status_code == 500:
            return HTMLResponse(_error_500, status_code=500)
        return HTMLResponse(str(exc.detail), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled server error")
        return HTMLResponse(_error_500, status_code=500)

    # Auto-initialize database on startup
    @app.on_event("startup")
    def startup_init_db():
        try:
            config = load_config()
            db_path = config.db_path
            # Use absolute path on Railway, relative to cwd locally
            if not os.path.isabs(db_path):
                if os.path.exists("/app"):
                    db_path = os.path.join("/app", db_path)
                else:
                    db_path = os.path.abspath(db_path)
            init_database(db_path)
            seed_sections(db_path)
            # Sync any new sources from sources.yaml into DB
            from weeklyamp.db.repository import Repository
            repo = Repository(db_path)
            added = sync_sources_from_config(repo)
            if added:
                logger.info("Synced %d new sources from sources.yaml", added)
            logger.info("Database initialized at %s", db_path)
        except Exception:
            logger.exception("Failed to initialize database")

    # Public landing page
    @app.get("/")
    def landing(request: Request):
        from fastapi.responses import HTMLResponse as HR
        from weeklyamp.web.security import is_authenticated
        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR / "web")), autoescape=True)
        tpl = env.get_template("landing.html")
        authenticated = is_authenticated(request)
        return HR(tpl.render(authenticated=authenticated))

    # Health check
    @app.get("/health")
    def health():
        return {"status": "ok"}

    # Static files
    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Import routes here to avoid circular imports at module level
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

    # Security logs (authenticated, uses Jinja2 template with autoescape)
    from jinja2 import Environment, FileSystemLoader

    _sec_env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR / "web")), autoescape=True
    )

    @app.get("/security/logs")
    def security_logs():
        from weeklyamp.web.deps import get_repo
        repo = get_repo()
        events = repo.get_security_log(limit=50)
        tpl = _sec_env.get_template("security_logs.html")
        return HTMLResponse(tpl.render(events=events))

    return app
