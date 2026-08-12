from decimal import Decimal
from getpass import getpass

from sqlalchemy import select

from app.db import SessionLocal
from app.models import User
from app.security import hash_password


db = SessionLocal()

try:

    print("\n=== Crear usuario Ramal CRM ===\n")

    username = input(
        "Usuario: "
    ).strip().lower()

    full_name = input(
        "Nombre completo: "
    ).strip()

    role = input(
        "Perfil [admin/sales]: "
    ).strip().lower()

    if role not in {
        "admin",
        "sales",
    }:
        raise ValueError(
            "Perfil inválido."
        )

    if role == "sales":

        discount = Decimal(
            input(
                "Descuento máximo % [0]: "
            ).strip()
            or "0"
        )

    else:
        discount = Decimal("100")

    password = getpass(
        "Contraseña: "
    )

    password2 = getpass(
        "Repite contraseña: "
    )

    if password != password2:
        raise ValueError(
            "Las contraseñas no coinciden."
        )

    if len(password) < 8:
        raise ValueError(
            "La contraseña debe tener al menos 8 caracteres."
        )

    existing = db.scalar(
        select(User).where(
            User.username == username
        )
    )

    if existing:
        raise ValueError(
            "Ese usuario ya existe."
        )

    user = User(
        username=username,
        full_name=full_name,
        password_hash=hash_password(password),
        role=role,
        max_discount_pct=discount,
        active=True,
    )

    db.add(user)

    db.commit()

    print(
        f"\nUsuario {username} creado correctamente.\n"
    )

finally:
    db.close()
