from decimal import ROUND_CEILING, Decimal


ARTICLE_21_ROUNDING_CODE = "ARTICLE_21_ROUND_UP_BY_MAGNITUDE"


def round_up_land_unit_price(value: Decimal) -> Decimal:
    """Apply the official Article 21 tail-digit rule used by Tables 6 and 14.

    The supplied official workbook uses ROUNDUP with a magnitude-dependent
    place: ones below 100, tens below 1,000, hundreds below 100,000, and
    thousands from 100,000 upward.  Land prices are non-negative, so
    ROUND_CEILING is equivalent to Excel ROUNDUP for these values.
    """

    if value < 0:
        raise ValueError("land unit price cannot be negative")
    if value <= Decimal("100"):
        quantum = Decimal("1")
    elif value <= Decimal("1000"):
        quantum = Decimal("1E1")
    elif value <= Decimal("100000"):
        quantum = Decimal("1E2")
    else:
        quantum = Decimal("1E3")
    return value.quantize(quantum, rounding=ROUND_CEILING)