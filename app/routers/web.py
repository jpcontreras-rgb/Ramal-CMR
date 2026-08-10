from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Product, Prospect, ProspectStatus, Quote, QuoteItem
from app.services.google_places import search_places
from app.services.pricing import split_gross

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def money_clp(v):
    if v is None:
        return "Consultar"
    return "$" + f"{int(v):,}".replace(",", ".")

templates.env.filters["clp"] = money_clp


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    today = datetime.now()
    counts = {
        "prospects": db.scalar(select(func.count()).select_from(Prospect)) or 0,
        "to_contact": db.scalar(select(func.count()).select_from(Prospect).where(Prospect.status.in_([ProspectStatus.NEW, ProspectStatus.TO_CONTACT]))) or 0,
        "quotes_active": db.scalar(select(func.count()).select_from(Quote).where(Quote.valid_until >= date.today())) or 0,
        "followups": db.scalar(select(func.count()).select_from(Prospect).where(Prospect.next_action_at <= today)) or 0,
    }
    recent = db.scalars(select(Prospect).order_by(Prospect.created_at.desc()).limit(8)).all()
    return templates.TemplateResponse(request, "dashboard.html", {"counts": counts, "recent": recent})


@router.get("/products", response_class=HTMLResponse)
def product_list(request: Request, db: Session = Depends(get_db)):
    products = db.scalars(select(Product).order_by(Product.category, Product.name)).all()
    return templates.TemplateResponse(request, "products.html", {"products": products})


@router.get("/prospects", response_class=HTMLResponse)
def prospect_list(request: Request, status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Prospect).order_by(Prospect.next_action_at.asc().nullslast(), Prospect.created_at.desc())
    if status:
        try: stmt = stmt.where(Prospect.status == ProspectStatus(status))
        except ValueError: pass
    prospects = db.scalars(stmt).all()
    return templates.TemplateResponse(request, "prospects.html", {"prospects": prospects, "statuses": list(ProspectStatus), "status_filter": status})


@router.post("/prospects")
def prospect_create(company_name: str = Form(...), industry: str = Form(""), commune: str = Form(""), phone: str = Form(""), email: str = Form(""), instagram: str = Form(""), website: str = Form(""), address: str = Form(""), google_place_id: str = Form(""), latitude: str = Form(""), longitude: str = Form(""), source: str = Form("Manual"), db: Session = Depends(get_db)):
    if google_place_id:
        existing = db.scalar(select(Prospect).where(Prospect.google_place_id == google_place_id))
        if existing:
            return RedirectResponse(f"/prospects/{existing.id}", status_code=303)
    p = Prospect(company_name=company_name, industry=industry or None, commune=commune or None, phone=phone or None, email=email or None, instagram=instagram or None, website=website or None, address=address or None, google_place_id=google_place_id or None, latitude=float(latitude) if latitude else None, longitude=float(longitude) if longitude else None, source=source or None)
    db.add(p); db.commit(); db.refresh(p)
    return RedirectResponse(f"/prospects/{p.id}", status_code=303)


@router.get("/prospects/{prospect_id}", response_class=HTMLResponse)
def prospect_detail(prospect_id: int, request: Request, db: Session = Depends(get_db)):
    p = db.get(Prospect, prospect_id)
    quotes = db.scalars(select(Quote).where(Quote.prospect_id == prospect_id).order_by(Quote.created_at.desc())).all()
    products = db.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.category, Product.name)).all()
    return templates.TemplateResponse(request, "prospect_detail.html", {"p": p, "quotes": quotes, "products": products, "statuses": list(ProspectStatus)})


@router.post("/prospects/{prospect_id}/status")
def prospect_status(prospect_id: int, status: str = Form(...), db: Session = Depends(get_db)):
    p = db.get(Prospect, prospect_id)
    p.status = ProspectStatus(status); db.commit()
    return RedirectResponse(f"/prospects/{prospect_id}", status_code=303)


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
def quote_create_form(prospect_id: int, product_id: int = Form(...), quantity_kg: Decimal = Form(...), unit_price_gross_clp: Decimal | None = Form(None), notes: str = Form(""), db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    unit = unit_price_gross_clp or product.price_gross_clp
    if unit is None:
        return RedirectResponse(f"/prospects/{prospect_id}?error=precio", status_code=303)
    q = Quote(prospect_id=prospect_id, quote_date=date.today(), valid_until=date.today()+timedelta(days=5), notes=notes or None)
    db.add(q); db.flush(); q.quote_number=f"COT-{q.quote_date.year}-{q.id:05d}"
    gross=(quantity_kg*unit).quantize(Decimal("1"))
    db.add(QuoteItem(quote_id=q.id, product_id=product.id, product_name_snapshot=product.name, quantity_kg=quantity_kg, unit_price_gross_clp=unit, line_total_gross_clp=gross))
    q.net_clp,q.tax_clp,q.total_clp=split_gross(gross)
    p=db.get(Prospect, prospect_id); p.status=ProspectStatus.QUOTED
    db.commit()
    return RedirectResponse(f"/quotes/{q.id}", status_code=303)


@router.get("/quotes/{quote_id}", response_class=HTMLResponse)
def quote_detail(quote_id: int, request: Request, db: Session = Depends(get_db)):
    quote=db.get(Quote, quote_id)
    return templates.TemplateResponse(request, "quote.html", {"q": quote})
