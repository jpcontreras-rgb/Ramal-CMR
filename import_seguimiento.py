from __future__ import annotations

import csv
from datetime import datetime, time
from pathlib import Path

from sqlalchemy import func, or_, select

from app.db import SessionLocal
from app.models import Activity, Contact, Prospect, ProspectStatus


CSV_PATH = Path(__file__).parent / "data" / "seguimiento_import.csv"


def norm(s: str | None) -> str:
    return (s or "").strip()


def dt_from_date(value: str, hour: int = 12):
    if not value:
        return None
    try:
        d = datetime.strptime(value, "%Y-%m-%d").date()
        return datetime.combine(d, time(hour, 0))
    except ValueError:
        return None


def find_existing_prospect(db, company_name: str, email: str, phone: str):
    # Prefer exact unique contact information. Only fall back to company name
    # when the row has no email and no phone.
    if email:
        p = db.scalar(
            select(Prospect).where(
                func.lower(Prospect.email) == email.lower()
            )
        )
        if p:
            return p

    if phone:
        p = db.scalar(
            select(Prospect).where(Prospect.phone == phone)
        )
        if p:
            return p

    if not email and not phone:
        return db.scalar(
            select(Prospect).where(
                func.lower(Prospect.company_name) == company_name.lower(),
                Prospect.source == "Plantilla de Seguimiento",
            )
        )

    return None


def contact_exists(db, prospect_id: int, name: str, email: str):
    q = select(Contact).where(Contact.prospect_id == prospect_id)
    if email:
        q = q.where(func.lower(Contact.email) == email.lower())
    elif name:
        q = q.where(func.lower(Contact.name) == name.lower())
    else:
        return True
    return db.scalar(q) is not None


def activity_exists(db, prospect_id: int, marker: str):
    return db.scalar(
        select(Activity).where(
            Activity.prospect_id == prospect_id,
            Activity.result.ilike(f"%{marker}%"),
        )
    ) is not None


def main():
    if not CSV_PATH.exists():
        raise SystemExit(f"No se encontró {CSV_PATH}")

    created = 0
    updated = 0
    contacts_created = 0
    activities_created = 0
    skipped = 0

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    db = SessionLocal()
    try:
        for row in rows:
            company_name = norm(row["company_name"])
            email = norm(row["email"])
            phone = norm(row["phone"])
            if not company_name:
                skipped += 1
                continue

            p = find_existing_prospect(db, company_name, email, phone)
            is_new = p is None

            if is_new:
                p = Prospect(
                    company_name=company_name,
                    industry=norm(row["industry"]) or None,
                    phone=phone or None,
                    email=email or None,
                    source="Plantilla de Seguimiento",
                    status=ProspectStatus[row["status"]],
                    potential=norm(row["potential"]) or None,
                    notes=norm(row["prospect_notes"]) or None,
                )
                db.add(p)
                db.flush()
                created += 1
            else:
                # Complete missing data without overwriting newer CRM data.
                if not p.industry and norm(row["industry"]):
                    p.industry = norm(row["industry"])
                if not p.phone and phone:
                    p.phone = phone
                if not p.email and email:
                    p.email = email
                if not p.potential and norm(row["potential"]):
                    p.potential = norm(row["potential"])
                if not p.notes and norm(row["prospect_notes"]):
                    p.notes = norm(row["prospect_notes"])
                updated += 1

            contact_name = norm(row["contact_name"])
            role = norm(row["role"])
            if contact_name and not contact_exists(db, p.id, contact_name, email):
                db.add(
                    Contact(
                        prospect_id=p.id,
                        name=contact_name,
                        role=role or None,
                        phone=phone or None,
                        email=email or None,
                    )
                )
                contacts_created += 1

            marker = f"[Importado fila {row['source_row']}]"
            result = norm(row["result"])
            next_action = norm(row["next_action"])
            if result or next_action:
                if not activity_exists(db, p.id, marker):
                    happened_at = dt_from_date(norm(row["activity_date"]), 12) or datetime.utcnow()
                    next_action_at = dt_from_date(norm(row["next_action_date"]), 9)

                    result_parts = []
                    if result:
                        result_parts.append(result)
                    result_parts.append(marker)

                    db.add(
                        Activity(
                            prospect_id=p.id,
                            activity_type=norm(row["activity_type"]) or "Seguimiento",
                            happened_at=happened_at,
                            result="\n".join(result_parts),
                            next_action=next_action or None,
                            next_action_at=next_action_at,
                        )
                    )
                    activities_created += 1

                    if is_new:
                        p.last_contact_at = happened_at
                        if next_action_at:
                            p.next_action_at = next_action_at

            db.commit()

        print("Importación terminada")
        print(f"Prospectos creados: {created}")
        print(f"Prospectos existentes completados: {updated}")
        print(f"Contactos creados: {contacts_created}")
        print(f"Gestiones creadas: {activities_created}")
        print(f"Filas omitidas: {skipped}")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
