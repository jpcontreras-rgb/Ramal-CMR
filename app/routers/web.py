import datetime as dt
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.config import settings
from app.models import Product, Prospect, ProspectStatus, Quote, QuoteItem, Order, Contact, Activity, AuditEvent
from app.services.google_places import search_places
from app.services.pricing import split_gross
from app.services.tavily_enrichment import enrich_company
from app.security import require_user, log_event

router = APIRouter(dependencies=[Depends(require_user)])
templates = Jinja2Templates(directory="app/templates")


def money_clp(v):
    if v is None:
        return "Consultar"
    return "$" + f"{int(v):,}".replace(",", ".")

templates.env.filters["clp"] = money_clp




def day_bounds_utc():

    tz = ZoneInfo(settings.timezone)

    now_local = datetime.now(tz)

    start_local = now_local.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    end_local = (
        start_local
        + timedelta(days=1)
    )

    start_utc = (
        start_local
        .astimezone(dt.timezone.utc)
        .replace(tzinfo=None)
    )

    end_utc = (
        end_local
        .astimezone(dt.timezone.utc)
        .replace(tzinfo=None)
    )

    return (
        now_local,
        start_utc,
        end_utc,
    )


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
):

    now_local, start_utc, end_utc = day_bounds_utc()

    now_local_naive = now_local.replace(
        tzinfo=None
    )

    today_local = now_local.date()


    # =========================================
    # ACTIVIDAD DE HOY
    # =========================================

    prospects_today = (
        db.scalar(
            select(func.count())
            .select_from(Prospect)
            .where(
                Prospect.created_at >= start_utc,
                Prospect.created_at < end_utc,
            )
        )
        or 0
    )


    web_researched_today = (
        db.scalar(
            select(
                func.count(
                    func.distinct(
                        AuditEvent.prospect_id
                    )
                )
            )
            .where(
                AuditEvent.event_type
                == "WEB_RESEARCH",

                AuditEvent.prospect_id
                .is_not(None),

                AuditEvent.happened_at
                >= start_utc,

                AuditEvent.happened_at
                < end_utc,
            )
        )
        or 0
    )


    manual_types = [
        "MANUAL_EDIT",
        "MANUAL_CONTACT",
        "MANUAL_ACTIVITY",
        "MANUAL_STATUS",
    ]


    manual_worked_today = (
        db.scalar(
            select(
                func.count(
                    func.distinct(
                        AuditEvent.prospect_id
                    )
                )
            )
            .where(
                AuditEvent.event_type
                .in_(manual_types),

                AuditEvent.prospect_id
                .is_not(None),

                AuditEvent.happened_at
                >= start_utc,

                AuditEvent.happened_at
                < end_utc,
            )
        )
        or 0
    )


    quotes_today = (
        db.scalar(
            select(func.count())
            .select_from(Quote)
            .where(
                Quote.created_at >= start_utc,
                Quote.created_at < end_utc,
            )
        )
        or 0
    )


    sales_count_today = (
        db.scalar(
            select(func.count())
            .select_from(Order)
            .where(
                Order.created_at >= start_utc,
                Order.created_at < end_utc,
            )
        )
        or 0
    )


    sales_total_today = (
        db.scalar(
            select(
                func.sum(
                    Order.total_gross_clp
                )
            )
            .where(
                Order.created_at >= start_utc,
                Order.created_at < end_utc,
            )
        )
        or Decimal("0")
    )


    daily = {
        "prospects_added":
            prospects_today,

        "web_researched":
            web_researched_today,

        "manual_worked":
            manual_worked_today,

        "quotes_created":
            quotes_today,

        "sales_count":
            sales_count_today,

        "sales_total":
            sales_total_today,
    }


    # =========================================
    # CARTERA
    # =========================================

    counts = {

        "prospects":
            db.scalar(
                select(func.count())
                .select_from(Prospect)
            )
            or 0,

        "to_contact":
            db.scalar(
                select(func.count())
                .select_from(Prospect)
                .where(
                    Prospect.status.in_([
                        ProspectStatus.NEW,
                        ProspectStatus.TO_CONTACT,
                    ])
                )
            )
            or 0,

        "quotes_active":
            db.scalar(
                select(func.count())
                .select_from(Quote)
                .where(
                    Quote.valid_until
                    >= today_local
                )
            )
            or 0,

        "followups":
            db.scalar(
                select(func.count())
                .select_from(Prospect)
                .where(
                    Prospect.next_action_at
                    <= now_local_naive
                )
            )
            or 0,
    }


    recent = db.scalars(
        select(Prospect)
        .order_by(
            Prospect.created_at.desc()
        )
    ).all()


    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "daily": daily,
            "counts": counts,
            "recent": recent,
            "today_label":
                now_local.strftime(
                    "%d/%m/%Y"
                ),
        },
    )



@router.get("/products", response_class=HTMLResponse)
def product_list(
    request: Request,
    q: str = "",
    category: str = "",
    status: str = "active",
    db: Session = Depends(get_db),
):

    user = request.state.user
    is_admin = user.role == "admin"

    stmt = select(Product)

    # Ventas solo puede ver productos activos
    if not is_admin:

        stmt = stmt.where(
            Product.active.is_(True)
        )

        status = "active"

    else:

        if status == "active":
            stmt = stmt.where(
                Product.active.is_(True)
            )

        elif status == "inactive":
            stmt = stmt.where(
                Product.active.is_(False)
            )

    # Buscador
    if q.strip():

        term = f"%{q.strip()}%"

        stmt = stmt.where(
            or_(
                Product.name.ilike(term),
                Product.sku.ilike(term),
                Product.category.ilike(term),
            )
        )

    # Categoría
    if category:

        stmt = stmt.where(
            Product.category == category
        )

    stmt = stmt.order_by(
        Product.category,
        Product.name,
    )

    products = db.scalars(
        stmt
    ).all()

    categories = db.scalars(
        select(Product.category)
        .distinct()
        .order_by(Product.category)
    ).all()

    categories = [
        x for x in categories
        if x and x.strip()
    ]

    return templates.TemplateResponse(
        request,
        "products.html",
        {
            "products": products,
            "categories": categories,
            "q": q,
            "category_filter": category,
            "status_filter": status,
            "is_admin": is_admin,
            "error":
                request.query_params.get("error"),
            "created":
                request.query_params.get("created"),
            "updated":
                request.query_params.get("updated"),
        },
    )


@router.post("/products")
def product_create(
    request: Request,
    sku: str = Form(...),
    category: str = Form(...),
    name: str = Form(...),
    format: str = Form("1 kg"),
    price_gross_clp: Decimal = Form(...),
    db: Session = Depends(get_db),
):

    if request.state.user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Solo Administrador puede crear productos.",
        )

    sku = sku.strip().upper()

    existing = db.scalar(
        select(Product).where(
            func.lower(Product.sku)
            == sku.lower()
        )
    )

    if existing:
        return RedirectResponse(
            "/products?error=sku",
            status_code=303,
        )

    if price_gross_clp < 0:
        return RedirectResponse(
            "/products?error=price",
            status_code=303,
        )

    product = Product(
        sku=sku,
        category=category.strip(),
        name=name.strip(),
        format=format.strip() or "1 kg",
        price_gross_clp=price_gross_clp,
        active=True,
    )

    db.add(product)
    db.commit()
    db.refresh(product)

    return RedirectResponse(
        f"/products?created={product.id}",
        status_code=303,
    )


@router.post("/products/{product_id}/edit")
def product_edit(
    product_id: int,
    request: Request,
    sku: str = Form(...),
    category: str = Form(...),
    name: str = Form(...),
    format: str = Form("1 kg"),
    price_gross_clp: Decimal = Form(...),
    db: Session = Depends(get_db),
):

    if request.state.user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Solo Administrador puede modificar productos.",
        )

    product = db.get(
        Product,
        product_id,
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Producto no encontrado.",
        )

    sku = sku.strip().upper()

    duplicate = db.scalar(
        select(Product).where(
            func.lower(Product.sku)
            == sku.lower(),
            Product.id != product_id,
        )
    )

    if duplicate:
        return RedirectResponse(
            "/products?error=sku",
            status_code=303,
        )

    if price_gross_clp < 0:
        return RedirectResponse(
            "/products?error=price",
            status_code=303,
        )

    product.sku = sku
    product.category = category.strip()
    product.name = name.strip()
    product.format = format.strip() or "1 kg"
    product.price_gross_clp = price_gross_clp

    db.commit()

    return RedirectResponse(
        f"/products?updated={product_id}",
        status_code=303,
    )


@router.post("/products/{product_id}/toggle")
def product_toggle(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
):

    if request.state.user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Solo Administrador puede activar o desactivar productos.",
        )

    product = db.get(
        Product,
        product_id,
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Producto no encontrado.",
        )

    product.active = not product.active

    db.commit()

    return RedirectResponse(
        "/products?status=all",
        status_code=303,
    )


@router.get("/prospects", response_class=HTMLResponse)
def prospects(
    request: Request,
    q: str = "",
    status: str = "",
    industry: str = "",
    potential: str = "",
    followup: str = "",
    db: Session = Depends(get_db),
):
    stmt = select(Prospect)

    # --------------------------------------------------
    # BUSCADOR
    # --------------------------------------------------
    if q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Prospect.company_name.ilike(term),
                Prospect.email.ilike(term),
                Prospect.phone.ilike(term),
                Prospect.instagram.ilike(term),
                Prospect.commune.ilike(term),
            )
        )

    # --------------------------------------------------
    # ESTADO
    # --------------------------------------------------
    if status:
        try:
            stmt = stmt.where(
                Prospect.status == ProspectStatus(status)
            )
        except ValueError:
            pass

    # --------------------------------------------------
    # RUBRO
    # --------------------------------------------------
    if industry:
        stmt = stmt.where(
            Prospect.industry == industry
        )

    # --------------------------------------------------
    # POTENCIAL
    # --------------------------------------------------
    if potential:
        stmt = stmt.where(
            Prospect.potential == potential
        )

    # --------------------------------------------------
    # SEGUIMIENTOS
    # --------------------------------------------------
    now = dt.datetime.now()
    today_start = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    tomorrow = today_start + dt.timedelta(days=1)

    if followup == "overdue":
        stmt = stmt.where(
            Prospect.next_action_at.is_not(None),
            Prospect.next_action_at < now,
        )

    elif followup == "today":
        stmt = stmt.where(
            Prospect.next_action_at >= today_start,
            Prospect.next_action_at < tomorrow,
        )

    elif followup == "upcoming":
        stmt = stmt.where(
            Prospect.next_action_at >= tomorrow,
        )

    elif followup == "no_action":
        stmt = stmt.where(
            Prospect.next_action_at.is_(None)
        )

    # Primero los que tienen próxima gestión
    stmt = stmt.order_by(
        Prospect.next_action_at.asc().nullslast(),
        Prospect.company_name.asc(),
    )

    prospect_list = db.scalars(stmt).all()

    industries = db.scalars(
        select(Prospect.industry)
        .where(Prospect.industry.is_not(None))
        .distinct()
        .order_by(Prospect.industry)
    ).all()

    industries = [
        x for x in industries
        if x and x.strip()
    ]

    potentials = db.scalars(
        select(Prospect.potential)
        .where(Prospect.potential.is_not(None))
        .distinct()
        .order_by(Prospect.potential)
    ).all()

    potentials = [
        x for x in potentials
        if x and x.strip()
    ]

    return templates.TemplateResponse(
        request,
        "prospects.html",
        {
            "prospects": prospect_list,
            "statuses": list(ProspectStatus),
            "status_filter": status,
            "q": q,
            "industry_filter": industry,
            "potential_filter": potential,
            "followup_filter": followup,
            "industries": industries,
            "potentials": potentials,
            "now": now,
            "today_start": today_start,
            "tomorrow": tomorrow,
        },
    )


@router.post("/prospects")
def prospect_create(request: Request, company_name: str = Form(...), industry: str = Form(""), commune: str = Form(""), phone: str = Form(""), email: str = Form(""), instagram: str = Form(""), website: str = Form(""), address: str = Form(""), google_place_id: str = Form(""), latitude: str = Form(""), longitude: str = Form(""), source: str = Form("Manual"), db: Session = Depends(get_db)):
    if google_place_id:
        existing = db.scalar(select(Prospect).where(Prospect.google_place_id == google_place_id))
        if existing:
            return RedirectResponse(f"/prospects/{existing.id}", status_code=303)
    p = Prospect(company_name=company_name, industry=industry or None, commune=commune or None, phone=phone or None, email=email or None, instagram=instagram or None, website=website or None, address=address or None, google_place_id=google_place_id or None, latitude=float(latitude) if latitude else None, longitude=float(longitude) if longitude else None, source=source or None)
    db.add(p); db.commit(); db.refresh(p)
    log_event(
        db,
        request,
        "PROSPECT_CREATED",
        p.id,
    )
    db.commit()
    return RedirectResponse(f"/prospects/{p.id}", status_code=303)


@router.get("/prospects/{prospect_id}", response_class=HTMLResponse)
def prospect_detail(prospect_id: int, request: Request, db: Session = Depends(get_db)):
    p = db.get(Prospect, prospect_id)
    quotes = db.scalars(select(Quote).where(Quote.prospect_id == prospect_id).order_by(Quote.created_at.desc())).all()
    products = db.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.category, Product.name)).all()
    return templates.TemplateResponse(request, "prospect_detail.html", {"p": p, "quotes": quotes, "products": products, "statuses": list(ProspectStatus)})



@router.post("/prospects/{prospect_id}/enrich", response_class=HTMLResponse)
async def prospect_enrich(
    prospect_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    p = db.get(Prospect, prospect_id)

    quotes = db.scalars(
        select(Quote)
        .where(Quote.prospect_id == prospect_id)
        .order_by(Quote.created_at.desc())
    ).all()

    products = db.scalars(
        select(Product)
        .where(Product.active.is_(True))
        .order_by(Product.category, Product.name)
    ).all()

    enrichment = None
    enrich_error = None

    try:
        enrichment = await enrich_company(
            p.company_name,
            p.website,
        )
    except Exception as e:
        enrich_error = str(e)

    return templates.TemplateResponse(
        request,
        "prospect_detail.html",
        {
            "p": p,
            "quotes": quotes,
            "products": products,
            "statuses": list(ProspectStatus),
            "enrichment": enrichment,
            "enrich_error": enrich_error,
        },
    )


@router.post("/prospects/{prospect_id}/status")
def prospect_status(prospect_id: int, request: Request, status: str = Form(...), db: Session = Depends(get_db)):
    p = db.get(Prospect, prospect_id)
    old_status = p.status.value

    p.status = ProspectStatus(status)

    log_event(
        db,
        request,
        "MANUAL_STATUS",
        prospect_id,
        {
            "from": old_status,
            "to": p.status.value,
        },
    )

    db.commit()

    return RedirectResponse(f"/prospects/{prospect_id}", status_code=303)



@router.post("/prospects/{prospect_id}/delete")
def prospect_delete(
    prospect_id: int,
    db: Session = Depends(get_db),
):
    p = db.get(Prospect, prospect_id)

    if not p:
        return RedirectResponse("/prospects", status_code=303)

    quote_count = db.scalar(
        select(func.count())
        .select_from(Quote)
        .where(Quote.prospect_id == prospect_id)
    ) or 0

    order_count = db.scalar(
        select(func.count())
        .select_from(Order)
        .where(Order.prospect_id == prospect_id)
    ) or 0

    # No borrar historial comercial
    if quote_count > 0 or order_count > 0:
        return RedirectResponse(
            f"/prospects/{prospect_id}?delete_error=history",
            status_code=303,
        )

    db.delete(p)
    db.commit()

    return RedirectResponse("/prospects?deleted=1", status_code=303)




@router.post("/prospects/{prospect_id}/edit")
def prospect_edit(
    prospect_id: int,
    request: Request,
    company_name: str = Form(...),
    branch_name: str = Form(""),
    industry: str = Form(""),
    subindustry: str = Form(""),
    commune: str = Form(""),
    city: str = Form(""),
    address: str = Form(""),
    phone: str = Form(""),
    whatsapp: str = Form(""),
    email: str = Form(""),
    instagram: str = Form(""),
    website: str = Form(""),
    potential: str = Form(""),
    owner: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    p = db.get(Prospect, prospect_id)

    if not p:
        return RedirectResponse("/prospects", status_code=303)

    p.company_name = company_name.strip()
    p.branch_name = branch_name.strip() or None
    p.industry = industry.strip() or None
    p.subindustry = subindustry.strip() or None
    p.commune = commune.strip() or None
    p.city = city.strip() or None
    p.address = address.strip() or None
    p.phone = phone.strip() or None
    p.whatsapp = whatsapp.strip() or None
    p.email = email.strip() or None
    p.instagram = instagram.strip() or None
    p.website = website.strip() or None
    p.potential = potential.strip() or None
    p.owner = owner.strip() or None
    p.notes = notes.strip() or None

    db.commit()

    return RedirectResponse(
        f"/prospects/{prospect_id}",
        status_code=303,
    )


@router.post("/prospects/{prospect_id}/contacts")
def prospect_contact_create(
    prospect_id: int,
    request: Request,
    name: str = Form(...),
    role: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    instagram: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    p = db.get(Prospect, prospect_id)

    if not p:
        return RedirectResponse("/prospects", status_code=303)

    contact = Contact(
        prospect_id=prospect_id,
        name=name.strip(),
        role=role.strip() or None,
        phone=phone.strip() or None,
        email=email.strip() or None,
        instagram=instagram.strip() or None,
        notes=notes.strip() or None,
    )

    db.add(contact)

    log_event(
        db,
        request,
        "MANUAL_CONTACT",
        prospect_id,
    )

    db.commit()

    return RedirectResponse(
        f"/prospects/{prospect_id}#contactos",
        status_code=303,
    )


@router.post("/contacts/{contact_id}/delete")
def contact_delete(
    contact_id: int,
    db: Session = Depends(get_db),
):
    contact = db.get(Contact, contact_id)

    if not contact:
        return RedirectResponse("/prospects", status_code=303)

    prospect_id = contact.prospect_id

    db.delete(contact)
    db.commit()

    return RedirectResponse(
        f"/prospects/{prospect_id}#contactos",
        status_code=303,
    )


@router.post("/prospects/{prospect_id}/activities")
def prospect_activity_create(
    prospect_id: int,
    request: Request,
    activity_type: str = Form(...),
    result: str = Form(""),
    next_action: str = Form(""),
    next_action_at: str = Form(""),
    db: Session = Depends(get_db),
):
    p = db.get(Prospect, prospect_id)

    if not p:
        return RedirectResponse("/prospects", status_code=303)

    next_dt = None

    if next_action_at:
        try:
            next_dt = datetime.fromisoformat(next_action_at)
        except ValueError:
            next_dt = None

    now = datetime.now()

    activity = Activity(
        prospect_id=prospect_id,
        activity_type=activity_type,
        happened_at=now,
        result=result.strip() or None,
        next_action=next_action.strip() or None,
        next_action_at=next_dt,
    )

    db.add(activity)

    p.last_contact_at = now

    if next_dt:
        p.next_action_at = next_dt

        if p.status not in [
            ProspectStatus.CUSTOMER,
            ProspectStatus.LOST,
            ProspectStatus.DO_NOT_CONTACT,
        ]:
            p.status = ProspectStatus.FOLLOW_UP

    log_event(
        db,
        request,
        "MANUAL_ACTIVITY",
        prospect_id,
        {
            "activity_type":
                activity_type,
        },
    )

    db.commit()

    return RedirectResponse(
        f"/prospects/{prospect_id}#gestiones",
        status_code=303,
    )


@router.get("/web-search", response_class=HTMLResponse)
async def web_search_page(request: Request, q: str | None = None, db: Session = Depends(get_db)):
    results=[]; error=None
    if q:
        try:
            results = await search_places(q)
            ids=[x[0] for x in db.execute(select(Prospect.google_place_id).where(Prospect.google_place_id.is_not(None))).all()]
            for r in results: r["exists"] = r.get("google_place_id") in ids
        except Exception as e:
            error=str(e)
    return templates.TemplateResponse(request, "web_search.html", {"q": q or "", "results": results, "error": error})


@router.post("/prospects/{prospect_id}/quotes")
def quote_create_form(prospect_id: int, request: Request, product_id: int = Form(...), quantity_kg: Decimal = Form(...), unit_price_gross_clp: Decimal | None = Form(None), notes: str = Form(""), db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    unit = unit_price_gross_clp or product.price_gross_clp
    if unit is None:
        return RedirectResponse(f"/prospects/{prospect_id}?error=precio", status_code=303)
    q = Quote(prospect_id=prospect_id, quote_date=date.today(), valid_until=date.today()+timedelta(days=5), notes=notes or None)
    db.add(q); db.flush(); q.quote_number=f"COT-{q.quote_date.year}-{q.id:05d}"
    gross=(quantity_kg*unit).quantize(Decimal("1"))
    db.add(QuoteItem(quote_id=q.id, product_id=product.id, product_name_snapshot=product.name, quantity_kg=quantity_kg, unit_price_gross_clp=unit, line_total_gross_clp=gross))
    q.net_clp,q.tax_clp,q.total_clp=split_gross(gross)
    p=db.get(Prospect, prospect_id)
    p.status=ProspectStatus.QUOTED

    log_event(
        db,
        request,
        "QUOTE_CREATED",
        prospect_id,
        {
            "quote_id": q.id,
            "quote_number":
                q.quote_number,
        },
    )

    db.commit()
    return RedirectResponse(f"/quotes/{q.id}", status_code=303)


@router.get("/quotes/{quote_id}", response_class=HTMLResponse)
def quote_detail(quote_id: int, request: Request, db: Session = Depends(get_db)):
    quote=db.get(Quote, quote_id)
    return templates.TemplateResponse(request, "quote.html", {"q": quote})
