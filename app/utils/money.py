from decimal import Decimal, ROUND_HALF_UP


CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def to_money(value: Decimal | float | int | str | None) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        decimal_value = value
    else:
        decimal_value = Decimal(str(value))
    return decimal_value.quantize(CENT, rounding=ROUND_HALF_UP)
