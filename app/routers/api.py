from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Product, Prospect, Quote, QuoteItem
from app.services.google_places import search_places
from app.services.pricing import split_gross
from app.security import require_user
from app.services.tavily_enrichment import enrich_company

router = APIRouter(
    prefix="/api",
    tags=["api"],
    dependencies=[Depends(require_user)],
)


class ProspectIn(BaseModel):
    company_name: str
    industry: str | None = None
    address: str | None = None
    commune: str | None = None
    phone: str | None = None
    email: str | None = None
    instagram: str | None = None
    website: str | None = None
    google_place_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    source: str | None = None


class QuoteLineIn(BaseModel):
    product_id: int
    quantity_kg: Decimal = Field(gt=0)
    unit_price_gross_clp: Decimal | None = Field(default=None, gt=0)


class QuoteIn(BaseModel):
    prospect_id: int
    items: list[QuoteLineIn]
    notes: str | None = None


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/products")
def products(db: Session = Depends(get_db)):
    rows = db.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.category, Product.name)).all()
    return [{"id": p.id, "sku": p.sku, "category": p.category, "name": p.name, "format": p.format, "price_gross_clp": float(p.price_gross_clp) if p.price_gross_clp is not None else None} for p in rows]


@router.post("/prospects")
def create_prospect(data: ProspectIn, db: Session = Depends(get_db)):
    if data.google_place_id:
        existing = db.scalar(select(Prospect).where(Prospect.google_place_id == data.google_place_id))
        if existing:
            return {"id": existing.id, "duplicate": True}
    prospect = Prospect(**data.model_dump())
    db.add(prospect)
    db.commit(); db.refresh(prospect)
    return {"id": prospect.id, "duplicate": False}


@router.get("/web-search/places")
async def places(q: str):
    try:
        return await search_places(q)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/web-search/enrich")
async def enrich(company_name: str, website: str | None = None):
    try:
        return await enrich_company(company_name, website)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/quotes")
def create_quote(data: QuoteIn, db: Session = Depends(get_db)):
    prospect = db.get(Prospect, data.prospect_id)
    if not prospect:
        raise HTTPException(404, "Prospecto no encontrado")
    if not data.items:
        raise HTTPException(400, "La cotización necesita al menos un producto")

    quote = Quote(prospect_id=prospect.id, quote_date=date.today(), valid_until=date.today() + timedelta(days=5), notes=data.notes)
    db.add(quote); db.flush()
    quote.quote_number = f"COT-{quote.quote_date.year}-{quote.id:05d}"

    gross = Decimal("0")
    for line in data.items:
        product = db.get(Product, line.product_id)
        if not product:
            raise HTTPException(400, f"Producto {line.product_id} no existe")
        unit = line.unit_price_gross_clp if line.unit_price_gross_clp is not None else product.price_gross_clp
        if unit is None:
            raise HTTPException(400, f"{product.name} requiere precio manual")
        total = (line.quantity_kg * unit).quantize(Decimal("1"))
        gross += total
        db.add(QuoteItem(quote_id=quote.id, product_id=product.id, product_name_snapshot=product.name, quantity_kg=line.quantity_kg, unit_price_gross_clp=unit, line_total_gross_clp=total))

    quote.net_clp, quote.tax_clp, quote.total_clp = split_gross(gross)
    db.commit(); db.refresh(quote)
    return {"id": quote.id, "quote_number": quote.quote_number, "valid_until": quote.valid_until, "net_clp": float(quote.net_clp), "tax_clp": float(quote.tax_clp), "total_clp": float(quote.total_clp)}
