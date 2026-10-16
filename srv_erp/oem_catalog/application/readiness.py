import frappe
from frappe.utils import today


def readiness(item, revision, context, package):
    defaults = next((row for row in revision.company_defaults if row.company == context.get('company')), None)
    factor = next((row.conversion_factor for row in item.uoms if row.uom == package.uom), 1 if item.stock_uom == package.uom else None)
    from decimal import Decimal
    barcode = factor is not None and Decimal(str(factor)) == package.factor
    price = None
    if defaults and defaults.selling_price_list:
        from erpnext.stock.get_item_details import get_price_list_rate_for
        price_list = frappe.get_doc('Price List', defaults.selling_price_list)
        price_list.check_permission('read')
        args = frappe._dict({'price_list': price_list.name, 'currency': price_list.currency,
                             'customer': context.get('customer'), 'company': context.get('company'),
                             'transaction_date': context.get('effective_date') or today(),
                             'uom': package.uom, 'stock_uom': item.stock_uom, 'qty': 1,
                             'conversion_factor': float(package.factor)})
        price = get_price_list_rate_for(args, item.name)
    bom = frappe.get_list('BOM', filters={'item': item.name, 'is_active': 1, 'docstatus': 1}, pluck='name', limit_page_length=1) if frappe.has_permission('BOM', 'read') else []
    return {'physical': True, 'sales': bool(defaults and price is not None and price > 0 and barcode),
            'barcode': barcode, 'manufacturing': bool(bom), 'price': price,
            'missing': ([] if defaults else ['MISSING_COMPANY_DEFAULTS']) + ([] if price is not None and price > 0 else ['MISSING_PRICE']) + ([] if barcode else ['UNSUPPORTED_SCAN_UOM'])}
