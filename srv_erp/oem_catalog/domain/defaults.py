from dataclasses import dataclass
from typing import Any

from .models import CatalogError

SCOPES = ('product_revision', 'company', 'brand', 'brand_group', 'brand_product',
          'customer_brand', 'customer_brand_product', 'source', 'user')


@dataclass(frozen=True)
class Default:
    key: str
    value: Any
    scope: str
    record: str
    revision: int = 1
    specificity: int = 0
    priority: int = 0
    locked: bool = False
    explanation: str = ''


def resolve(defaults):
    grouped = {}
    for value in defaults:
        if value.scope not in SCOPES:
            raise CatalogError('INVALID_INPUT', 'Unknown default scope')
        grouped.setdefault(value.key, []).append(value)
    result = {}
    for key, candidates in grouped.items():
        locked = [d for d in candidates if d.locked]
        if locked and any(d.value != locked[0].value for d in locked):
            raise CatalogError('CONFIGURATION_CONFLICT', 'Locked defaults disagree', key)
        rank = lambda d: (SCOPES.index(d.scope), d.specificity, d.priority)
        winner = max(candidates, key=rank)
        ties = [d for d in candidates if rank(d) == rank(winner)]
        if any(d.value != winner.value for d in ties):
            raise CatalogError('CONFIGURATION_CONFLICT', 'Equal-priority defaults disagree', key)
        if locked and winner.value != locked[0].value:
            raise CatalogError('CONFIGURATION_CONFLICT', 'Explicit value conflicts with a locked default', key)
        result[key] = {'value': winner.value, 'source_type': winner.scope,
                       'source_record': winner.record, 'source_revision': winner.revision,
                       'locked': bool(locked), 'explanation': winner.explanation}
    return result
