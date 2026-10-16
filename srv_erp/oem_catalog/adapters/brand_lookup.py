import json

import frappe

from srv_erp.oem_catalog.permissions import available, authorize_context


def managed_item_brand(item_code):
    if not available(): return None
    binding = frappe.db.get_value('OEM Item Binding', {'stock_item': item_code}, ['specification', 'binding_state'], as_dict=True)
    if not binding: return None
    item = frappe.get_doc('Item', item_code); item.check_permission('read')
    if binding.binding_state != 'Active': return ''
    spec = frappe.get_doc('OEM Specification', binding.specification)
    return json.loads(spec.canonical_json)['attributes']['brand']


def extend_candidates(brand, txt, filters):
    if not available(): return []
    if filters.get('customer'):
        authorize_context({'customer': filters['customer'], 'company': filters.get('company'), 'brand': brand}, existing=True)
    rows = frappe.db.sql('''select binding.stock_item, spec.product
        from `tabOEM Item Binding` binding join `tabOEM Specification` spec on spec.name=binding.specification
        where binding.binding_state='Active'
        and JSON_UNQUOTE(JSON_EXTRACT(spec.canonical_json, '$.attributes.brand'))=%s
        order by binding.stock_item limit 500''', brand, as_dict=True)
    names = []
    for row in rows:
        if frappe.get_doc('OEM Product', row.product).has_permission('read'): names.append(row.stock_item)
    if not names: return []
    return [tuple(row) for row in frappe.get_list('Item', filters={'name': ['in', names], 'disabled': 0, 'has_variants': 0},
            or_filters=[['name', 'like', '%' + txt + '%'], ['item_name', 'like', '%' + txt + '%']],
            fields=['name', 'item_name'], as_list=True, limit_page_length=500, order_by='name asc')]
