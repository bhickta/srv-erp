import frappe

UNIQUE = {
    'OEM Product Revision': [('product', 'revision')],
    'OEM Asset Revision': [('asset', 'revision')],
    'OEM Default Profile': [('profile_code', 'revision')],
    'OEM Customer Brand': [('customer', 'brand')],
    'OEM Request Source': [('request', 'actor', 'row_intent_id')],
    'OEM Customer Item Alias': [('customer', 'specification')],
}
INDEXES = {
    'OEM Product': [('lifecycle', 'item_group', 'catalogue_code')],
    'OEM Specification': [('product', 'release_state')],
    'OEM Item Binding': [('binding_state', 'specification')],
    'OEM Configuration Request': [('status', 'requested_on'), ('specification', 'requested_on')],
    'OEM Request Source': [('source_doctype', 'source_document')],
    'OEM Customer Brand': [('customer', 'enabled')],
    'OEM Outbox Event': [('state', 'next_attempt_on')],
    'OEM Configuration Draft': [('draft_owner', 'modified')],
    'OEM Customer Item Alias': [('customer', 'last_used_on')],
}


def execute():
    for doctype, constraints in UNIQUE.items():
        for columns in constraints:
            frappe.db.add_unique(doctype, columns, constraint_name='oem_' + '_'.join(columns))
    for doctype, indexes in INDEXES.items():
        for columns in indexes:
            frappe.db.add_index(doctype, columns, index_name='oem_' + '_'.join(columns))
