import csv
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Product


def run():
    csv_path = Path(__file__).resolve().parent.parent / "data" / "products.csv"
    with SessionLocal() as db, csv_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            product = db.scalar(select(Product).where(Product.sku == row["sku"]))
            price = Decimal(row["price_gross_clp"]) if row["price_gross_clp"] else None
            if not product:
                product = Product(
                    sku=row["sku"], category=row["category"], name=row["name"],
                    format=row["format"], price_gross_clp=price, active=True
                )
                db.add(product)
            else:
                product.category = row["category"]
                product.name = row["name"]
                product.format = row["format"]
                product.price_gross_clp = price
        db.commit()


if __name__ == "__main__":
    run()
