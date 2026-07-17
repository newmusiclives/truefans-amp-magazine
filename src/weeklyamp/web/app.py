"""FastAPI web application for the TrueFans DISPATCH dashboard."""

from __future__ import annotations

import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi import Response as FastAPIResponse
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from weeklyamp.core.config import load_config
from weeklyamp.core.database import init_database, seed_agents, seed_content, seed_editions, seed_guest_contacts, seed_sections
from weeklyamp.research.sources import sync_sources_from_config
from weeklyamp.web.security import (
    AdminIPAllowlistMiddleware,
    AuthMiddleware,
    BodySizeLimitMiddleware,
    ComingSoonMiddleware,
    CSRFMiddleware,
    SecurityHeadersMiddleware,
    login_2fa_page,
    login_2fa_submit,
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

    PII scrubbing: every log record's message is passed through
    :class:`weeklyamp.core.logging_filters.PIIRedactionFilter`, which
    redacts email addresses, phone numbers, bearer tokens, and
    ``tfs_*`` API keys before the record leaves the process. This is a
    defense-in-depth against accidentally logging subscriber emails or
    tokens — individual log calls still shouldn't include PII on purpose.
    """
    log_format = os.environ.get("LOG_FORMAT", "text")
    level = os.environ.get("LOG_LEVEL", "INFO").upper()

    from weeklyamp.core.logging_filters import PIIRedactionFilter
    PIIScrubFilter = PIIRedactionFilter  # keep local name for the block below

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


def _preflight_db_admin_hash_present(config) -> bool:
    """Return True if admin_settings.admin_password_hash exists in the DB.

    Runs during startup preflight, so the DB may or may not be
    reachable depending on what's already initialized. We treat any
    failure as "not present" — callers still have the env-var path to
    fall back on, and if both are absent we'll fail loudly anyway.

    Important: this runs BEFORE the lifespan startup that calls
    init_database, so the table may not exist yet on a truly fresh
    deploy. That's fine — a fresh deploy legitimately has no DB
    override and the env var path is required, which is the desired
    behavior.
    """
    try:
        from weeklyamp.db.repository import Repository
        db_path = config.db_path
        backend = config.db_backend
        if backend == "sqlite" and not os.path.isabs(db_path):
            if os.path.exists("/app"):
                db_path = os.path.join("/app", db_path)
            else:
                db_path = os.path.abspath(db_path)
        repo = Repository(db_path, config.database_url, backend)
        return bool(repo.get_admin_setting("admin_password_hash"))
    except Exception:
        logger.debug("preflight DB admin-hash check failed", exc_info=True)
        return False


def create_app() -> FastAPI:
    _setup_logging()
    _setup_sentry()

    config = load_config()

    # Production safety checks — fail fast if critical config is missing
    if _is_production():
        missing = []
        if not os.environ.get("WEEKLYAMP_SECRET_KEY"):
            missing.append("WEEKLYAMP_SECRET_KEY")
        # Admin credentials satisfied by ANY of: env hash, env password,
        # or admin_settings.admin_password_hash in the DB. The DB branch
        # is how the in-app change-password UI rotates credentials
        # without redeploying env vars (this is also what bit us on
        # 2026-04-17 when env vars were removed mid-session and the
        # DB check wasn't part of preflight).
        has_env_admin = bool(
            os.environ.get("WEEKLYAMP_ADMIN_HASH") or os.environ.get("WEEKLYAMP_ADMIN_PASSWORD")
        )
        has_db_admin = _preflight_db_admin_hash_present(config)
        if not has_env_admin and not has_db_admin:
            missing.append("admin credentials (env WEEKLYAMP_ADMIN_HASH/ADMIN_PASSWORD or admin_settings row)")
        if missing:
            logger.critical("Production mode: missing required config: %s", ", ".join(missing))
            sys.exit(1)
    else:
        if not os.environ.get("WEEKLYAMP_SECRET_KEY"):
            logger.warning("WEEKLYAMP_SECRET_KEY not set — sessions won't survive restarts")
        if (
            not os.environ.get("WEEKLYAMP_ADMIN_HASH")
            and not os.environ.get("WEEKLYAMP_ADMIN_PASSWORD")
            and not _preflight_db_admin_hash_present(config)
        ):
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
            # Feature flags: register config defaults + seed any missing
            # DB rows so /admin/feature-flags has a complete list to toggle.
            from weeklyamp.core import feature_flags as ff
            ff.set_config_defaults(config.features)
            ff.seed_from_config(repo, config.features)
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

    app = FastAPI(title="TrueFans DISPATCH", docs_url="/docs", redoc_url="/redoc", lifespan=lifespan)

    # Store config on app for access in routes
    app.state.config = config

    # Middleware (order matters: outermost runs first)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(AuthMiddleware)
    # Admin IP allowlist runs BEFORE auth so blocked IPs never trigger
    # login attempts (keeping the attacker surface small).
    app.add_middleware(
        AdminIPAllowlistMiddleware,
        allowlist=os.environ.get("WEEKLYAMP_ADMIN_IP_ALLOWLIST", ""),
    )
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=config.max_request_body,
        # Webhooks occasionally carry larger payloads from external systems;
        # size enforcement there happens inside the webhook handler which
        # validates the HMAC before reading the full body.
        exempt_paths=("/webhooks/inbound",),
    )
    app.add_middleware(GZipMiddleware, minimum_size=500)

    # Pre-launch "coming soon" gate. Registered LAST so it sits OUTERMOST and
    # short-circuits before any other handling when closed. Off unless
    # WEEKLYAMP_COMING_SOON is truthy; admins with a session and an optional
    # ?preview=<WEEKLYAMP_COMING_SOON_TOKEN> link bypass it. See
    # ComingSoonMiddleware for the full allow-list.
    app.add_middleware(
        ComingSoonMiddleware,
        enabled=os.environ.get("WEEKLYAMP_COMING_SOON", "").lower() in ("true", "1", "yes"),
        token=os.environ.get("WEEKLYAMP_COMING_SOON_TOKEN", "").strip(),
    )

    # CORS — lock cross-origin requests to an explicit allowlist.
    # Default: no origins allowed (same-origin only, no CORS headers).
    # Configure via WEEKLYAMP_CORS_ORIGINS as a comma-separated list of
    # full origin URLs (e.g. "https://web-production-2684b.up.railway.app").
    # Use "*" only for local dev — it's incompatible with
    # allow_credentials=True so session cookies won't work cross-origin anyway.
    cors_env = os.environ.get("WEEKLYAMP_CORS_ORIGINS", "").strip()
    if cors_env:
        from fastapi.middleware.cors import CORSMiddleware
        origins = [o.strip() for o in cors_env.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials="*" not in origins,
            allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "HX-Request", "HX-Target"],
        )

    # White-label domain routing (inactive unless white_label.enabled=true)
    if config.white_label.enabled:
        from weeklyamp.web.middleware.domain_router import DomainRoutingMiddleware
        app.add_middleware(DomainRoutingMiddleware, config=config)

    # Auth routes
    app.add_api_route("/login", login_page, methods=["GET"])
    app.add_api_route("/login", login_submit, methods=["POST"])
    app.add_api_route("/login/2fa", login_2fa_page, methods=["GET"])
    app.add_api_route("/login/2fa", login_2fa_submit, methods=["POST"])
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

    # Public sample-issue pages — link from the "3 Editions, One Mission"
    # cards on the landing page. Serves the pre-rendered demo files from
    # the repo root. Whitelist of slugs to prevent path traversal; any
    # other slug 404s.
    _SAMPLE_FILES = {
        "fan": ("demo_fan_monday.html", "Fan Edition", "Music for fans"),
        "artist": ("demo_artist_monday.html", "Artist Edition", "Working musicians"),
        "industry": ("demo_industry_monday.html", "Industry Edition", "Music business"),
        "tucson": ("demo_tucson_artist.html", "Tucson Artist Edition", "Local edition — Tucson, AZ"),
        "corrales": ("demo_corrales_artist.html", "Corrales Artist Edition", "Local edition — Corrales, NM"),
        "sugar-lime-blue": ("demo_sugar_lime_blue.html", "Sugar Lime Blue Edition", "Artist-specific edition"),
    }

    @app.get("/sample/{edition}")
    def sample_issue(edition: str):
        entry = _SAMPLE_FILES.get(edition.lower())
        if not entry:
            return HTMLResponse(_error_404, status_code=404)
        fname = entry[0]
        sample_path = _TEMPLATES_DIR.parent / fname
        if not sample_path.exists():
            return HTMLResponse(_error_404, status_code=404)
        return HTMLResponse(sample_path.read_text())

    @app.get("/samples", response_class=HTMLResponse)
    def samples_index():
        """Index page listing all sample editions — share this URL."""
        cards = []
        for slug, (fname, title, blurb) in _SAMPLE_FILES.items():
            if not (_TEMPLATES_DIR.parent / fname).exists():
                continue
            cards.append(
                f'<a href="/sample/{slug}" style="display:block;padding:20px;border:1px solid #e5e7eb;'
                f'border-radius:8px;text-decoration:none;color:#1a1a1a;background:#fff;'
                f'transition:border-color 0.15s;" '
                f"onmouseover=\"this.style.borderColor='#b09a3a'\" "
                f"onmouseout=\"this.style.borderColor='#e5e7eb'\">"
                f'<div style="font-size:18px;font-weight:700;margin-bottom:6px;">{title}</div>'
                f'<div style="font-size:14px;color:#6b7280;">{blurb}</div>'
                f'</a>'
            )
        body = (
            '<!DOCTYPE html><html lang="en"><head>'
            '<meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
            '<title>TrueFans DISPATCH &mdash; Sample Editions</title></head>'
            '<body style="font-family:Georgia,serif;background:#f9f9f9;margin:0;padding:40px 20px;">'
            '<div style="max-width:640px;margin:0 auto;">'
            '<h1 style="font-size:28px;margin:0 0 8px;color:#1a1a1a;">TrueFans DISPATCH &mdash; Sample Editions</h1>'
            '<p style="color:#6b7280;font-size:15px;margin:0 0 28px;">'
            'Six sample issues. Three top-line editions plus two local editions and one artist-specific edition. '
            'Every fact is sourced &mdash; click through to read.</p>'
            f'<div style="display:flex;flex-direction:column;gap:12px;">{"".join(cards)}</div>'
            '<p style="color:#9ca3af;font-size:12px;margin:32px 0 0;text-align:center;">'
            '&copy; 2026 TrueFans DISPATCH</p>'
            '</div></body></html>'
        )
        return HTMLResponse(body)

    # Pre-launch waitlist capture — posted from the "coming soon" holding
    # page. Reachable while the gate is closed via the ComingSoonMiddleware
    # allow-list and the "/coming-soon" public prefix. Re-renders the same
    # holding page with a success/error banner (works without JavaScript).
    @app.post("/coming-soon/notify", response_class=HTMLResponse)
    async def coming_soon_notify(request: Request):
        from weeklyamp.web.security import render_coming_soon_page
        from weeklyamp.web.routes.subscribe import (
            _EMAIL_RE, _get_client_ip, _is_subscribe_rate_limited, _record_subscribe,
        )
        form = await request.form()
        email = (form.get("email", "") or "").strip()[:254]
        ip = _get_client_ip(request)

        if _is_subscribe_rate_limited(ip):
            return HTMLResponse(
                render_coming_soon_page(
                    error="Too many requests — please try again in a few minutes.", email=email),
                status_code=429,
            )
        if not email or not _EMAIL_RE.match(email):
            return HTMLResponse(
                render_coming_soon_page(error="Please enter a valid email address.", email=email),
            )
        try:
            from weeklyamp.web.deps import get_repo
            repo = get_repo()
            referrer = (request.query_params.get("ref", "") or request.headers.get("referer", ""))[:500]
            repo.add_to_launch_waitlist(email=email, source="coming-soon", referrer=referrer)
            _record_subscribe(ip)
        except Exception:
            logger.exception("Launch waitlist capture failed")
            return HTMLResponse(
                render_coming_soon_page(
                    error="Something went wrong — please try again later.", email=email),
            )
        # Idempotent: a repeat email also lands here, which is the right UX.
        return HTMLResponse(
            render_coming_soon_page(
                message="You're on the list — we'll email you the moment we launch. Thank you!"),
        )

    # Admin viewer for the pre-launch waitlist. Protected by AuthMiddleware
    # (non-public path → anonymous is redirected to /login). ?export=csv
    # downloads the full list.
    @app.get("/admin/waitlist", response_class=HTMLResponse)
    def admin_waitlist(request: Request):
        from weeklyamp.web.deps import get_repo
        repo = get_repo()
        if request.query_params.get("export") == "csv":
            import csv
            import io
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["email", "source", "referrer", "created_at"])
            for e in repo.get_launch_waitlist(limit=100000):
                writer.writerow([
                    e.get("email", ""), e.get("source", ""),
                    e.get("referrer", ""), e.get("created_at", ""),
                ])
            return PlainTextResponse(
                buf.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=launch_waitlist.csv"},
            )

        import html as _html
        entries = repo.get_launch_waitlist(limit=2000)
        count = repo.get_launch_waitlist_count()
        rows = "".join(
            f'<tr><td>{_html.escape(str(e.get("email","")))}</td>'
            f'<td>{_html.escape(str(e.get("source","")))}</td>'
            f'<td>{_html.escape(str(e.get("created_at","")))}</td></tr>'
            for e in entries
        ) or '<tr><td colspan="3" style="color:#9ca3af;">No signups yet.</td></tr>'
        body = (
            '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
            '<title>Launch Waitlist</title>'
            '<style>body{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
            'background:#f9f9f9;margin:0;padding:40px 20px;color:#1a1a1a}'
            '.wrap{max-width:760px;margin:0 auto}h1{font-size:24px;margin:0 0 4px}'
            '.sub{color:#6b7280;font-size:14px;margin:0 0 20px}'
            'a.btn{display:inline-block;background:#b09a3a;color:#fff;text-decoration:none;'
            'padding:8px 14px;border-radius:6px;font-size:14px;font-weight:600;margin-bottom:18px}'
            'table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e7eb;'
            'border-radius:8px;overflow:hidden}th,td{text-align:left;padding:10px 14px;'
            'border-bottom:1px solid #f0f0f0;font-size:14px}th{background:#fafafa;color:#374151}'
            '</style></head><body><div class="wrap">'
            '<h1>Launch Waitlist</h1>'
            f'<p class="sub">{count} email{"" if count == 1 else "s"} captured from the coming-soon page.</p>'
            '<a class="btn" href="/admin/waitlist?export=csv">Download CSV</a>'
            '<table><thead><tr><th>Email</th><th>Source</th><th>Signed up</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
            '</div></body></html>'
        )
        return HTMLResponse(body)

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
            "Disallow: /admin/resend\n"
            "Disallow: /admin/editions\n"
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
        # Include published living editions in sitemap
        try:
            from weeklyamp.web.deps import get_repo as _sitemap_repo
            _repo = _sitemap_repo()
            for ed in _repo.get_published_editions():
                urls.append(f"{site_domain}/edition/{ed['id']}")
        except Exception:
            pass
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
    from weeklyamp.web.routes import promo_admin as promo_admin_routes
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
    from weeklyamp.web.routes import live_editions as live_editions_routes
    from weeklyamp.web.routes import notifications as notifications_routes
    from weeklyamp.web.routes import licensee_portal as licensee_portal_routes
    from weeklyamp.web.routes import admin_2fa as admin_2fa_routes
    from weeklyamp.web.routes import admin_account as admin_account_routes
    from weeklyamp.web.routes import admin_cost_dashboard as admin_cost_dashboard_routes
    from weeklyamp.web.routes import admin_feature_flags as admin_feature_flags_routes
    from weeklyamp.web.routes import admin_password_reset as admin_password_reset_routes
    from weeklyamp.web.routes import analytics as analytics_hub_routes
    from weeklyamp.web.routes import send_time as send_time_routes
    # v36+ future vision features
    from weeklyamp.web.routes import events as events_routes
    from weeklyamp.web.routes import marketplace as marketplace_routes
    from weeklyamp.web.routes import developer_api as developer_api_routes
    # v38+ Developer API v2
    from weeklyamp.web.routes import api_v2 as api_v2_routes
    # v51+ Resend to non-openers
    from weeklyamp.web.routes import resend as resend_routes

    # Feature-flag-gated routers. Each gated router 404s when its flag
    # is off; flip at /admin/feature-flags to turn on.
    from weeklyamp.core.feature_flags import FeatureFlag, require_feature

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
    app.include_router(
        calendar_routes.router, prefix="/calendar",
        dependencies=[Depends(require_feature(FeatureFlag.CALENDAR_REBOOK))],
    )
    app.include_router(growth_routes.router, prefix="/growth")
    # v21+ advanced feature routes
    app.include_router(tracking_routes.router)
    app.include_router(preferences_routes.router)
    app.include_router(
        ab_tests_routes.router, prefix="/ab-tests",
        dependencies=[Depends(require_feature(FeatureFlag.AB_TESTING))],
    )
    app.include_router(
        webhooks_routes.router, prefix="/webhooks",
        dependencies=[Depends(require_feature(FeatureFlag.WEBHOOKS_INBOUND))],
    )
    app.include_router(backup_routes.router, prefix="/backup")
    # v22+ music-specific feature routes
    app.include_router(
        spotify_routes.router, prefix="/spotify",
        dependencies=[Depends(require_feature(FeatureFlag.SPOTIFY))],
    )
    app.include_router(artists_routes.router)
    app.include_router(
        section_analytics_routes.router, prefix="/sections/analytics",
        dependencies=[Depends(require_feature(FeatureFlag.SECTION_HEATMAP))],
    )
    app.include_router(
        trivia_routes.router,
        dependencies=[Depends(require_feature(FeatureFlag.TRIVIA))],
    )
    # v23+ growth & monetization routes
    app.include_router(
        refer_routes.router,
        dependencies=[Depends(require_feature(FeatureFlag.REFERRALS))],
    )
    app.include_router(
        advertise_routes.router,
        dependencies=[Depends(require_feature(FeatureFlag.ADVERTISERS))],
    )
    app.include_router(lead_magnets_routes.router)
    app.include_router(
        contests_routes.router,
        dependencies=[Depends(require_feature(FeatureFlag.CONTESTS))],
    )
    app.include_router(
        reader_content_routes.router,
        dependencies=[Depends(require_feature(FeatureFlag.USER_SUBMISSIONS))],
    )
    app.include_router(embed_routes.router)
    app.include_router(
        welcome_routes.router, prefix="/admin/welcome-sequence",
        dependencies=[Depends(require_feature(FeatureFlag.WELCOME_SEQUENCE))],
    )
    app.include_router(
        reengagement_routes.router, prefix="/admin/reengagement",
        dependencies=[Depends(require_feature(FeatureFlag.REENGAGEMENT))],
    )
    # v26+ paid tiers & billing
    app.include_router(
        billing_routes.router,
        dependencies=[Depends(require_feature(FeatureFlag.PAID_TIERS))],
    )
    # v26+ advertiser self-serve portal
    app.include_router(
        advertiser_portal_routes.router,
        dependencies=[Depends(require_feature(FeatureFlag.ADVERTISERS))],
    )
    # v26+ community forum
    app.include_router(
        community_routes.router,
        dependencies=[Depends(require_feature(FeatureFlag.COMMUNITY))],
    )
    # v27+ affiliate programs
    app.include_router(
        affiliates_routes.router, prefix="/affiliates",
        dependencies=[Depends(require_feature(FeatureFlag.REFERRALS))],
    )
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
    app.include_router(
        licensing_routes.router, prefix="/admin/licensing",
        dependencies=[Depends(require_feature(FeatureFlag.FRANCHISE))],
    )
    # Revenue calculator
    app.include_router(pricing_calc_routes.router, prefix="/admin/calculator")
    # v32+ marketing & promotion hub
    app.include_router(marketing_routes.router, prefix="/admin/marketing")
    # Edition-specific landing pages
    app.include_router(edition_pages_routes.router)
    # Living Editions — web-hosted versions of published issues
    app.include_router(live_editions_routes.router)
    # Notification center
    app.include_router(notifications_routes.router, prefix="/notifications")
    # White-label licensee portal
    app.include_router(
        licensee_portal_routes.router, prefix="/licensee",
        dependencies=[Depends(require_feature(FeatureFlag.WHITE_LABEL))],
    )
    # Admin self-service: change password + feature flags + 2FA + reset + cost
    app.include_router(promo_admin_routes.router, prefix="/admin/promo")
    app.include_router(admin_account_routes.router, prefix="/admin")
    app.include_router(admin_feature_flags_routes.router, prefix="/admin")
    app.include_router(admin_2fa_routes.router, prefix="/admin")
    app.include_router(admin_cost_dashboard_routes.router, prefix="/admin")
    # Password reset lives under /login/* so it's reachable unauthenticated.
    # Public paths are matched by prefix — /login is already in
    # _PUBLIC_PREFIXES so /login/forgot and /login/reset inherit.
    app.include_router(admin_password_reset_routes.router, prefix="/login")
    # Analytics hub (NPS, content reports, forecasting, media kit)
    app.include_router(analytics_hub_routes.router, prefix="/admin/analytics")
    # Send-Time Optimization dashboard
    app.include_router(send_time_routes.router, prefix="/admin/send-times")
    # v51+ Resend to non-openers
    app.include_router(resend_routes.router, prefix="/admin/resend")
    # v36+ future vision features
    app.include_router(
        events_routes.router, prefix="/events",
        dependencies=[Depends(require_feature(FeatureFlag.EVENTS))],
    )
    app.include_router(
        marketplace_routes.router, prefix="/marketplace",
        dependencies=[Depends(require_feature(FeatureFlag.MARKETPLACE))],
    )
    app.include_router(developer_api_routes.router, prefix="/admin/api")
    # v38+ Developer API v2 (public, auth via API key)
    app.include_router(
        api_v2_routes.router,
        dependencies=[Depends(require_feature(FeatureFlag.API_V2))],
    )

    # Convenience redirects for common short URLs
    from fastapi.responses import RedirectResponse as _Redir

    @app.get("/revenue")
    @app.get("/revenue/")
    async def _revenue_redirect():
        return _Redir("/admin/revenue/", status_code=302)

    @app.get("/admin/security-log")
    @app.get("/security/logs")  # legacy alias
    def security_logs(request: Request):
        """Admin audit log viewer. Reads security_log (written by
        security.py's _log_security_event). Supports ?event_type=X and
        ?limit=N query params for filtering/pagination.

        Uses the shared `render()` helper so the sidebar's `ff()` feature-
        flag global resolves — a prior inline Jinja Environment didn't
        register it and 500'd on every request.
        """
        from weeklyamp.web.deps import get_repo, render
        repo = get_repo()
        event_type = request.query_params.get("event_type", "").strip() or None
        try:
            limit = min(500, int(request.query_params.get("limit") or config.pagination_default))
        except ValueError:
            limit = config.pagination_default
        events = repo.get_security_log(limit=limit, event_type=event_type)
        # Build a list of distinct event types seen in recent history
        # so the filter dropdown reflects real data, not a hardcoded set.
        recent_types = sorted({e.get("event_type", "") for e in repo.get_security_log(limit=500)})
        return HTMLResponse(render(
            "security_logs.html",
            events=events,
            event_type=event_type or "",
            limit=limit,
            event_types=[t for t in recent_types if t],
        ))

    return app
