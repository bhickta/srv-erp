from erpnext.selling.doctype.sales_order.sales_order import SalesOrder

from .pending_order_lines import clear_empty_totals, validate_pending


class OEMSalesOrder(SalesOrder):
    def validate(self):
        if self.get('oem_pending_lines'):
            validate_pending(self)
            clear_empty_totals(self)
        super().validate()
        clear_empty_totals(self)

    def _get_missing_mandatory_fields(self):
        missing = super()._get_missing_mandatory_fields()
        if self.docstatus == 0 and self._action in ('save', None) and not self.items and self.get('oem_pending_lines') and validate_pending(self):
            return [(field, message) for field, message in missing if field != 'items']
        return missing
