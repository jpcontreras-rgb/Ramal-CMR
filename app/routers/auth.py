from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditEvent, User
from app.security import verify_password


router = APIRouter()

templates = Jinja2Templates(
    directory="app/templates"
)


@router.get(
    "/login",
    response_class=HTMLResponse,
)
def login_page(request: Request):

    if request.session.get("user_id"):
        return RedirectResponse(
            "/",
            status_code=303,
        )

    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": None,
        },
    )


@router.post(
    "/login",
    response_class=HTMLResponse,
)
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):

    username_clean = username.strip().lower()

    user = db.scalar(
        select(User).where(
            func.lower(User.username)
            == username_clean
        )
    )

    valid = (
        user
        and user.active
        and verify_password(
            password,
            user.password_hash,
        )
    )

    if not valid:

        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error":
                    "Usuario o contraseña incorrectos.",
            },
            status_code=401,
        )

    request.session.clear()
    request.session["user_id"] = user.id

    user.last_login_at = datetime.utcnow()

    db.add(
        AuditEvent(
            user_id=user.id,
            event_type="LOGIN",
            happened_at=datetime.utcnow(),
        )
    )

    db.commit()

    return RedirectResponse(
        "/",
        status_code=303,
    )


@router.post("/logout")
def logout(
    request: Request,
    db: Session = Depends(get_db),
):

    user_id = request.session.get("user_id")

    if user_id:

        db.add(
            AuditEvent(
                user_id=int(user_id),
                event_type="LOGOUT",
                happened_at=datetime.utcnow(),
            )
        )

        db.commit()

    request.session.clear()

    return RedirectResponse(
        "/login",
        status_code=303,
    )
