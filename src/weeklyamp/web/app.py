"""FastAPI web application for the TrueFans NEWSLETTERS dashboard."""

from __future__ import annotations

import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi import Response as FastAPIResponse
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from weeklyamp.core.config import load_config
from weeklyamp.core.database import init_database, seed_agents, seed_editions, seed_guest_contacts, seed_sections
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


def _setup_logging():
    """Configure structured logging with JSON-compatible format."""
    log_format = os.environ.get("LOG_FORMAT", "text")
    level = os.environ.get("LOG_LEVEL", "INFO").upper()

    if log_format == "json":
        import json
        class JSONFormatter(logging.Formatter):
            def format(self, record):
                return json.dumps({
                    "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "line": record.lineno,
                })
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logging.root.handlers = [handler]
        logging.root.setLevel(level)
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def _is_production() -> bool:
    """Check if running in production mode."""
    return os.environ.get("WEEKLYAMP_ENV", "development").lower() in ("production", "prod")


def create_app() -> FastAPI:
    _setup_logging()

    config = load_config()

    # Production safety checks — fail fast if critical config is missing
    if _is_production():
        missing = []
        if not os.environ.get("WEEKLYAMP_SECRET_KEY"):
            missing.append("WEEKLYAMP_SECRET_KEY")
        if not os.environ.get("WEEKLYAMP_ADMIN_HASH") and not os.environ.get("WEEKLYAMP_ADMIN_PASSWORD"):
            missing.append("WEEKLYAMP_ADMIN_HASH or WEEKLYAMP_ADMIN_PASSWORD")
        if missing:
            logger.critical("Production mode: missing required config: %s", ", ".join(missing))
            sys.exit(1)
    else:
        if not os.environ.get("WEEKLYAMP_SECRET_KEY"):
            logger.warning("WEEKLYAMP_SECRET_KEY not set — sessions won't survive restarts")
        if not os.environ.get("WEEKLYAMP_ADMIN_HASH") and not os.environ.get("WEEKLYAMP_ADMIN_PASSWORD"):
            logger.warning("No admin password configured — auth is disabled")

    if config.email.enabled and not config.email.smtp_host:
        logger.warning("Email enabled but SMTP_HOST not configured — sending will fail")

    site_domain = config.site_domain.rstrip("/")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        try:
            db_path = config.db_path
            backend = config.db_backend
            database_url = config.database_url
            # Use absolute path on Railway, relative to cwd locally (sqlite only)
            if backend == "sqlite" and not os.path.isabs(db_path):
                if os.path.exists("/app"):
                    db_path = os.path.join("/app", db_path)
                else:
                    db_path = os.path.abspath(db_path)
            init_database(db_path, database_url, backend)
            seed_sections(db_path, database_url, backend)
            seed_editions(db_path, database_url, backend)
            seed_guest_contacts(db_path, database_url, backend)
            seed_agents(db_path, database_url, backend)
            # Sync any new sources from sources.yaml into DB
            from weeklyamp.db.repository import Repository
            repo = Repository(db_path, database_url, backend)
            added = sync_sources_from_config(repo)
            if added:
                logger.info("Synced %d new sources from sources.yaml", added)
            logger.info("Database initialized at %s (backend=%s)", db_path, backend)
        except Exception:
            logger.exception("Failed to initialize database")
            if _is_production():
                sys.exit(1)

        yield

        # Shutdown — close connections cleanly
        logger.info("Shutting down — closing database connections")

    app = FastAPI(title="TrueFans NEWSLETTERS", docs_url=None, redoc_url=None, lifespan=lifespan)

    # Store config on app for access in routes
    app.state.config = config

    # Middleware (order matters: outermost runs first)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=500)

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
        logger.exception("Unhandled server error: %s %s", request.method, request.url.path)
        return HTMLResponse(_error_500, status_code=500)

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

    # Health checks
    @app.get("/health")
    def health():
        try:
            from weeklyamp.web.deps import get_repo
            repo = get_repo()
            repo.get_editions()
            return {"status": "ok", "db": "connected"}
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"status": "error", "detail": str(exc)},
            )

    @app.get("/health/ready")
    def readiness():
        """Readiness check — verifies all dependencies are available."""
        checks = {}
        overall = True

        # Database
        try:
            from weeklyamp.web.deps import get_repo
            repo = get_repo()
            repo.get_editions()
            checks["db"] = "ok"
        except Exception as exc:
            checks["db"] = f"error: {exc}"
            overall = False

        # AI provider (check key is set, don't make a call)
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"):
            checks["ai_provider"] = "configured"
        else:
            checks["ai_provider"] = "not configured"

        # Email
        if config.email.enabled:
            if config.email.smtp_host:
                checks["email"] = "configured"
            else:
                checks["email"] = "enabled but smtp_host missing"
                overall = False
        else:
            checks["email"] = "disabled"

        status_code = 200 if overall else 503
        return JSONResponse(
            status_code=status_code,
            content={"status": "ok" if overall else "degraded", "checks": checks},
        )

    @app.get("/health/live")
    def liveness():
        """Liveness check — confirms the process is alive."""
        return {"status": "ok"}

    # SEO: robots.txt
    @app.get("/robots.txt")
    def robots_txt():
        body = (
            "User-agent: *\n"
            "Allow: /\n"
            "Disallow: /dashboard\n"
            "Disallow: /research\n"
            "Disallow: /drafts\n"
            "Disallow: /review\n"
            "Disallow: /publish\n"
            "Disallow: /subscribers\n"
            "Disallow: /sections\n"
            "Disallow: /schedule\n"
            "Disallow: /sponsor-blocks\n"
            "Disallow: /sponsors\n"
            "Disallow: /agents\n"
            "Disallow: /submissions\n"
            "Disallow: /guests\n"
            "Disallow: /calendar\n"
            "Disallow: /growth\n"
            "Disallow: /security\n"
            "Disallow: /login\n"
            "Disallow: /logout\n"
            "\n"
            f"Sitemap: {site_domain}/sitemap.xml\n"
        )
        return PlainTextResponse(body)

    # SEO: sitemap.xml
    @app.get("/sitemap.xml")
    def sitemap_xml():
        urls = [
            f"{site_domain}/",
            f"{site_domain}/newsletters",
            f"{site_domain}/subscribe",
            f"{site_domain}/submit",
        ]
        xml_urls = "\n".join(
            f"  <url><loc>{u}</loc></url>" for u in urls
        )
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{xml_urls}\n"
            "</urlset>\n"
        )
        return FastAPIResponse(content=xml, media_type="application/xml")

    # SEO: favicon redirect
    @app.get("/favicon.ico")
    def favicon_ico():
        return RedirectResponse(url="/static/favicon.svg", status_code=301)

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
    from weeklyamp.web.routes import newsletters as newsletters_routes
    from weeklyamp.web.routes import submit as submit_routes
    from weeklyamp.web.routes import subscribe as subscribe_routes

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
    app.include_router(subscribe_routes.router)
    app.include_router(newsletters_routes.router)
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
        events = repo.get_security_log(limit=config.pagination_default)
        tpl = _sec_env.get_template("security_logs.html")
        return HTMLResponse(tpl.render(events=events))

    return app
