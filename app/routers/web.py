import asyncio
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
from app.models import (
    Product,
    Prospect,
    ProspectStatus,
    Quote,
    QuoteItem,
    QuoteStatus,
    Order,
    OrderItem,
    Contact,
    Activity,
    AuditEvent,
)
from app.services.google_places import search_places
from app.services.pricing import split_gross, money
from app.services.tavily_enrichment import enrich_company
from app.services.opportunity_analysis import analyze_restaurant_opportunity
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

    # Por defecto la bandeja contiene oportunidades,
    # no clientes ya convertidos.
    if not status:
        stmt = stmt.where(
            Prospect.status
            != ProspectStatus.CUSTOMER
        )

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



@router.get(
    "/prospects/{prospect_id}/quotes/new",
    response_class=HTMLResponse,
)
def quote_new(
    prospect_id: int,
    request: Request,
    db: Session = Depends(get_db),
):

    p = db.get(
        Prospect,
        prospect_id,
    )

    if not p:
        return RedirectResponse(
            "/prospects",
            status_code=303,
        )


    products = db.scalars(
        select(Product)
        .where(
            Product.active.is_(True),
            Product.price_gross_clp.is_not(None),
        )
        .order_by(
            Product.category,
            Product.name,
        )
    ).all()


    return templates.TemplateResponse(
        request,
        "quote_new.html",
        {
            "p": p,
            "products": products,
        },
    )



@router.post("/prospects/{prospect_id}/quotes")
def quote_create_form(
    prospect_id: int,
    request: Request,
    product_id: list[int] = Form(...),
    quantity_kg: list[Decimal] = Form(...),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):

    prospect = db.get(
        Prospect,
        prospect_id,
    )

    if not prospect:
        return RedirectResponse(
            "/prospects",
            status_code=303,
        )


    if len(product_id) != len(quantity_kg):

        return RedirectResponse(
            f"/prospects/{prospect_id}/quotes/new?error=items",
            status_code=303,
        )


    # Agrupar el mismo producto si fue agregado dos veces.
    quantities = {}

    for pid, qty in zip(
        product_id,
        quantity_kg,
    ):

        if qty <= 0:
            continue

        quantities[pid] = (
            quantities.get(
                pid,
                Decimal("0"),
            )
            + qty
        )


    if not quantities:

        return RedirectResponse(
            f"/prospects/{prospect_id}/quotes/new?error=empty",
            status_code=303,
        )


    prepared_items = []

    total_gross = Decimal("0")


    for pid, qty in quantities.items():

        product = db.get(
            Product,
            pid,
        )

        if (
            not product
            or not product.active
            or product.price_gross_clp is None
        ):

            return RedirectResponse(
                f"/prospects/{prospect_id}/quotes/new?error=product",
                status_code=303,
            )


        unit_price = money(
            Decimal(
                product.price_gross_clp
            )
        )


        line_total = money(
            qty * unit_price
        )


        prepared_items.append(
            {
                "product": product,
                "quantity": qty,
                "unit_price": unit_price,
                "line_total": line_total,
            }
        )


        total_gross += line_total


    total_gross = money(
        total_gross
    )


    net, tax, total = split_gross(
        total_gross
    )


    today = date.today()


    quote = Quote(
        prospect_id=prospect_id,
        quote_date=today,
        valid_until=(
            today
            + timedelta(days=5)
        ),
        notes=notes.strip() or None,
        terms=(
            "Esta cotización tiene una vigencia "
            "de 5 días corridos desde su fecha "
            "de emisión. Transcurrido dicho plazo, "
            "precios y disponibilidad deberán ser "
            "confirmados nuevamente."
        ),
        net_clp=net,
        tax_clp=tax,
        total_clp=total,
    )


    db.add(quote)

    db.flush()


    quote.quote_number = (
        f"COT-{today.year}-{quote.id:05d}"
    )


    for item in prepared_items:

        product = item["product"]

        db.add(
            QuoteItem(
                quote_id=quote.id,
                product_id=product.id,
                product_name_snapshot=product.name,
                quantity_kg=item["quantity"],
                unit_price_gross_clp=item["unit_price"],
                line_total_gross_clp=item["line_total"],
            )
        )


    prospect.status = (
        ProspectStatus.QUOTED
    )


    log_event(
        db,
        request,
        "QUOTE_CREATED",
        prospect_id,
        {
            "quote_id": quote.id,
            "quote_number":
                quote.quote_number,
            "items":
                len(prepared_items),
            "total_clp":
                int(total),
        },
    )


    db.commit()


    return RedirectResponse(
        f"/quotes/{quote.id}",
        status_code=303,
    )


@router.get("/quotes/{quote_id}", response_class=HTMLResponse)
def quote_detail(
    quote_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    quote = db.get(
        Quote,
        quote_id,
    )

    if not quote:
        raise HTTPException(
            status_code=404,
            detail="Cotización no encontrada.",
        )

    order = db.scalar(
        select(Order).where(
            Order.quote_id == quote_id
        )
    )

    display_status = quote.status.value

    if (
        quote.valid_until < date.today()
        and quote.status not in [
            QuoteStatus.ACCEPTED,
            QuoteStatus.REJECTED,
        ]
    ):
        display_status = QuoteStatus.EXPIRED.value

    return templates.TemplateResponse(
        request,
        "quote.html",
        {
            "q": quote,
            "order": order,
            "display_status": display_status,
            "error":
                request.query_params.get("error"),
            "duplicated":
                request.query_params.get("duplicated"),
        },
    )


@router.post("/quotes/{quote_id}/accept")
def quote_accept(
    quote_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    quote = db.get(Quote, quote_id)

    if not quote:
        raise HTTPException(
            status_code=404,
            detail="Cotización no encontrada.",
        )

    # Evita generar dos pedidos desde la misma cotización
    existing_order = db.scalar(
        select(Order).where(
            Order.quote_id == quote_id
        )
    )

    if existing_order:
        return RedirectResponse(
            f"/orders/{existing_order.id}",
            status_code=303,
        )

    if quote.status == QuoteStatus.REJECTED:
        return RedirectResponse(
            f"/quotes/{quote_id}?error=rejected",
            status_code=303,
        )

    if (
        quote.status == QuoteStatus.EXPIRED
        or quote.valid_until < date.today()
    ):
        return RedirectResponse(
            f"/quotes/{quote_id}?error=expired",
            status_code=303,
        )

    if not quote.items:
        return RedirectResponse(
            f"/quotes/{quote_id}?error=noitems",
            status_code=303,
        )

    prospect = db.get(
        Prospect,
        quote.prospect_id,
    )

    if not prospect:
        raise HTTPException(
            status_code=404,
            detail="Prospecto no encontrado.",
        )

    today = date.today()

    order = Order(
        prospect_id=prospect.id,
        quote_id=quote.id,
        order_date=today,
        status="Ingresado",
        notes=quote.notes,
        total_gross_clp=quote.total_clp,
    )

    db.add(order)
    db.flush()

    order.order_number = (
        f"PED-{today.year}-{order.id:05d}"
    )

    # Copiamos precios y cantidades de la cotización.
    # No usamos el precio vigente del catálogo.
    for quote_item in quote.items:

        db.add(
            OrderItem(
                order_id=order.id,
                product_id=quote_item.product_id,
                product_name_snapshot=
                    quote_item.product_name_snapshot,
                quantity_kg=
                    quote_item.quantity_kg,
                unit_price_gross_clp=
                    quote_item.unit_price_gross_clp,
                line_total_gross_clp=
                    quote_item.line_total_gross_clp,
            )
        )

    quote.status = QuoteStatus.ACCEPTED
    prospect.status = ProspectStatus.CUSTOMER
    prospect.next_action_at = None

    db.add(
        Activity(
            prospect_id=prospect.id,
            activity_type="Venta",
            happened_at=datetime.utcnow(),
            result=(
                f"Cotización {quote.quote_number} aceptada. "
                f"Pedido {order.order_number} generado por "
                f"{money_clp(order.total_gross_clp)}."
            ),
        )
    )

    log_event(
        db,
        request,
        "ORDER_CREATED",
        prospect.id,
        {
            "quote_id": quote.id,
            "quote_number": quote.quote_number,
            "order_id": order.id,
            "order_number": order.order_number,
            "total_clp": int(order.total_gross_clp),
        },
    )

    db.commit()

    return RedirectResponse(
        f"/orders/{order.id}",
        status_code=303,
    )


@router.get(
    "/orders/{order_id}",
    response_class=HTMLResponse,
)
def order_detail(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Pedido no encontrado.",
        )

    quote = None

    if order.quote_id:
        quote = db.get(
            Quote,
            order.quote_id,
        )

    net, tax, total = split_gross(
        Decimal(order.total_gross_clp)
    )

    return templates.TemplateResponse(
        request,
        "order.html",
        {
            "order": order,
            "quote": quote,
            "net": net,
            "tax": tax,
            "total": total,
        },
    )


@router.get(
    "/clients",
    response_class=HTMLResponse,
)
def clients(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
):
    stmt = select(Prospect).where(
        Prospect.status == ProspectStatus.CUSTOMER
    )

    if q.strip():
        term = f"%{q.strip()}%"

        stmt = stmt.where(
            or_(
                Prospect.company_name.ilike(term),
                Prospect.email.ilike(term),
                Prospect.phone.ilike(term),
                Prospect.commune.ilike(term),
            )
        )

    customers = db.scalars(
        stmt.order_by(
            Prospect.updated_at.desc()
        )
    ).all()

    client_rows = []

    for customer in customers:

        orders_count = (
            db.scalar(
                select(func.count())
                .select_from(Order)
                .where(
                    Order.prospect_id == customer.id
                )
            )
            or 0
        )

        purchased = (
            db.scalar(
                select(
                    func.sum(
                        Order.total_gross_clp
                    )
                )
                .where(
                    Order.prospect_id == customer.id
                )
            )
            or Decimal("0")
        )

        last_order = db.scalar(
            select(Order)
            .where(
                Order.prospect_id == customer.id
            )
            .order_by(
                Order.order_date.desc(),
                Order.id.desc(),
            )
            .limit(1)
        )

        client_rows.append(
            {
                "customer": customer,
                "orders_count": orders_count,
                "purchased": purchased,
                "last_order": last_order,
            }
        )

    return templates.TemplateResponse(
        request,
        "clients.html",
        {
            "clients": client_rows,
            "q": q,
        },
    )


@router.get(
    "/clients/new",
    response_class=HTMLResponse,
)
def client_new(
    request: Request,
):
    return templates.TemplateResponse(
        request,
        "client_new.html",
        {},
    )


@router.post("/clients/new")
def client_create(
    request: Request,
    company_name: str = Form(...),
    branch: str = Form(""),
    industry: str = Form(""),
    address: str = Form(""),
    commune: str = Form(""),
    city: str = Form(""),
    phone: str = Form(""),
    whatsapp: str = Form(""),
    email: str = Form(""),
    instagram: str = Form(""),
    website: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):

    client = Prospect(
        company_name=company_name.strip(),
        branch=branch.strip() or None,
        industry=industry.strip() or None,
        address=address.strip() or None,
        commune=commune.strip() or None,
        city=city.strip() or None,
        phone=phone.strip() or None,
        whatsapp=whatsapp.strip() or None,
        email=email.strip() or None,
        instagram=instagram.strip() or None,
        website=website.strip() or None,
        notes=notes.strip() or None,

        # Se crea inmediatamente como cliente
        status=ProspectStatus.CUSTOMER,

        source="Ingreso directo",
    )

    db.add(client)
    db.flush()

    log_event(
        db,
        request,
        "CLIENT_CREATED_DIRECTLY",
        client.id,
        {
            "company_name": client.company_name,
        },
    )

    db.commit()
    db.refresh(client)

    return RedirectResponse(
        f"/prospects/{client.id}",
        status_code=303,
    )

@router.get(
    "/quotes",
    response_class=HTMLResponse,
)
def quotes_list(
    request: Request,
    q: str = "",
    status: str = "",
    prospect_id: str = "",
    date_from: str = "",
    date_to: str = "",
    db: Session = Depends(get_db),
):

    today = date.today()

    # Los formularios GET envían "" cuando un filtro
    # está vacío. Lo convertimos manualmente a None.
    prospect_id_value = None

    if prospect_id.strip():
        try:
            prospect_id_value = int(
                prospect_id.strip()
            )
        except ValueError:
            prospect_id_value = None


    def parse_optional_date(
        value: str,
    ):
        value = (value or "").strip()

        if not value:
            return None

        try:
            return date.fromisoformat(value)
        except ValueError:
            return None


    date_from_value = parse_optional_date(
        date_from
    )

    date_to_value = parse_optional_date(
        date_to
    )

    stmt = select(Quote)


    # --------------------------------------------------
    # BUSCADOR
    # --------------------------------------------------

    if q.strip():

        term = f"%{q.strip()}%"

        stmt = (
            stmt
            .join(
                Prospect,
                Quote.prospect_id == Prospect.id,
            )
            .where(
                or_(
                    Quote.quote_number.ilike(term),
                    Prospect.company_name.ilike(term),
                    Prospect.email.ilike(term),
                )
            )
        )


    # --------------------------------------------------
    # EMPRESA / CLIENTE
    # --------------------------------------------------

    if prospect_id_value:

        stmt = stmt.where(
            Quote.prospect_id
            == prospect_id_value
        )


    # --------------------------------------------------
    # FECHAS
    # --------------------------------------------------

    if date_from_value:

        stmt = stmt.where(
            Quote.quote_date
            >= date_from_value
        )

    if date_to_value:

        stmt = stmt.where(
            Quote.quote_date
            <= date_to_value
        )


    # --------------------------------------------------
    # ESTADO
    # --------------------------------------------------

    if status == QuoteStatus.EXPIRED.value:

        stmt = stmt.where(
            Quote.valid_until < today,
            Quote.status.notin_([
                QuoteStatus.ACCEPTED,
                QuoteStatus.REJECTED,
            ]),
        )

    elif status:

        try:

            selected_status = QuoteStatus(
                status
            )

            stmt = stmt.where(
                Quote.status == selected_status
            )

            # Borrador y Enviada no incluyen
            # cotizaciones que ya están vencidas.
            if selected_status in [
                QuoteStatus.DRAFT,
                QuoteStatus.SENT,
            ]:

                stmt = stmt.where(
                    Quote.valid_until >= today
                )

        except ValueError:
            pass


    quotes = db.scalars(
        stmt.order_by(
            Quote.quote_date.desc(),
            Quote.id.desc(),
        )
    ).unique().all()


    rows = []


    for quote in quotes:

        order = db.scalar(
            select(Order).where(
                Order.quote_id == quote.id
            )
        )

        display_status = quote.status.value

        if (
            quote.valid_until < today
            and quote.status not in [
                QuoteStatus.ACCEPTED,
                QuoteStatus.REJECTED,
            ]
        ):
            display_status = (
                QuoteStatus.EXPIRED.value
            )

        rows.append(
            {
                "quote": quote,
                "order": order,
                "display_status":
                    display_status,
            }
        )


    # KPIs del resultado filtrado
    total_quotes = len(rows)

    total_amount = sum(
        (
            Decimal(row["quote"].total_clp)
            for row in rows
        ),
        Decimal("0"),
    )

    accepted_count = sum(
        1
        for row in rows
        if row["display_status"]
        == QuoteStatus.ACCEPTED.value
    )


    # Empresas que tienen cotizaciones
    companies = db.scalars(
        select(Prospect)
        .join(
            Quote,
            Quote.prospect_id
            == Prospect.id,
        )
        .distinct()
        .order_by(
            Prospect.company_name
        )
    ).all()


    return templates.TemplateResponse(
        request,
        "quotes.html",
        {
            "rows": rows,
            "q": q,
            "status_filter": status,
            "prospect_filter":
                prospect_id_value,
            "date_from":
                date_from_value,
            "date_to":
                date_to_value,
            "companies":
                companies,
            "total_quotes":
                total_quotes,
            "total_amount":
                total_amount,
            "accepted_count":
                accepted_count,
        },
    )



# =========================================================
# MARCAR COMO ENVIADA
# =========================================================

@router.post("/quotes/{quote_id}/sent")
def quote_mark_sent(
    quote_id: int,
    request: Request,
    db: Session = Depends(get_db),
):

    quote = db.get(
        Quote,
        quote_id,
    )

    if not quote:
        raise HTTPException(
            status_code=404,
            detail="Cotización no encontrada.",
        )


    order = db.scalar(
        select(Order).where(
            Order.quote_id == quote.id
        )
    )


    if (
        order
        or quote.status
        in [
            QuoteStatus.ACCEPTED,
            QuoteStatus.REJECTED,
        ]
    ):
        return RedirectResponse(
            f"/quotes/{quote_id}?error=locked",
            status_code=303,
        )


    if quote.valid_until < date.today():

        quote.status = QuoteStatus.EXPIRED
        db.commit()

        return RedirectResponse(
            f"/quotes/{quote_id}?error=expired",
            status_code=303,
        )


    quote.status = QuoteStatus.SENT
    quote.sent_at = datetime.utcnow()


    db.add(
        Activity(
            prospect_id=quote.prospect_id,
            activity_type="Cotización",
            happened_at=datetime.utcnow(),
            result=(
                f"Cotización "
                f"{quote.quote_number} "
                f"marcada como enviada."
            ),
        )
    )


    log_event(
        db,
        request,
        "QUOTE_SENT",
        quote.prospect_id,
        {
            "quote_id": quote.id,
            "quote_number":
                quote.quote_number,
        },
    )


    db.commit()


    return RedirectResponse(
        f"/quotes/{quote.id}",
        status_code=303,
    )



# =========================================================
# RECHAZAR
# =========================================================

@router.post("/quotes/{quote_id}/reject")
def quote_reject(
    quote_id: int,
    request: Request,
    db: Session = Depends(get_db),
):

    quote = db.get(
        Quote,
        quote_id,
    )

    if not quote:
        raise HTTPException(
            status_code=404,
            detail="Cotización no encontrada.",
        )


    order = db.scalar(
        select(Order).where(
            Order.quote_id == quote.id
        )
    )


    if (
        order
        or quote.status
        == QuoteStatus.ACCEPTED
    ):
        return RedirectResponse(
            f"/quotes/{quote_id}?error=locked",
            status_code=303,
        )


    quote.status = QuoteStatus.REJECTED


    db.add(
        Activity(
            prospect_id=quote.prospect_id,
            activity_type="Cotización",
            happened_at=datetime.utcnow(),
            result=(
                f"Cotización "
                f"{quote.quote_number} "
                f"marcada como rechazada."
            ),
        )
    )


    log_event(
        db,
        request,
        "QUOTE_REJECTED",
        quote.prospect_id,
        {
            "quote_id": quote.id,
            "quote_number":
                quote.quote_number,
        },
    )


    db.commit()


    return RedirectResponse(
        f"/quotes/{quote.id}",
        status_code=303,
    )



# =========================================================
# DUPLICAR
# =========================================================

@router.post("/quotes/{quote_id}/duplicate")
def quote_duplicate(
    quote_id: int,
    request: Request,
    db: Session = Depends(get_db),
):

    original = db.get(
        Quote,
        quote_id,
    )

    if not original:
        raise HTTPException(
            status_code=404,
            detail="Cotización no encontrada.",
        )


    today = date.today()


    duplicated = Quote(
        prospect_id=
            original.prospect_id,

        quote_date=today,

        valid_until=(
            today
            + timedelta(days=5)
        ),

        status=QuoteStatus.DRAFT,

        notes=original.notes,

        terms=original.terms,

        net_clp=
            original.net_clp,

        tax_clp=
            original.tax_clp,

        total_clp=
            original.total_clp,
    )


    db.add(duplicated)

    db.flush()


    duplicated.quote_number = (
        f"COT-{today.year}-"
        f"{duplicated.id:05d}"
    )


    for item in original.items:

        db.add(
            QuoteItem(
                quote_id=
                    duplicated.id,

                product_id=
                    item.product_id,

                product_name_snapshot=
                    item.product_name_snapshot,

                quantity_kg=
                    item.quantity_kg,

                unit_price_gross_clp=
                    item.unit_price_gross_clp,

                line_total_gross_clp=
                    item.line_total_gross_clp,
            )
        )


    prospect = db.get(
        Prospect,
        original.prospect_id,
    )


    if (
        prospect
        and prospect.status
        != ProspectStatus.CUSTOMER
    ):
        prospect.status = (
            ProspectStatus.QUOTED
        )


    log_event(
        db,
        request,
        "QUOTE_DUPLICATED",
        original.prospect_id,
        {
            "original_quote_id":
                original.id,

            "new_quote_id":
                duplicated.id,

            "new_quote_number":
                duplicated.quote_number,
        },
    )


    db.commit()


    return RedirectResponse(
        f"/quotes/{duplicated.id}?duplicated=1",
        status_code=303,
    )



@router.get(
    "/opportunities",
    response_class=HTMLResponse,
)
def opportunities_page(
    request: Request,
    db: Session = Depends(get_db),
):

    products = db.scalars(
        select(Product)
        .where(
            Product.active.is_(True)
        )
        .order_by(
            Product.category,
            Product.name,
        )
    ).all()

    return templates.TemplateResponse(
        request,
        "opportunities.html",
        {
            "products":
                products,

            "results":
                None,

            "zone":
                "",

            "business_type":
                "restaurantes",

            "product_filter":
                "",

            "max_results":
                6,

            "search_error":
                None,
        },
    )



@router.post(
    "/opportunities",
    response_class=HTMLResponse,
)
async def opportunities_search(
    request: Request,
    zone: str = Form(...),
    business_type: str = Form(
        "restaurantes"
    ),
    product_id: str = Form(""),
    max_results: int = Form(6),
    db: Session = Depends(get_db),
):

    products = db.scalars(
        select(Product)
        .where(
            Product.active.is_(True)
        )
        .order_by(
            Product.category,
            Product.name,
        )
    ).all()


    max_results = max(
        1,
        min(
            max_results,
            8,
        ),
    )


    product_id_value = None

    if product_id.strip().isdigit():
        product_id_value = int(
            product_id.strip()
        )


    selected_products = products

    if product_id_value:

        selected_products = [
            product
            for product in products
            if product.id
            == product_id_value
        ]


    product_payload = [
        {
            "id":
                product.id,

            "name":
                product.name,

            "category":
                product.category,
        }

        for product
        in selected_products
    ]


    results = []

    search_error = None


    try:

        places = await search_places(
            (
                f"{business_type} "
                f"en {zone}, Chile"
            ),
            max_results=max_results,
        )


        place_ids = [
            place["google_place_id"]
            for place in places
            if place.get(
                "google_place_id"
            )
        ]


        existing_by_place = {}

        if place_ids:

            existing = db.scalars(
                select(Prospect)
                .where(
                    Prospect.google_place_id
                    .in_(place_ids)
                )
            ).all()

            existing_by_place = {
                prospect.google_place_id:
                    prospect.id

                for prospect
                in existing
            }


        semaphore = asyncio.Semaphore(3)


        async def analyze_place(
            place: dict,
        ) -> dict:

            async with semaphore:

                try:

                    analysis = (
                        await
                        analyze_restaurant_opportunity(
                            place.get(
                                "company_name"
                            )
                            or "",

                            place.get(
                                "website"
                            ),

                            product_payload,
                        )
                    )

                except Exception as exc:

                    analysis = {
                        "score":
                            0,

                        "level":
                            "Sin análisis",

                        "matches":
                            [],

                        "sources":
                            [],

                        "suggested_products_text":
                            "",

                        "evidence_text":
                            "",

                        "evidence_url":
                            "",

                        "error":
                            str(exc),
                    }


                score = analysis.get(
                    "score",
                    0,
                )

                if place.get("phone"):
                    score = min(
                        100,
                        score + 3,
                    )


                if score >= 80:
                    analysis["level"] = (
                        "Alta"
                    )

                elif score >= 60:
                    analysis["level"] = (
                        "Media"
                    )

                elif score > 0:
                    analysis["level"] = (
                        "Baja"
                    )


                analysis["score"] = score


                return {
                    **place,
                    **analysis,

                    "existing_id":
                        existing_by_place.get(
                            place.get(
                                "google_place_id"
                            )
                        ),
                }


        results = await asyncio.gather(
            *[
                analyze_place(place)
                for place in places
            ]
        )


        results.sort(
            key=lambda item:
                item.get(
                    "score",
                    0,
                ),
            reverse=True,
        )


        log_event(
            db,
            request,
            "OPPORTUNITY_SEARCH",
            None,
            {
                "zone":
                    zone,

                "business_type":
                    business_type,

                "product_id":
                    product_id_value,

                "results":
                    len(results),
            },
        )

        db.commit()


    except Exception as exc:

        search_error = str(exc)


    return templates.TemplateResponse(
        request,
        "opportunities.html",
        {
            "products":
                products,

            "results":
                results,

            "zone":
                zone,

            "business_type":
                business_type,

            "product_filter":
                product_id,

            "max_results":
                max_results,

            "search_error":
                search_error,
        },
    )



@router.post(
    "/opportunities/add"
)
def opportunity_add(
    request: Request,

    company_name: str = Form(...),

    industry: str = Form(""),

    zone: str = Form(""),

    address: str = Form(""),

    phone: str = Form(""),

    website: str = Form(""),

    google_place_id: str = Form(""),

    latitude: str = Form(""),

    longitude: str = Form(""),

    google_maps_url: str = Form(""),

    score: int = Form(0),

    level: str = Form(""),

    suggested_products: str = Form(""),

    evidence_text: str = Form(""),

    evidence_url: str = Form(""),

    db: Session = Depends(get_db),
):


    existing = None


    if google_place_id:

        existing = db.scalar(
            select(Prospect).where(
                Prospect.google_place_id
                == google_place_id
            )
        )


    if not existing:

        existing = db.scalar(
            select(Prospect).where(
                func.lower(
                    Prospect.company_name
                )
                == company_name
                .strip()
                .lower(),

                Prospect.address
                == (
                    address.strip()
                    or None
                ),
            )
        )


    if existing:

        return RedirectResponse(
            f"/prospects/{existing.id}",
            status_code=303,
        )


    notes_parts = [
        (
            "Oportunidad detectada "
            "automáticamente por Ramal CRM."
        ),
        (
            f"Score comercial: "
            f"{score}/100"
            + (
                f" ({level})."
                if level
                else "."
            )
        ),
    ]


    if suggested_products:

        notes_parts.append(
            "Productos Ramal sugeridos: "
            + suggested_products
            + "."
        )


    if evidence_text:

        notes_parts.append(
            "Evidencia encontrada: "
            + evidence_text
        )


    prospect = Prospect(
        company_name=
            company_name.strip()[:180],

        industry=
            industry.strip()[:120]
            or None,

        commune=
            zone.strip()[:100]
            or None,

        address=
            address.strip()[:240]
            or None,

        phone=
            phone.strip()[:80]
            or None,

        website=
            website.strip()[:240]
            or None,

        google_place_id=
            google_place_id.strip()[:180]
            or None,

        latitude=
            float(latitude)
            if latitude
            else None,

        longitude=
            float(longitude)
            if longitude
            else None,

        source=
            "Oportunidades Ramal",

        source_url=(
            evidence_url.strip()
            or google_maps_url.strip()
            or ""
        )[:500] or None,

        status=
            ProspectStatus.NEW,

        potential=
            level
            or None,

        owner=
            request.state.user.full_name,

        notes=
            "\n\n".join(
                notes_parts
            ),
    )


    db.add(prospect)
    db.flush()


    log_event(
        db,
        request,
        "OPPORTUNITY_ADDED",
        prospect.id,
        {
            "score":
                score,

            "level":
                level,

            "suggested_products":
                suggested_products,
        },
    )


    db.commit()
    db.refresh(prospect)


    return RedirectResponse(
        f"/prospects/{prospect.id}",
        status_code=303,
    )
