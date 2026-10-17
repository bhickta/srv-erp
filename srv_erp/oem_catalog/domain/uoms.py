"""Transaction UOM compatibility without changing stored factor representation."""
from decimal import Decimal
from typing import Iterable, Any


def transaction_factor(stock_uom: str, conversions: Iterable[tuple[str, Any]], uom: str):
    """Use the first explicit factor, then the implicit stock-UOM factor of one.

    Return the original numeric value so barcode snapshots retain their existing
    representation. A missing conversion is distinct from a conflicting factor.
    """
    return next((factor for code, factor in conversions if code == uom),
                1 if stock_uom == uom else None)


def factors_match(actual, expected) -> bool:
    return actual is not None and Decimal(str(actual)) == Decimal(str(expected))
