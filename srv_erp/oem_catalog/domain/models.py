from dataclasses import dataclass
from decimal import Decimal
from typing import Any


class CatalogError(ValueError):
    def __init__(self, code: str, message: str, field: str | None = None):
        super().__init__(message)
        self.code, self.field = code, field


@dataclass(frozen=True)
class Attribute:
    key: str
    kind: str
    identity: bool = True
    required: bool = True
    choices: tuple[str, ...] = ()
    precision: int = 6
    minimum: str | None = None
    maximum: str | None = None
    step: str | None = None
    unit: str | None = None
    max_length: int = 500
    multiple: bool = False
    ordered: bool = False


@dataclass(frozen=True)
class Schema:
    product: str
    namespace: str
    stock_uom: str
    attributes: tuple[Attribute, ...]


@dataclass(frozen=True)
class Identity:
    canonical_json: str
    digest: str
    values: dict[str, Any]


@dataclass(frozen=True)
class Package:
    code: str
    uom: str
    factor: Decimal
    whole_number: bool = False
