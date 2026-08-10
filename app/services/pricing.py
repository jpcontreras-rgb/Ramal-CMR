from decimal import Decimal, ROUND_HALF_UP

IVA = Decimal("0.19")


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def split_gross(gross: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    gross = money(gross)
    net = money(gross / (Decimal("1") + IVA))
    tax = gross - net
    return net, tax, gross
