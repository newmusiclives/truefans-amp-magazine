"""Admin user management."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def users_page(request: Request):
    repo = get_repo()
    users = repo.get_admin_users()
    return HTMLResponse(render("admin_users.html", users=users))


@router.post("/create", response_class=HTMLResponse)
async def create_user(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(""),
    role: str = Form("viewer"),
    password: str = Form(...),
):
    repo = get_repo()
    from weeklyamp.web.security import hash_password

    pw_hash = hash_password(password)
    repo.create_admin_user(email, pw_hash, display_name, role)
    return HTMLResponse(
        f'<div class="alert alert-success">User {email} created as {role}.</div>'
    )


@router.post("/{user_id}/role", response_class=HTMLResponse)
async def update_role(user_id: int, request: Request, role: str = Form(...)):
    repo = get_repo()
    repo.update_admin_user_role(user_id, role)
    return HTMLResponse(f'<span class="badge badge-info">{role}</span>')
