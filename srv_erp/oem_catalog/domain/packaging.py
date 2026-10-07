from decimal import Decimal, InvalidOperation

from .models import CatalogError, Package


def exact_positive(value):
    if isinstance(value, (float, bool)):
        raise CatalogError('INVALID_INPUT', 'Use an exact positive decimal')
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError):
        raise CatalogError('INVALID_INPUT', 'Invalid quantity or factor')
    if not number.is_finite() or number <= 0 or number > Decimal('1000000000'):
        raise CatalogError('INVALID_INPUT', 'Quantity or factor is outside bounds')
    return number


def validate_packages(packages: tuple[Package, ...], stock_uom: str):
    factors, codes = {stock_uom: Decimal(1)}, set()
    for package in packages:
        factor = exact_positive(package.factor)
        if package.code in codes or not package.code or not package.uom:
            raise CatalogError('CONFIGURATION_CONFLICT', 'Package codes must be unique and complete')
        if package.uom in factors and factors[package.uom] != factor:
            raise CatalogError('CONFIGURATION_CONFLICT', 'One UOM cannot represent two conversion factors')
        codes.add(package.code)
        factors[package.uom] = factor
    return factors


def quantities(package: Package, quantity):
    quantity = exact_positive(quantity)
    if package.whole_number and quantity != quantity.to_integral_value():
        raise CatalogError('INVALID_INPUT', 'This UOM requires whole package quantities')
    return quantity, quantity * exact_positive(package.factor)
