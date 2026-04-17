"""Admin feature flag toggle UI.

Mounted at /admin/feature-flags (see app.py). Grouped by category, with
htmx-powered per-toggle POST that writes the DB and invalidates the
in-process cache immediately. No page reload needed.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from weeklyamp.core.feature_flags import (
    FLAG_METADATA,
    LAUNCH_SET,
    enabled,
    invalidate_cache,
)
from weeklyamp.web.deps import get_repo, render
from weeklyamp.web.security import is_authenticated

router = APIRouter()


def _require_admin(request: Request) -> Response | None:
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)
    return None


def _grouped_flags() -> dict[str, list[dict]]:
    """Return flags grouped for the admin UI.

    A pinned "Launch Set" group comes first, containing the ten flags
    recommended ON for the minimum-viable public launch (see
    :data:`weeklyamp.core.feature_flags.LAUNCH_SET`). The remaining
    flags are grouped by their FLAG_METADATA category underneath.

    A flag appearing in LAUNCH_SET is NOT duplicated in its original
    category group — the Launch Set is its canonical home in the UI.
    """
    def _entry(key: str) -> dict:
        label, _category, description = FLAG_METADATA[key]
        return {
            "key": key,
            "label": label,
            "description": description,
            "enabled": enabled(key),
        }

    groups: dict[str, list[dict]] = {
        "Launch Set (minimum viable)": [_entry(k) for k in LAUNCH_SET if k in FLAG_METADATA],
    }
    launch_set = set(LAUNCH_SET)
    for key, (label, category, description) in FLAG_METADATA.items():
        if key in launch_set:
            continue
        cat = category or "Other"
        groups.setdefault(cat, []).append(_entry(key))
    return groups


@router.get("/feature-flags", response_class=HTMLResponse)
async def feature_flags_page(request: Request) -> Response:
    redirect = _require_admin(request)
    if redirect is not None:
        return redirect
    return HTMLResponse(render("admin_feature_flags.html", groups=_grouped_flags()))


@router.post("/feature-flags/toggle")
async def feature_flags_toggle(
    request: Request,
    key: str = Form(...),
    enabled_value: str = Form(""),
) -> Response:
    """htmx POST target. Form posts key=<flag>&enabled_value=on|<empty>.

    An unchecked checkbox does not submit its value, so an empty
    `enabled_value` means "turn off" and "on" means "turn on".
    """
    redirect = _require_admin(request)
    if redirect is not None:
        return redirect
    if key not in FLAG_METADATA:
        # Reject unknown flag keys — prevents writing arbitrary rows
        # via a crafted POST.
        return HTMLResponse("Unknown flag", status_code=400)

    new_value = enabled_value.lower() in ("on", "true", "1", "yes")
    label, category, description = FLAG_METADATA[key]
    repo = get_repo()
    repo.set_feature_flag(key, new_value, description=description, category=category)
    invalidate_cache(key)

    # Return a fragment the htmx swap can drop back into the row so the
    # toggle visibly reflects the new state without a page reload.
    return HTMLResponse(
        render(
            "admin_feature_flags_row.html",
            flag={
                "key": key,
                "label": label,
                "description": description,
                "enabled": new_value,
            },
        )
    )
