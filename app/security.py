import json
from datetime import datetime

from fastapi import Depends, HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditEvent, User


password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(
    plain_password: str,
    password_hash: str,
) -> bool:
    return password_hasher.verify(
        plain_password,
        password_hash,
    )


def require_user(
    request: Request,
    db: Session = Depends(get_db),
):

    user_id = request.session.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=303,
            headers={"Location": "/login"},
        )

    user = db.get(User, int(user_id))

    if not user or not user.active:

        request.session.clear()

        raise HTTPException(
            status_code=303,
            headers={"Location": "/login"},
        )

    request.state.user = user

    return user


def require_admin(request: Request):

    user = request.state.user

    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Se requiere perfil Administrador",
        )

    return user


def log_event(
    db: Session,
    request: Request,
    event_type: str,
    prospect_id: int | None = None,
    details: dict | None = None,
):

    user = getattr(
        request.state,
        "user",
        None,
    )

    event = AuditEvent(
        user_id=user.id if user else None,
        prospect_id=prospect_id,
        event_type=event_type,
        happened_at=datetime.utcnow(),
        details_json=(
            json.dumps(
                details,
                ensure_ascii=False,
            )
            if details
            else None
        ),
    )

    db.add(event)
