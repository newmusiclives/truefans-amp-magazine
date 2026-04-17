"""Admin 2FA (TOTP) management — enroll, verify, disable.

Routes mount under /admin/2fa (see app.py). The TOTP secret is stored
in admin_settings under key `admin_totp_secret`. Enrollment is a
two-step flow (show QR → verify code → persist) so we don't activate
2FA until the admin has proven they have a working authenticator entry.
"""

from __future__ import annotations

import base64
import io

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from weeklyamp.web.deps import get_repo, render
from weeklyamp.web.security import (
    get_totp_secret,
    is_2fa_enabled,
    is_authenticated,
    verify_totp,
)

router = APIRouter()


def _require_admin(request: Request) -> Response | None:
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)
    return None


def _pending_secret_key(request: Request) -> str:
    """Per-session pending secret key in admin_settings.

    Store the enrollment candidate under a per-SESSION key so multiple
    admins (or the same admin re-enrolling) don't trample each other.
    Sessions are shared here, so we key on the session cookie suffix.
    """
    cookie = request.cookies.get("_session", "")
    # Short, deterministic suffix — no PII.
    suffix = cookie[-12:] if cookie else "default"
    return f"admin_totp_pending:{suffix}"


def _otpauth_uri(secret: str, label: str = "TrueFans SIGNAL") -> str:
    import pyotp
    return pyotp.TOTP(secret).provisioning_uri(
        name="admin", issuer_name=label
    )


def _qr_svg_data_uri(uri: str) -> str:
    """Render the otpauth URI as an inline SVG data URI.

    Using qrcode's SVG factory keeps us off PIL (which needs a native
    image library) — small dep, small image.
    """
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgImage, box_size=8)
    buf = io.BytesIO()
    img.save(buf)
    svg = buf.getvalue()
    b64 = base64.b64encode(svg).decode()
    return f"data:image/svg+xml;base64,{b64}"


@router.get("/2fa", response_class=HTMLResponse)
async def twofa_status(request: Request) -> Response:
    """Status page: shows whether 2FA is on and offers enroll/disable."""
    redirect = _require_admin(request)
    if redirect is not None:
        return redirect
    return HTMLResponse(render(
        "admin_2fa.html",
        enabled=is_2fa_enabled(),
    ))


@router.get("/2fa/enroll", response_class=HTMLResponse)
async def twofa_enroll_page(request: Request) -> Response:
    """Show QR code + verification form for a fresh secret."""
    redirect = _require_admin(request)
    if redirect is not None:
        return redirect

    import pyotp
    repo = get_repo()

    # Reuse the pending secret if the admin refreshed the page; only
    # generate a new one if none is in-flight. This avoids rotating
    # secrets on every page reload while the admin is scanning.
    pending_key = _pending_secret_key(request)
    secret = repo.get_admin_setting(pending_key) or pyotp.random_base32()
    repo.set_admin_setting(pending_key, secret)

    uri = _otpauth_uri(secret)
    return HTMLResponse(render(
        "admin_2fa_enroll.html",
        secret=secret,
        qr_data_uri=_qr_svg_data_uri(uri),
        otpauth_uri=uri,
        error="",
    ))


@router.post("/2fa/enroll")
async def twofa_enroll_verify(
    request: Request,
    code: str = Form(...),
) -> Response:
    """Verify the entered code against the pending secret; if valid,
    promote it to the live admin_totp_secret and clear the pending row."""
    redirect = _require_admin(request)
    if redirect is not None:
        return redirect

    repo = get_repo()
    pending_key = _pending_secret_key(request)
    secret = repo.get_admin_setting(pending_key)
    if not secret:
        # Pending row expired / missing — send them back to enroll start.
        return RedirectResponse("/admin/2fa/enroll", status_code=302)

    import pyotp
    if not pyotp.TOTP(secret).verify((code or "").strip(), valid_window=1):
        return HTMLResponse(
            render(
                "admin_2fa_enroll.html",
                secret=secret,
                qr_data_uri=_qr_svg_data_uri(_otpauth_uri(secret)),
                otpauth_uri=_otpauth_uri(secret),
                error="That code didn't match. Check your authenticator app and try again.",
            ),
            status_code=400,
        )

    # Promote pending → live, clear pending.
    repo.set_admin_setting("admin_totp_secret", secret)
    repo.set_admin_setting(pending_key, "")
    return RedirectResponse("/admin/2fa", status_code=302)


@router.post("/2fa/disable")
async def twofa_disable(
    request: Request,
    code: str = Form(...),
) -> Response:
    """Disable 2FA — requires a valid current TOTP code so a stolen
    session cookie alone can't turn it off."""
    redirect = _require_admin(request)
    if redirect is not None:
        return redirect

    if not verify_totp(code):
        return HTMLResponse(
            render(
                "admin_2fa.html",
                enabled=is_2fa_enabled(),
                error="Current TOTP code required to disable 2FA.",
            ),
            status_code=400,
        )

    repo = get_repo()
    repo.set_admin_setting("admin_totp_secret", "")
    return RedirectResponse("/admin/2fa", status_code=302)
