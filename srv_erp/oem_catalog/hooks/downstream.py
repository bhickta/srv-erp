import json
from decimal import Decimal

import frappe
from frappe import _

from srv_erp.oem_catalog.application.configure import active_binding
from srv_erp.oem_catalog.permissions import available


def validate(doc, method=None):
    if not available() or (not doc.is_new() and doc.docstatus == 2): return
    rows = doc.get('items') or []
    if doc.doctype == 'BOM': rows = list(rows) + [frappe._dict(item_code=doc.item, uom=doc.uom, conversion_factor=1)]
    codes = {row.get('item_code') for row in rows if row.get('item_code')}
    if doc.doctype == 'Work Order': codes.add(doc.production_item)
    if not codes: return
    bindings = frappe.get_all('OEM Item Binding', filters={'stock_item': ['in', sorted(codes)]}, fields=['stock_item', 'specification'])
    mapping, uoms = {row.stock_item: row.specification for row in bindings}, {}
    for row in rows:
        if row.get('sales_order'):
            order = frappe.db.get_value('Sales Order', row.sales_order, ['docstatus', 'oem_unresolved_line_count'], as_dict=True)
            if order and (order.docstatus != 1 or order.oem_unresolved_line_count):
                frappe.throw(_('Unresolved OEM Sales Order cannot create downstream demand.'))
        if row.get('item_code') not in mapping: continue
        binding, item = active_binding(mapping[row.item_code], {}, permission=False)
        uom = row.get('uom') or item.stock_uom
        factor = next((r.conversion_factor for r in item.uoms if r.uom == uom), 1 if item.stock_uom == uom else None)
        if factor is None or (row.get('conversion_factor') and Decimal(str(row.conversion_factor)) != Decimal(str(factor))):
            frappe.throw(_('Managed Item/UOM conversion is inconsistent.'))
        uoms.setdefault(item.name, set()).add(uom)
        if doc.doctype in {'Delivery Note', 'Sales Invoice'} and doc.get('customer'):
            spec = frappe.get_doc('OEM Specification', mapping[row.item_code])
            physical = json.loads(spec.canonical_json)
            from srv_erp.oem_catalog.permissions import authorize_context
            authorize_context({'customer': doc.customer, 'company': doc.company, 'brand': physical['attributes']['brand']}, spec.product, existing=True, transaction=True)
    if doc.doctype in {'Stock Entry', 'Delivery Note', 'Stock Reconciliation'}:
        from srv_erp.package_barcode.service import get_item_qty_entry_rules, get_default_qty_entry_rule, get_effective_qty_entry_rule, QTY_RULE_FORCE_BARCODE
        item_rules = get_item_qty_entry_rules(sorted(uoms))
        for code, used in uoms.items():
            if len(used) > 1 and get_effective_qty_entry_rule(code, item_rules, get_default_qty_entry_rule()) == QTY_RULE_FORCE_BARCODE:
                frappe.throw(_('UNSUPPORTED_SCAN_UOM: managed Force Barcode Only flow requires one fixed UOM per Item.'))
