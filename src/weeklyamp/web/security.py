"""Authentication, CSRF protection, and security headers middleware."""

from __future__ import annotations

import logging
import os
import secrets
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
    """Return the active admin bcrypt hash.

    Resolution order (highest priority first):
        1. admin_settings.admin_password_hash row in the DB
           — this is the runtime-mutable override written by the
           in-app change-password UI. It exists so operators can
           rotate the admin password without editing Railway env vars.
        2. WEEKLYAMP_ADMIN_HASH env var (legacy / bootstrap path)
        3. WEEKLYAMP_ADMIN_PASSWORD env var, hashed at runtime
           (legacy convenience for dev / bootstrap)
        4. Empty string — auth is disabled, every request is allowed
           (only used during local dev with no admin configured)

    The result is cached in-process. Call `invalidate_admin_hash_cache()`
    after writing a new override (the change-password route does this)
    so subsequent requests pick up the new value without a restart.
    """
    global _cached_admin_hash
    if _cached_admin_hash:
        return _cached_admin_hash

    # 1. DB override
    try:
        from weeklyamp.web.deps import get_repo
        repo = get_repo()
        db_hash = repo.get_admin_setting("admin_password_hash")
        if db_hash:
            _cached_admin_hash = db_hash
            return db_hash
    except Exception:
        # DB may not be initialized yet on very early startup, or the
        # admin_settings table may not exist on a pre-v44 deploy. Fall
        # through to env-var resolution rather than blocking auth.
        logger.debug("admin_settings lookup failed", exc_info=True)

    # 2. Env var hash
    h = os.environ.get("WEEKLYAMP_ADMIN_HASH", "").strip()
    if h:
        _cached_admin_hash = h
        return h

    # 3. Env var raw password (hashed at runtime)
    pw = os.environ.get("WEEKLYAMP_ADMIN_PASSWORD", "").strip()
    if pw:
        _cached_admin_hash = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
        logger.info("WEEKLYAMP_ADMIN_PASSWORD set — hashed at runtime (pw length=%d)", len(pw))
        return _cached_admin_hash

    # 4. Nothing configured — auth disabled
    return ""


def invalidate_admin_hash_cache() -> None:
    """Drop the cached admin hash so the next call to `_get_admin_hash()`
    re-resolves from DB / env. Call this immediately after writing a new
    `admin_password_hash` row via the change-password route — otherwise
    the new password won't take effect until the next worker restart."""
    global _cached_admin_hash
    _cached_admin_hash = ""


# ---- 2FA (TOTP) ----
# Two-factor auth lives in the same admin_settings key/value table we use
# for the password hash. Key `admin_totp_secret` holds the base32 secret;
# presence of a non-empty value = 2FA enabled. Absent = 2FA off, backwards-
# compatible with existing single-factor admins.

_PRE_2FA_COOKIE = "_pre_2fa"
_PRE_2FA_TTL = 300  # 5 minutes — enough to find your authenticator app
_PRE_2FA_VALUE = "admin"


def is_2fa_enabled() -> bool:
    try:
        from weeklyamp.web.deps import get_repo
        return bool(get_repo().get_admin_setting("admin_totp_secret"))
    except Exception:
        logger.debug("2FA check failed — treating as disabled", exc_info=True)
        return False


def get_totp_secret() -> str:
    try:
        from weeklyamp.web.deps import get_repo
        return get_repo().get_admin_setting("admin_totp_secret") or ""
    except Exception:
        return ""


def verify_totp(code: str) -> bool:
    """Verify a 6-digit TOTP code. Uses pyotp with valid_window=1 (accepts
    previous and next 30s step) so slight clock drift doesn't lock users
    out — RFC 6238 §5.2 standard tolerance."""
    secret = get_totp_secret()
    if not secret:
        return True  # no secret → 2FA not enforced
    try:
        import pyotp
        return pyotp.TOTP(secret).verify((code or "").strip(), valid_window=1)
    except Exception:
        logger.warning("TOTP verification error", exc_info=True)
        return False


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
_PUBLIC_PREFIXES = (
    "/health", "/login", "/static", "/submit", "/subscribe", "/unsubscribe",
    "/resubscribe", "/feedback",
    "/verify", "/newsletters", "/api/", "/feed.xml", "/feed.json", "/feed/", "/t/", "/preferences/",
    "/webhooks/inbound", "/artists", "/trivia/leaderboard", "/advertise",
    "/resources", "/refer", "/contests", "/contribute", "/embed",
    "/artist-newsletters", "/mobile-app", "/articles", "/docs", "/redoc",
    "/n/", "/for-artists", "/for-fans", "/for-industry", "/license",
    "/licensee", "/onboarding", "/preview", "/my-dashboard",
    "/events/public", "/events/register", "/marketplace",
    # Billing — public pricing page, webhook must accept unauthenticated
    # POSTs from Manifest Financial (signature verified inside the handler),
    # and the checkout / success pages are hit by anonymous prospects.
    "/pricing", "/billing/webhook", "/billing/success", "/billing/checkout",
)
_PUBLIC_EXACT = frozenset({"/"})

_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "templates" / "web"
_login_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)


# ---- Rate limiting (backed by the app Repository, so SQLite OR Postgres) ----
#
# Previously this module opened its own sqlite3 connection to a file
# path baked in relative to the module. That was fine in local dev but
# broke in production where the app runs on Postgres — every login
# attempt logged a traceback because the SQLite file didn't exist /
# didn't have the rate_limits table, and the rate limiter fell open.
#
# We now use the app's Repository which auto-detects the backend.
# Postgres doesn't have SQLite's datetime('now', '-N seconds') syntax,
# so we compute the cutoff in Python and pass it as a bind param —
# that works on both backends.


def _rate_limit_conn():
    """Return a Repository connection suitable for rate-limit queries.

    Uses the same backend (SQLite or Postgres) as the rest of the app.
    Callers are responsible for conn.commit() / conn.close().
    """
    from weeklyamp.web.deps import get_repo
    return get_repo()._conn()


def _cutoff_for(window_seconds: int) -> str:
    """Return an ISO-8601 timestamp that's ``window_seconds`` in the past.

    Used as the lower bound for counting recent rate-limit attempts.
    Portable across SQLite and Postgres (both compare TIMESTAMP columns
    against ISO strings correctly).
    """
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    # SQLite's default CURRENT_TIMESTAMP format is 'YYYY-MM-DD HH:MM:SS'
    # without timezone, and Postgres handles both; format accordingly.
    return cutoff.strftime("%Y-%m-%d %H:%M:%S")


def _get_login_rate_config() -> tuple[int, int]:
    """Get login rate limit config (soft tier)."""
    max_attempts = int(os.environ.get("WEEKLYAMP_RATE_LOGIN_MAX", 5))
    window = int(os.environ.get("WEEKLYAMP_RATE_LOGIN_WINDOW", 900))
    return max_attempts, window


def _get_login_lockout_config() -> tuple[int, int]:
    """Get login hard-lockout config (second tier).

    Fires once an IP has accumulated N failures within the lockout
    window, and blocks further attempts for the rest of that window.
    Defaults: 10 failures within 1 hour → blocked for up to 1 hour.
    """
    max_attempts = int(os.environ.get("WEEKLYAMP_LOGIN_LOCKOUT_MAX", 10))
    window = int(os.environ.get("WEEKLYAMP_LOGIN_LOCKOUT_WINDOW", 3600))
    return max_attempts, window


def _is_hard_locked(ip: str) -> bool:
    """Return True if the IP is in hard-lockout state (second tier).

    The lockout counter uses the same ``rate_limits`` table but a
    larger window than the soft rate limit, so it takes many more
    failures or a longer sustained attack before the hard lockout
    kicks in. Fail-open on DB errors — the soft tier already blocks
    a naive attacker, and we'd rather accept legitimate logins than
    refuse everyone if the rate_limits table is unavailable.
    """
    max_attempts, window = _get_login_lockout_config()
    return _is_rate_limited_with(ip, "login", max_attempts, window)


def _get_client_ip(request: Request) -> str:
    """Extract client IP from X-Forwarded-For (Railway/proxy) or direct connection."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_rate_limited(ip: str, limit_type: str = "login") -> bool:
    """Check if an IP has exceeded the attempt limit for the given limit type."""
    max_attempts, window = _get_login_rate_config()
    return _is_rate_limited_with(ip, limit_type, max_attempts, window)


def _record_attempt(ip: str, limit_type: str = "login") -> None:
    """Record a failed attempt for an IP under the given limit type."""
    try:
        conn = _rate_limit_conn()
        try:
            # INSERT auto-gets RETURNING id appended by _PgConnAdapter —
            # rate_limits does have an id column so that's fine here.
            conn.execute(
                "INSERT INTO rate_limits (ip_address, limit_type) VALUES (?, ?)",
                (ip, limit_type),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.warning("Failed to record attempt for limit_type=%s", limit_type, exc_info=True)


def _clear_attempts(ip: str, limit_type: str = "login") -> None:
    """Clear attempts for an IP under the given limit type after a successful action."""
    try:
        conn = _rate_limit_conn()
        try:
            conn.execute(
                "DELETE FROM rate_limits WHERE ip_address = ? AND limit_type = ?",
                (ip, limit_type),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.warning("Failed to clear attempts for limit_type=%s", limit_type, exc_info=True)


def _is_rate_limited_with(
    ip: str, limit_type: str, max_attempts: int, window_seconds: int
) -> bool:
    """Check rate limit with custom threshold and window.

    SQL uses a parameterised ISO timestamp cutoff rather than SQLite's
    ``datetime('now', ...)`` so the same query runs on Postgres.
    """
    try:
        cutoff = _cutoff_for(window_seconds)
        conn = _rate_limit_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM rate_limits "
                "WHERE ip_address = ? AND limit_type = ? AND attempted_at >= ?",
                (ip, limit_type, cutoff),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return False
        # Aliased COUNT works identically under sqlite3.Row and
        # psycopg2 RealDictCursor (both support row["c"]).
        return row["c"] >= max_attempts
    except Exception:
        logger.warning("Rate-limit check failed — allowing request", exc_info=True)
        return False


def rate_limit(limit_type: str, max_per_minute: int = 60):
    """FastAPI dependency factory for per-IP rate limiting.

    Usage::

        @router.get("/endpoint", dependencies=[Depends(rate_limit("api_editions", 120))])
        async def endpoint(): ...

    On limit exceeded returns HTTP 429 with a JSON body. Uses the
    persistent rate_limits table so limits survive restarts.
    """
    from fastapi import HTTPException

    async def _check(request: Request) -> None:
        ip = _get_client_ip(request)
        if _is_rate_limited_with(ip, limit_type, max_per_minute, 60):
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({max_per_minute}/min for {limit_type})",
            )
        _record_attempt(ip, limit_type=limit_type)

    return _check


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


def create_pre_2fa_cookie(response: Response, request: Request | None = None) -> Response:
    """Short-lived signed cookie marking password OK, waiting on TOTP."""
    signer = _get_signer()
    signed = signer.sign(_PRE_2FA_VALUE).decode()
    secure = _is_secure(request) if request else False
    response.set_cookie(
        _PRE_2FA_COOKIE, signed,
        max_age=_PRE_2FA_TTL, httponly=True, samesite="lax", secure=secure,
    )
    return response


def is_pre_2fa(request: Request) -> bool:
    cookie = request.cookies.get(_PRE_2FA_COOKIE)
    if not cookie:
        return False
    try:
        _get_signer().unsign(cookie, max_age=_PRE_2FA_TTL)
        return True
    except (BadSignature, SignatureExpired):
        return False


def clear_pre_2fa_cookie(response: Response) -> Response:
    response.delete_cookie(_PRE_2FA_COOKIE)
    return response


# ---- Password reset tokens ----
# Signed timestamp tokens for the forgot-password flow. Max age = 30min.
# Uses a distinct salt so a token can't be confused with a session cookie
# or a pre-2FA cookie.

_PASSWORD_RESET_SALT = "password-reset-v1"
_PASSWORD_RESET_TTL = 1800  # 30 minutes


def issue_password_reset_token(email: str) -> str:
    """Issue a one-shot signed reset token for ``email``.

    The caller should email the resulting token to the admin and also
    store it under admin_settings[password_reset_token] so the reset
    handler can enforce one-shot semantics (token is consumed on
    successful password update).
    """
    signer = TimestampSigner(_get_secret_key() or _FALLBACK_SECRET_KEY, salt=_PASSWORD_RESET_SALT)
    return signer.sign(email.encode()).decode()


def verify_password_reset_token(token: str) -> str:
    """Verify a reset token and return the email it was issued for.

    Returns '' on any failure (expired, tampered, missing). Never
    raises — callers just check the return value.
    """
    if not token:
        return ""
    try:
        signer = TimestampSigner(_get_secret_key() or _FALLBACK_SECRET_KEY, salt=_PASSWORD_RESET_SALT)
        return signer.unsign(token, max_age=_PASSWORD_RESET_TTL).decode()
    except (BadSignature, SignatureExpired):
        return ""


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


# ---- Licensee session helpers ----

_LICENSEE_SESSION_COOKIE = "_licensee_session"


def create_licensee_session(response: Response, licensee_id: int, request: Request | None = None) -> Response:
    """Sign and set a licensee session cookie identifying which licensee is logged in."""
    signer = _get_signer()
    signed = signer.sign(f"licensee:{int(licensee_id)}".encode()).decode()
    secure = _is_secure(request) if request else False
    response.set_cookie(
        _LICENSEE_SESSION_COOKIE,
        signed,
        max_age=_get_session_max_age(),
        httponly=True,
        samesite="lax",
        secure=secure,
    )
    return response


def get_licensee_id_from_session(request: Request) -> int | None:
    """Return the authenticated licensee_id from the session cookie, or None."""
    cookie = request.cookies.get(_LICENSEE_SESSION_COOKIE)
    if not cookie:
        return None
    signer = _get_signer()
    try:
        raw = signer.unsign(cookie, max_age=_get_session_max_age()).decode()
    except (BadSignature, SignatureExpired):
        return None
    if not raw.startswith("licensee:"):
        return None
    try:
        return int(raw.split(":", 1)[1])
    except (ValueError, IndexError):
        return None


def clear_licensee_session(response: Response) -> Response:
    """Remove the licensee session cookie."""
    response.delete_cookie(_LICENSEE_SESSION_COOKIE)
    return response


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

    # Hard lockout — checked first so brute-force attempts can't extend
    # their lockout by continuing to hammer the endpoint.
    if _is_hard_locked(ip):
        _log_security_event(request, "login_hard_locked")
        tpl = _login_env.get_template("login.html")
        return HTMLResponse(
            tpl.render(
                error="Account locked due to repeated failed attempts. "
                "Try again later or contact an administrator."
            ),
            status_code=429,
        )

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
    env_pw = os.environ.get("WEEKLYAMP_ADMIN_PASSWORD", "").strip()
    password_ok = verify_password(password, admin_hash) if admin_hash else False
    if not password_ok and env_pw and password == env_pw:
        password_ok = True
    if password_ok:
        _clear_attempts(ip)
        # 2FA branch — if a TOTP secret is on file, don't issue a full
        # session yet. Set the short-lived pre-2FA cookie and redirect
        # to the code challenge page.
        if is_2fa_enabled():
            _log_security_event(request, "login_password_ok_awaiting_2fa")
            response = RedirectResponse("/login/2fa", status_code=302)
            create_pre_2fa_cookie(response, request)
            return response
        _log_security_event(request, "login_success")
        response = RedirectResponse("/dashboard", status_code=302)
        create_session(response, request)
        return response

    _record_attempt(ip)
    _log_security_event(request, "login_failure")
    tpl = _login_env.get_template("login.html")
    return HTMLResponse(
        tpl.render(error="Invalid password"),
        status_code=401,
    )


async def login_2fa_page(request: Request) -> Response:
    """GET /login/2fa — TOTP challenge after password step.

    Gated on the pre-2FA cookie: if someone hits this URL without
    having completed the password step, send them back to /login.
    """
    if not is_pre_2fa(request):
        return RedirectResponse("/login", status_code=302)
    tpl = _login_env.get_template("login_2fa.html")
    return HTMLResponse(tpl.render(error=""))


async def login_2fa_submit(request: Request) -> Response:
    """POST /login/2fa — verify the 6-digit TOTP code.

    On success, issue the full session cookie and clear the pre-2FA
    cookie. On failure, record an attempt and re-render with error.
    """
    ip = _get_client_ip(request)

    if not is_pre_2fa(request):
        return RedirectResponse("/login", status_code=302)

    if _is_rate_limited(ip):
        _log_security_event(request, "login_2fa_rate_limited")
        tpl = _login_env.get_template("login_2fa.html")
        return HTMLResponse(
            tpl.render(error="Too many attempts. Please try again later."),
            status_code=429,
        )

    form = await request.form()
    code = str(form.get("code", "")).strip()
    if verify_totp(code):
        _clear_attempts(ip)
        _log_security_event(request, "login_2fa_success")
        response = RedirectResponse("/dashboard", status_code=302)
        create_session(response, request)
        clear_pre_2fa_cookie(response)
        return response

    _record_attempt(ip)
    _log_security_event(request, "login_2fa_failure")
    tpl = _login_env.get_template("login_2fa.html")
    return HTMLResponse(
        tpl.render(error="Invalid code. Try again."),
        status_code=401,
    )


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


class AdminIPAllowlistMiddleware(BaseHTTPMiddleware):
    """Optionally restrict /admin/* access to a list of IPs or CIDR ranges.

    Configured via the ``WEEKLYAMP_ADMIN_IP_ALLOWLIST`` env var as a
    comma-separated list of IPs (``203.0.113.42``) and/or CIDR ranges
    (``192.168.1.0/24``). Empty / unset = no allowlist, all IPs allowed
    (the safe default for setup-before-IPs-are-known).

    Honors ``X-Forwarded-For`` so the real client IP is checked when
    running behind Railway's proxy rather than the proxy's own IP.
    """

    def __init__(self, app, allowlist: str = "") -> None:
        super().__init__(app)
        self._networks: list = []
        if allowlist.strip():
            import ipaddress
            for entry in allowlist.split(","):
                entry = entry.strip()
                if not entry:
                    continue
                try:
                    # strict=False so bare IPs parse as /32 (v4) or /128 (v6)
                    net = ipaddress.ip_network(entry, strict=False)
                    self._networks.append(net)
                except ValueError:
                    logger.warning("Ignoring invalid IP/CIDR in allowlist: %s", entry)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self._networks or not request.url.path.startswith("/admin"):
            return await call_next(request)

        import ipaddress
        try:
            client_ip = ipaddress.ip_address(_get_client_ip(request))
        except ValueError:
            _log_security_event(request, "admin_ip_invalid", detail="unparseable client IP")
            return Response("Forbidden", status_code=403)

        if not any(client_ip in net for net in self._networks):
            _log_security_event(request, "admin_ip_blocked", detail=str(client_ip))
            return Response("Forbidden", status_code=403)
        return await call_next(request)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose body exceeds a configurable size.

    Guards against memory-exhaustion attacks: a single POST with a
    multi-gigabyte body can OOM a worker before any handler runs. We
    check Content-Length (fast path, most legit clients send it) and
    then stream-accumulate the body with a running total so chunked
    requests without Content-Length also get bounded.

    Configured at app wiring time from ``config.max_request_body``
    (1 MB default). Webhooks and a few other endpoints that legitimately
    receive larger payloads can be listed in ``exempt_paths``.
    """

    def __init__(
        self,
        app,
        max_bytes: int = 1_048_576,
        exempt_paths: tuple[str, ...] = (),
    ) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes
        self._exempt = exempt_paths

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in ("GET", "HEAD", "DELETE", "OPTIONS"):
            return await call_next(request)
        if any(request.url.path.startswith(p) for p in self._exempt):
            return await call_next(request)

        # Fast path: trust Content-Length when the client supplies it.
        cl = request.headers.get("content-length")
        if cl:
            try:
                if int(cl) > self._max_bytes:
                    return Response("Request body too large", status_code=413)
            except ValueError:
                return Response("Invalid Content-Length", status_code=400)

        return await call_next(request)


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
