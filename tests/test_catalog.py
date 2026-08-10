import csv
from pathlib import Path

def test_catalog_has_33_products():
    path=Path(__file__).resolve().parent.parent/'data'/'products.csv'
    rows=list(csv.DictReader(path.open(encoding='utf-8')))
    assert len(rows)==33
    assert any(r['name']=='Pulled pork' and r['price_gross_clp']=='8990' for r in rows)
