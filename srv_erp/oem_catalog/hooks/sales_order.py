import json

import frappe
from frappe import _

from srv_erp.oem_catalog.application.configure import active_binding
from srv_erp.oem_catalog.domain.packaging import exact_positive
from srv_erp.oem_catalog.infrastructure.commands import digest
from srv_erp.oem_catalog.permissions import authorize_context, available, settings


def validate(doc, method=None):
    if not available(): return
    if doc.get('oem_pending_lines'):
        from srv_erp.oem_catalog.adapters.pending_order_lines import validate_pending
        validate_pending(doc)
    codes = {row.item_code for row in doc.items if row.item_code}
    if not codes: return
    bindings = frappe.get_all('OEM Item Binding', filters={'stock_item': ['in', sorted(codes)]}, fields=['stock_item', 'specification'])
    mapping = {row.stock_item: row.specification for row in bindings}
    seen = set()
    context = {'customer': doc.customer, 'company': doc.company, 'brand': doc.get('brand_filter')}
    for row in doc.items:
        if row.item_code not in mapping:
            if row.get('oem_specification'): frappe.throw(_('OEM row has no matching binding.'))
            continue
        spec = frappe.get_doc('OEM Specification', mapping[row.item_code])
        # Existing concrete Items remain transactable with mode Off; authorization
        # and physical/UOM integrity still apply to newly managed usage.
        authorize_context(context, spec.product, existing=True)
        physical = json.loads(spec.canonical_json)
        if physical['attributes'].get('brand') != context.get('brand'):
            frappe.throw(_('Managed physical Brand must agree with order context.'))
        binding, item = active_binding(spec.name, context)
        factor = next((u.conversion_factor for u in item.uoms if u.uom == row.uom), 1 if row.uom == item.stock_uom else None)
        from decimal import Decimal
        if factor is None or Decimal(str(factor)) != Decimal(str(row.conversion_factor)):
            frappe.throw(_('Managed UOM conversion does not match released stock.'))
        if row.get('oem_specification') and row.oem_specification != spec.name:
            frappe.throw(_('Managed specification cannot be replaced.'))
        for field, key in json.loads(settings().physical_field_mapping_json or '{}').items():
            if field not in {'branding_type', 'color', 'marketed_by'}: frappe.throw(_('Invalid physical field mapping.'))
            if row.get(field) and row.get(field) != physical['attributes'].get(key):
                frappe.throw(_('Managed physical customization requires a new configuration.'))
        row.oem_specification, row.oem_snapshot_json, row.oem_snapshot_hash = spec.name, spec.canonical_json, digest(physical)
        if row.get('oem_row_intent_id'):
            if row.oem_row_intent_id in seen: frappe.throw(_('Duplicate applied row intent.'))
            seen.add(row.oem_row_intent_id)
    if doc.docstatus == 1 and doc.get('oem_unresolved_line_count'):
        frappe.throw(_('Unresolved OEM intent blocks submission.'))
