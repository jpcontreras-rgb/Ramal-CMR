from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Date, DateTime, Enum as SAEnum, ForeignKey, Index, Numeric, String, Text, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ProspectStatus(str, Enum):
    NEW = "Nuevo"
    TO_CONTACT = "Por contactar"
    CONTACTED = "Contactado"
    INTERESTED = "Interesado"
    QUOTED = "Cotización"
    FOLLOW_UP = "Seguimiento"
    CUSTOMER = "Cliente"
    LOST = "Perdido"
    DO_NOT_CONTACT = "No contactar"


class QuoteStatus(str, Enum):
    DRAFT = "Borrador"
    SENT = "Enviada"
    ACCEPTED = "Aceptada"
    REJECTED = "Rechazada"
    EXPIRED = "Vencida"


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    format: Mapped[str] = mapped_column(String(40), default="1 kg")
    price_gross_clp: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Prospect(Base):
    __tablename__ = "prospects"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(180), index=True)
    branch_name: Mapped[str | None] = mapped_column(String(160))
    industry: Mapped[str | None] = mapped_column(String(120), index=True)
    subindustry: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(240))
    commune: Mapped[str | None] = mapped_column(String(100), index=True)
    city: Mapped[str | None] = mapped_column(String(100), index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    phone: Mapped[str | None] = mapped_column(String(80), index=True)
    whatsapp: Mapped[str | None] = mapped_column(String(80))
    email: Mapped[str | None] = mapped_column(String(180), index=True)
    instagram: Mapped[str | None] = mapped_column(String(180))
    website: Mapped[str | None] = mapped_column(String(240))
    google_place_id: Mapped[str | None] = mapped_column(String(180), unique=True, nullable=True)
    source: Mapped[str | None] = mapped_column(String(120))
    source_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[ProspectStatus] = mapped_column(SAEnum(ProspectStatus, name="prospect_status"), default=ProspectStatus.NEW, index=True)
    potential: Mapped[str | None] = mapped_column(String(30))
    owner: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contacts: Mapped[list[Contact]] = relationship(back_populates="prospect", cascade="all, delete-orphan")
    activities: Mapped[list[Activity]] = relationship(back_populates="prospect", cascade="all, delete-orphan")
    quotes: Mapped[list[Quote]] = relationship(back_populates="prospect")
    orders: Mapped[list[Order]] = relationship(back_populates="prospect")

    __table_args__ = (Index("ix_prospect_geo", "commune", "industry"),)


class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    prospect_id: Mapped[int] = mapped_column(ForeignKey("prospects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(80))
    email: Mapped[str | None] = mapped_column(String(180))
    instagram: Mapped[str | None] = mapped_column(String(180))
    notes: Mapped[str | None] = mapped_column(Text)
    prospect: Mapped[Prospect] = relationship(back_populates="contacts")


class Activity(Base):
    __tablename__ = "activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    prospect_id: Mapped[int] = mapped_column(ForeignKey("prospects.id", ondelete="CASCADE"), index=True)
    activity_type: Mapped[str] = mapped_column(String(60), index=True)
    happened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    result: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(String(240))
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    prospect: Mapped[Prospect] = relationship(back_populates="activities")


class Quote(Base):
    __tablename__ = "quotes"
    id: Mapped[int] = mapped_column(primary_key=True)
    quote_number: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    prospect_id: Mapped[int] = mapped_column(ForeignKey("prospects.id"), index=True)
    quote_date: Mapped[date] = mapped_column(Date, default=date.today)
    valid_until: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[QuoteStatus] = mapped_column(SAEnum(QuoteStatus, name="quote_status"), default=QuoteStatus.DRAFT, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    terms: Mapped[str] = mapped_column(Text, default="Cotización válida por 5 días corridos desde su fecha de emisión. Precios y disponibilidad sujetos a confirmación posterior a su vencimiento.")
    net_clp: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_clp: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total_clp: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)

    prospect: Mapped[Prospect] = relationship(back_populates="quotes")
    items: Mapped[list[QuoteItem]] = relationship(back_populates="quote", cascade="all, delete-orphan")


class QuoteItem(Base):
    __tablename__ = "quote_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("quotes.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    product_name_snapshot: Mapped[str] = mapped_column(String(180))
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit_price_gross_clp: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    line_total_gross_clp: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    quote: Mapped[Quote] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    prospect_id: Mapped[int] = mapped_column(ForeignKey("prospects.id"), index=True)
    quote_id: Mapped[int | None] = mapped_column(ForeignKey("quotes.id"), nullable=True, index=True)
    order_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    status: Mapped[str] = mapped_column(String(60), default="Ingresado", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    total_gross_clp: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    prospect: Mapped[Prospect] = relationship(back_populates="orders")
    items: Mapped[list[OrderItem]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    product_name_snapshot: Mapped[str] = mapped_column(String(180))
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit_price_gross_clp: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    line_total_gross_clp: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class WebSource(Base):
    __tablename__ = "web_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    prospect_id: Mapped[int] = mapped_column(ForeignKey("prospects.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(80))
    url: Mapped[str | None] = mapped_column(String(500))
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    data_json: Mapped[str | None] = mapped_column(Text)
