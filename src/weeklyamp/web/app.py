"""FastAPI web application for the TrueFans AMP Magazine dashboard."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

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

    # Security logs (authenticated, inline)
    from fastapi.responses import HTMLResponse

    @app.get("/security/logs")
    def security_logs():
        from weeklyamp.web.deps import get_repo
        repo = get_repo()
        events = repo.get_security_log(limit=50)
        rows = ""
        for ev in events:
            rows += (
                f"<tr><td>{ev.get('created_at','')}</td>"
                f"<td>{ev.get('event_type','')}</td>"
                f"<td>{ev.get('ip_address','')}</td>"
                f"<td>{ev.get('user_agent','')[:80]}</td>"
                f"<td>{ev.get('detail','')}</td></tr>"
            )
        if not rows:
            rows = '<tr><td colspan="5" style="text-align:center;color:#888">No events yet</td></tr>'
        html = (
            '<!DOCTYPE html><html><head><title>Security Logs</title>'
            '<link rel="stylesheet" href="/static/style.css">'
            '<style>table{width:100%;border-collapse:collapse;font-size:13px}'
            'th,td{padding:8px 12px;border-bottom:1px solid var(--border);text-align:left}'
            'th{font-weight:600;color:var(--text-dim)}</style></head>'
            '<body style="padding:32px;max-width:1200px;margin:0 auto">'
            '<h2>Security Audit Log</h2>'
            '<p><a href="/">&larr; Dashboard</a></p>'
            '<table><thead><tr><th>Time</th><th>Event</th><th>IP</th>'
            '<th>User Agent</th><th>Detail</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></body></html>'
        )
        return HTMLResponse(html)

    return app
