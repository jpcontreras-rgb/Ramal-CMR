from decimal import Decimal
from app.services.pricing import split_gross

def test_split_gross():
    net, tax, gross = split_gross(Decimal("11900"))
    assert net == Decimal("10000")
    assert tax == Decimal("1900")
    assert gross == Decimal("11900")
