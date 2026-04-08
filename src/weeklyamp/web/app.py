"""FastAPI web application for the TrueFans SIGNAL dashboard."""

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
from weeklyamp.core.database import init_database, seed_agents, seed_content, seed_editions, seed_guest_contacts, seed_sections
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


def _setup_sentry() -> None:
    """Initialise Sentry SDK if SENTRY_DSN is configured.

    Gracefully no-ops when SENTRY_DSN is not set, so production can
    adopt Sentry later without a code change. PII scrubbing: we keep
    ``send_default_pii=False`` and explicitly strip email addresses
    from event messages via a before_send hook.
    """
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        # sentry-sdk declared in requirements.txt but not installed — log
        # and continue. Don't block app startup on observability tooling.
        logging.getLogger(__name__).warning(
            "SENTRY_DSN set but sentry-sdk not installed — skipping init"
        )
        return

    import re
    _EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

    def _scrub_pii(event, hint):
        # Walk message + exception values and redact any email-shaped strings
        try:
            if event.get("message"):
                event["message"] = _EMAIL_RE.sub("<redacted-email>", event["message"])
            for ex in (event.get("exception") or {}).get("values", []):
                if ex.get("value"):
                    ex["value"] = _EMAIL_RE.sub("<redacted-email>", ex["value"])
        except Exception:
            pass
        return event

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("WEEKLYAMP_ENV", "development"),
        release=os.environ.get("RAILWAY_DEPLOYMENT_ID", "unknown"),
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
        profiles_sample_rate=0.0,
        send_default_pii=False,
        before_send=_scrub_pii,
        integrations=[FastApiIntegration(), StarletteIntegration()],
    )
    logging.getLogger(__name__).info(
        "Sentry initialised (env=%s)",
        os.environ.get("WEEKLYAMP_ENV", "development"),
    )


def _setup_logging():
    """Configure structured logging with JSON-compatible format.

    PII scrubbing: every log record's message is passed through a
    regex that redacts email addresses and long digit sequences
    before the record leaves the process. This is a defense-in-depth
    against accidentally logging subscriber emails or tokens —
    individual log calls still shouldn't include PII on purpose.
    """
    log_format = os.environ.get("LOG_FORMAT", "text")
    level = os.environ.get("LOG_LEVEL", "INFO").upper()

    import re
    _EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    _TOKEN_RE = re.compile(r"\b[a-fA-F0-9]{32,}\b")

    def _scrub(text: str) -> str:
        if not isinstance(text, str):
            return text
        text = _EMAIL_RE.sub("<redacted-email>", text)
        text = _TOKEN_RE.sub("<redacted-token>", text)
        return text

    class PIIScrubFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            # Scrub the formatted message and the raw msg so both text
            # and JSON formatters see the clean version.
            try:
                record.msg = _scrub(record.getMessage())
                record.args = ()  # args already merged into msg above
            except Exception:
                pass
            return True

    if log_format == "json":
        import json
        class JSONFormatter(logging.Formatter):
            def format(self, record):
                payload = {
                    "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "line": record.lineno,
                }
                # Preserve traceback information when present so that
                # `logger.exception()` calls remain diagnosable in
                # production. Without this, every exception logged
                # via .exception() loses its stack and the operator
                # is left guessing — see incident 2026-04-08 where
                # the scheduled_sends root cause was masked for
                # several hours because the formatter dropped exc_info.
                if record.exc_info:
                    payload["exception"] = self.formatException(record.exc_info)
                if record.stack_info:
                    payload["stack"] = self.formatStack(record.stack_info)
                return json.dumps(payload)
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        handler.addFilter(PIIScrubFilter())
        logging.root.handlers = [handler]
        logging.root.setLevel(level)
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        handler.addFilter(PIIScrubFilter())
        logging.root.handlers = [handler]
        logging.root.setLevel(level)


def _is_production() -> bool:
    """Check if running in production mode."""
    return os.environ.get("WEEKLYAMP_ENV", "development").lower() in ("production", "prod")


def create_app() -> FastAPI:
    _setup_logging()
    _setup_sentry()

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
            seed_content(db_path, database_url, backend)
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

        # Start background workers (disabled by default)
        from weeklyamp.workers.scheduler import start_scheduler, stop_scheduler
        _bg_scheduler = start_scheduler()

        yield

        # Shutdown — stop scheduler and close connections cleanly
        stop_scheduler()
        logger.info("Shutting down — closing database connections")

    app = FastAPI(title="TrueFans SIGNAL", docs_url="/docs", redoc_url="/redoc", lifespan=lifespan)

    # Store config on app for access in routes
    app.state.config = config

    # Middleware (order matters: outermost runs first)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=500)

    # White-label domain routing (inactive unless white_label.enabled=true)
    if config.white_label.enabled:
        from weeklyamp.web.middleware.domain_router import DomainRoutingMiddleware
        app.add_middleware(DomainRoutingMiddleware, config=config)

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
        return HR(tpl.render(
            authenticated=authenticated,
            site_domain=site_domain,
        ))

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
        """Readiness check — verifies all dependencies are available.

        This endpoint is designed to be hit every 30-60 seconds by an
        uptime monitor (Better Stack, Railway, etc.). It must return in
        under 500ms and must NOT perform any operation that contacts an
        external service synchronously (no SMTP handshake, no outbound
        HTTP). External-service health is reported by last-known-state
        checks against the database only.
        """
        checks = {}
        overall = True

        # --- Database (read + write) ---
        try:
            from weeklyamp.web.deps import get_repo
            repo = get_repo()
            repo.get_editions()
            checks["db_read"] = "ok"
        except Exception as exc:
            checks["db_read"] = f"error: {exc}"
            overall = False

        # DB backend + schema version — helps diagnose env var confusion
        try:
            from weeklyamp.core.database import _get_backend, get_schema_version
            backend = _get_backend()
            version = get_schema_version()
            checks["db_backend"] = backend
            checks["db_schema_version"] = version if version is not None else "unknown"
        except Exception as exc:
            checks["db_backend"] = f"error: {exc}"
            overall = False

        # --- AI provider (key presence only, no outbound call) ---
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"):
            checks["ai_provider"] = "configured"
        else:
            checks["ai_provider"] = "not configured"

        # --- Email (config only — no SMTP handshake on health check) ---
        if config.email.enabled:
            if config.email.smtp_host:
                checks["email"] = "enabled"
            else:
                checks["email"] = "enabled but smtp_host missing"
                overall = False
        else:
            checks["email"] = "disabled"

        # --- Scheduler / background workers ---
        workers_on = os.environ.get("WEEKLYAMP_WORKERS_ENABLED", "").lower() in (
            "true", "1", "yes",
        )
        checks["workers"] = "enabled" if workers_on else "disabled"

        # --- Last successful send (indirect scheduler/delivery heartbeat) ---
        try:
            from weeklyamp.web.deps import get_repo
            repo = get_repo()
            conn = repo._conn()
            row = conn.execute(
                "SELECT MAX(published_at) AS last_send FROM assembled_issues"
            ).fetchone()
            conn.close()
            last = None
            if row:
                # Row shape differs between sqlite (tuple-like) and pg (dict)
                try:
                    last = row["last_send"]
                except (KeyError, IndexError, TypeError):
                    last = row[0] if row else None
            checks["last_send"] = str(last) if last else "never"
        except Exception as exc:
            checks["last_send"] = f"error: {str(exc)[:80]}"

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
            "Disallow: /ab-tests\n"
            "Disallow: /webhooks\n"
            "Disallow: /backup\n"
            "Disallow: /editor-articles\n"
            "Disallow: /spotify\n"
            "Disallow: /admin/artists\n"
            "Disallow: /sections/analytics\n"
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
            f"{site_domain}/artists",
            f"{site_domain}/trivia/leaderboard",
            f"{site_domain}/advertise",
            f"{site_domain}/resources",
            f"{site_domain}/contests",
            f"{site_domain}/contribute",
            f"{site_domain}/refer/stats",
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
    from weeklyamp.web.routes import editor_articles as editor_articles_routes
    from weeklyamp.web.routes import guests as guests_routes
    from weeklyamp.web.routes import submissions as submissions_routes
    from weeklyamp.web.routes import newsletters as newsletters_routes
    from weeklyamp.web.routes import submit as submit_routes
    from weeklyamp.web.routes import subscribe as subscribe_routes
    # v21+ advanced features (inactive by default)
    from weeklyamp.web.routes import tracking as tracking_routes
    from weeklyamp.web.routes import preferences as preferences_routes
    from weeklyamp.web.routes import ab_tests as ab_tests_routes
    from weeklyamp.web.routes import webhooks as webhooks_routes
    from weeklyamp.web.routes import backup as backup_routes
    # v22+ music-specific features (inactive by default)
    from weeklyamp.web.routes import spotify as spotify_routes
    from weeklyamp.web.routes import artists as artists_routes
    from weeklyamp.web.routes import section_analytics as section_analytics_routes
    from weeklyamp.web.routes import trivia as trivia_routes
    # v23+ growth & monetization features (inactive by default)
    from weeklyamp.web.routes import refer as refer_routes
    from weeklyamp.web.routes import advertise as advertise_routes
    from weeklyamp.web.routes import lead_magnets as lead_magnets_routes
    from weeklyamp.web.routes import contests as contests_routes
    from weeklyamp.web.routes import reader_content as reader_content_routes
    from weeklyamp.web.routes import embed as embed_routes
    from weeklyamp.web.routes import welcome as welcome_routes
    from weeklyamp.web.routes import reengagement as reengagement_routes
    from weeklyamp.web.routes import billing as billing_routes
    from weeklyamp.web.routes import advertiser_portal as advertiser_portal_routes
    from weeklyamp.web.routes import affiliates as affiliates_routes
    from weeklyamp.web.routes import community as community_routes
    from weeklyamp.web.routes import revenue as revenue_routes
    # v28+ markets & artist newsletters
    from weeklyamp.web.routes import markets as markets_routes
    from weeklyamp.web.routes import artist_newsletters as artist_newsletters_routes
    from weeklyamp.web.routes import segments as segments_routes
    from weeklyamp.web.routes import mobile_app as mobile_app_routes
    from weeklyamp.web.routes import mobile_api as mobile_api_routes
    from weeklyamp.web.routes import setup as setup_routes
    from weeklyamp.web.routes import users as users_routes
    from weeklyamp.web.routes import licensing as licensing_routes
    from weeklyamp.web.routes import pricing_calc as pricing_calc_routes
    from weeklyamp.web.routes import marketing as marketing_routes
    from weeklyamp.web.routes import edition_pages as edition_pages_routes
    from weeklyamp.web.routes import notifications as notifications_routes
    from weeklyamp.web.routes import licensee_portal as licensee_portal_routes
    from weeklyamp.web.routes import analytics as analytics_hub_routes
    # v36+ future vision features
    from weeklyamp.web.routes import events as events_routes
    from weeklyamp.web.routes import marketplace as marketplace_routes
    from weeklyamp.web.routes import developer_api as developer_api_routes
    # v38+ Developer API v2
    from weeklyamp.web.routes import api_v2 as api_v2_routes

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
    app.include_router(editor_articles_routes.router, prefix="/editor-articles")
    app.include_router(guests_routes.router, prefix="/guests")
    app.include_router(calendar_routes.router, prefix="/calendar")
    app.include_router(growth_routes.router, prefix="/growth")
    # v21+ advanced feature routes
    app.include_router(tracking_routes.router)
    app.include_router(preferences_routes.router)
    app.include_router(ab_tests_routes.router, prefix="/ab-tests")
    app.include_router(webhooks_routes.router, prefix="/webhooks")
    app.include_router(backup_routes.router, prefix="/backup")
    # v22+ music-specific feature routes
    app.include_router(spotify_routes.router, prefix="/spotify")
    app.include_router(artists_routes.router)
    app.include_router(section_analytics_routes.router, prefix="/sections/analytics")
    app.include_router(trivia_routes.router)
    # v23+ growth & monetization routes
    app.include_router(refer_routes.router)
    app.include_router(advertise_routes.router)
    app.include_router(lead_magnets_routes.router)
    app.include_router(contests_routes.router)
    app.include_router(reader_content_routes.router)
    app.include_router(embed_routes.router)
    app.include_router(welcome_routes.router, prefix="/admin/welcome-sequence")
    app.include_router(reengagement_routes.router, prefix="/admin/reengagement")
    # v26+ paid tiers & billing
    app.include_router(billing_routes.router)
    # v26+ advertiser self-serve portal
    app.include_router(advertiser_portal_routes.router)
    # v26+ community forum
    app.include_router(community_routes.router)
    # v27+ affiliate programs
    app.include_router(affiliates_routes.router, prefix="/affiliates")
    # v28+ revenue dashboard
    app.include_router(revenue_routes.router, prefix="/admin/revenue")
    # v28+ markets & artist newsletters
    app.include_router(markets_routes.router, prefix="/admin/markets")
    app.include_router(artist_newsletters_routes.router)
    # v28+ subscriber segmentation
    app.include_router(segments_routes.router, prefix="/admin/segments")
    # Mobile app waitlist
    app.include_router(mobile_app_routes.router)
    # Mobile JSON API (v1)
    app.include_router(mobile_api_routes.router, prefix="/api/v1")
    # Setup & deliverability guide
    app.include_router(setup_routes.router, prefix="/admin/setup")
    # v29+ admin user management
    app.include_router(users_routes.router, prefix="/admin/users")
    # v30+ city edition licensing
    app.include_router(licensing_routes.router, prefix="/admin/licensing")
    # Revenue calculator
    app.include_router(pricing_calc_routes.router, prefix="/admin/calculator")
    # v32+ marketing & promotion hub
    app.include_router(marketing_routes.router, prefix="/admin/marketing")
    # Edition-specific landing pages
    app.include_router(edition_pages_routes.router)
    # Notification center
    app.include_router(notifications_routes.router, prefix="/notifications")
    # White-label licensee portal
    app.include_router(licensee_portal_routes.router, prefix="/licensee")
    # Analytics hub (NPS, content reports, forecasting, media kit)
    app.include_router(analytics_hub_routes.router, prefix="/admin/analytics")
    # v36+ future vision features
    app.include_router(events_routes.router, prefix="/events")
    app.include_router(marketplace_routes.router, prefix="/marketplace")
    app.include_router(developer_api_routes.router, prefix="/admin/api")
    # v38+ Developer API v2 (public, auth via API key)
    app.include_router(api_v2_routes.router)

    # Convenience redirects for common short URLs
    from fastapi.responses import RedirectResponse as _Redir

    @app.get("/revenue")
    @app.get("/revenue/")
    async def _revenue_redirect():
        return _Redir("/admin/revenue/", status_code=302)

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
