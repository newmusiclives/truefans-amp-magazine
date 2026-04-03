"""Authentication, CSRF protection, and security headers middleware."""

from __future__ import annotations

import logging
import os
import secrets
import sqlite3
from pathlib import Path

import bcrypt
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from jinja2 import Environment, FileSystemLoader
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)

def _get_secret_key() -> str:
    return os.environ.get("WEEKLYAMP_SECRET_KEY", "")


_cached_admin_hash: str | None = None


def _get_admin_hash() -> str:
    global _cached_admin_hash
    # Only use cache if we got a real hash (not empty)
    if _cached_admin_hash:
        return _cached_admin_hash
    h = os.environ.get("WEEKLYAMP_ADMIN_HASH", "").strip()
    if h:
        _cached_admin_hash = h
        return h
    pw = os.environ.get("WEEKLYAMP_ADMIN_PASSWORD", "").strip()
    if pw:
        _cached_admin_hash = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
        logger.info("WEEKLYAMP_ADMIN_PASSWORD set — hashed at runtime (pw length=%d)", len(pw))
        return _cached_admin_hash
    # Don't cache empty — re-check env vars on next call
    return ""


# Fallback secret key for dev when env var is not set
_FALLBACK_SECRET_KEY = ""

_SESSION_COOKIE = "_session"
_SESSION_VALUE = "admin"


def _get_session_max_age() -> int:
    """Get session max age from config, with fallback."""
    import os
    return int(os.environ.get("WEEKLYAMP_SESSION_MAX_AGE", 43200))

_CSRF_COOKIE = "_csrf"

# Routes that don't require authentication
_PUBLIC_PREFIXES = ("/health", "/login", "/static", "/submit", "/subscribe", "/unsubscribe", "/verify", "/newsletters", "/api/", "/feed.xml", "/t/", "/preferences/", "/webhooks/inbound", "/artists", "/trivia/leaderboard", "/advertise", "/resources", "/refer", "/contests", "/contribute", "/embed")
_PUBLIC_EXACT = frozenset({"/"})

_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "templates" / "web"
_login_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)


# ---- Rate limiting (SQLite-backed, survives restarts) ----

_DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "weeklyamp.db"


def _rate_limit_conn():
    """Open a lightweight SQLite connection for rate-limit queries."""
    return sqlite3.connect(str(_DB_PATH))


def _get_login_rate_config() -> tuple[int, int]:
    """Get login rate limit config."""
    max_attempts = int(os.environ.get("WEEKLYAMP_RATE_LOGIN_MAX", 5))
    window = int(os.environ.get("WEEKLYAMP_RATE_LOGIN_WINDOW", 900))
    return max_attempts, window


def _get_client_ip(request: Request) -> str:
    """Extract client IP from X-Forwarded-For (Railway/proxy) or direct connection."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_rate_limited(ip: str) -> bool:
    """Check if an IP has exceeded the login attempt limit."""
    max_attempts, window = _get_login_rate_config()
    try:
        conn = _rate_limit_conn()
        row = conn.execute(
            "SELECT COUNT(*) FROM rate_limits "
            "WHERE ip_address = ? AND limit_type = 'login' "
            "AND attempted_at >= datetime('now', '-' || ? || ' seconds')",
            (ip, window),
        ).fetchone()
        conn.close()
        return (row[0] if row else 0) >= max_attempts
    except Exception:
        logger.warning("Rate-limit check failed — allowing request", exc_info=True)
        return False


def _record_attempt(ip: str) -> None:
    """Record a failed login attempt for an IP."""
    try:
        conn = _rate_limit_conn()
        conn.execute(
            "INSERT INTO rate_limits (ip_address, limit_type) VALUES (?, 'login')",
            (ip,),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.warning("Failed to record login attempt", exc_info=True)


def _clear_attempts(ip: str) -> None:
    """Clear login attempts for an IP after successful login."""
    try:
        conn = _rate_limit_conn()
        conn.execute(
            "DELETE FROM rate_limits WHERE ip_address = ? AND limit_type = 'login'",
            (ip,),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.warning("Failed to clear login attempts", exc_info=True)


# ---- Secure cookie helpers ----

def _is_secure(request: Request) -> bool:
    """Check if the request arrived over HTTPS (via proxy header)."""
    return request.headers.get("X-Forwarded-Proto") == "https"


# ---- Password helpers ----

def hash_password(password: str) -> str:
    """Hash a password with bcrypt. Use this to generate WEEKLYAMP_ADMIN_HASH."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


# ---- Session helpers ----

def _get_signer() -> TimestampSigner:
    global _FALLBACK_SECRET_KEY
    key = _get_secret_key()
    if not key:
        if not _FALLBACK_SECRET_KEY:
            _FALLBACK_SECRET_KEY = secrets.token_hex(32)
            logger.warning("WEEKLYAMP_SECRET_KEY not set — using random key (sessions won't survive restarts)")
        key = _FALLBACK_SECRET_KEY
    return TimestampSigner(key)


def create_session(response: Response, request: Request | None = None) -> Response:
    """Sign and set the session cookie on a response."""
    signer = _get_signer()
    signed = signer.sign(_SESSION_VALUE).decode()
    secure = _is_secure(request) if request else False
    response.set_cookie(
        _SESSION_COOKIE,
        signed,
        max_age=_get_session_max_age(),
        httponly=True,
        samesite="lax",
        secure=secure,
    )
    return response


def clear_session(response: Response) -> Response:
    """Remove the session cookie."""
    response.delete_cookie(_SESSION_COOKIE)
    response.delete_cookie(_CSRF_COOKIE)
    return response


def is_authenticated(request: Request) -> bool:
    """Check if the request has a valid session cookie."""
    if not _get_admin_hash():
        # No password configured — auth disabled (dev mode)
        return True
    cookie = request.cookies.get(_SESSION_COOKIE)
    if not cookie:
        return False
    signer = _get_signer()
    try:
        signer.unsign(cookie, max_age=_get_session_max_age())
        return True
    except (BadSignature, SignatureExpired):
        return False


def _is_public(path: str) -> bool:
    """Check if a path is publicly accessible without auth."""
    if path in _PUBLIC_EXACT:
        return True
    return any(path.startswith(p) for p in _PUBLIC_PREFIXES)


# ---- Audit logging helper ----

def _log_security_event(request: Request, event_type: str, detail: str = "") -> None:
    """Log a security event to the database (best-effort)."""
    try:
        from weeklyamp.web.deps import get_repo
        repo = get_repo()
        repo.log_security_event(
            event_type=event_type,
            ip_address=_get_client_ip(request),
            user_agent=request.headers.get("User-Agent", "")[:500],
            detail=detail,
        )
    except Exception:
        logger.warning("Failed to write security log event: %s", event_type, exc_info=True)


# ---- Login / Logout route handlers ----

async def login_page(request: Request) -> Response:
    """GET /login — render login form."""
    if is_authenticated(request):
        return RedirectResponse("/dashboard", status_code=302)
    csrf_token = secrets.token_hex(32)
    tpl = _login_env.get_template("login.html")
    response = HTMLResponse(tpl.render(csrf_token=csrf_token))
    response.set_cookie(
        "_login_csrf", csrf_token,
        httponly=True, samesite="lax", max_age=900, secure=False,
        path="/login",
    )
    return response


async def login_submit(request: Request) -> Response:
    """POST /login — validate password and set session."""
    ip = _get_client_ip(request)

    # Rate limit check
    if _is_rate_limited(ip):
        _log_security_event(request, "login_rate_limited")
        tpl = _login_env.get_template("login.html")
        return HTMLResponse(
            tpl.render(error="Too many login attempts. Please try again later."),
            status_code=429,
        )

    form = await request.form()
    password = form.get("password", "").strip()

    admin_hash = _get_admin_hash()
    logger.info("Login attempt — password length: %d, hash present: %s", len(password), bool(admin_hash))
    if verify_password(password, admin_hash):
        _clear_attempts(ip)
        _log_security_event(request, "login_success")
        response = RedirectResponse("/dashboard", status_code=302)
        create_session(response, request)
        return response

    _record_attempt(ip)
    _log_security_event(request, "login_failure")
    tpl = _login_env.get_template("login.html")
    return HTMLResponse(tpl.render(error="Invalid password"), status_code=401)


async def logout(request: Request) -> Response:
    """GET /logout — clear session and redirect to login."""
    _log_security_event(request, "logout")
    response = RedirectResponse("/login", status_code=302)
    clear_session(response)
    return response


# ---- Middleware ----

_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://unpkg.com https://plausible.io; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "connect-src 'self'; "
    "img-src 'self' data: https:; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response."""

    # Routes that need to be loaded in a same-origin iframe
    _FRAMEABLE_PATHS = {"/publish/preview"}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # Prevent browser caching of HTML pages (not static assets)
        if not request.url.path.startswith("/static"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"

        if request.url.path in self._FRAMEABLE_PATHS:
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
            response.headers["Content-Security-Policy"] = _CSP.replace(
                "frame-ancestors 'none'", "frame-ancestors 'self'"
            )
        else:
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Content-Security-Policy"] = _CSP
        # HSTS only over HTTPS
        if request.headers.get("X-Forwarded-Proto") == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        return response


class AuthMiddleware(BaseHTTPMiddleware):
    """Require authentication for non-public routes."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if _is_public(request.url.path):
            return await call_next(request)

        if not is_authenticated(request):
            # For htmx requests, return 401 so JS can redirect
            if request.headers.get("HX-Request"):
                return Response(
                    status_code=401,
                    headers={"HX-Redirect": "/login"},
                )
            return RedirectResponse("/login", status_code=302)

        return await call_next(request)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF protection for state-changing requests."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Check CSRF for state-changing methods on authenticated routes
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            if not _is_public(request.url.path) and is_authenticated(request):
                cookie_token = request.cookies.get(_CSRF_COOKIE, "")
                header_token = request.headers.get("X-CSRF-Token", "")
                if not cookie_token or not header_token or cookie_token != header_token:
                    return Response("CSRF token mismatch", status_code=403)

        response = await call_next(request)

        # Set/refresh CSRF cookie on authenticated responses
        if is_authenticated(request) and not _is_public(request.url.path):
            if _CSRF_COOKIE not in request.cookies:
                csrf_token = secrets.token_hex(32)
                secure = _is_secure(request)
                response.set_cookie(
                    _CSRF_COOKIE,
                    csrf_token,
                    httponly=False,  # JS needs to read this
                    samesite="lax",
                    max_age=_get_session_max_age(),
                    secure=secure,
                )

        return response
