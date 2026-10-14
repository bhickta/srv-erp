from typing import Protocol
from srv_erp.oem_catalog.domain.models import Identity


class StockItems(Protocol):
    """Approved Item writes belong behind an adapter, never in the domain."""
    def materialize(self, product, revision, identity: Identity, context, settings): ...
    def fingerprint(self, item) -> str: ...
