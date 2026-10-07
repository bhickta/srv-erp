import json

import frappe
from frappe import _
from frappe.model.naming import make_autoname

from srv_erp.oem_catalog.application.publication import ITEM_FIELDS, validate_company_defaults
from srv_erp.oem_catalog.domain.packaging import validate_packages
from srv_erp.oem_catalog.infrastructure.schema_reader import schema_for


def materialize(product, revision, identity, context, settings):
    if not settings.allow_create_items:
        frappe.throw(_('New Item creation is disabled; use reviewed adoption.'))
    validate_company_defaults(revision)
    if not context.get('company') or not any(row.company == context['company'] for row in revision.company_defaults):
        frappe.throw(_('MISSING_COMPANY_DEFAULTS: configure the company before release.'))
    blueprint = json.loads(revision.item_blueprint_json or '{}')
    if set(blueprint) - ITEM_FIELDS:
        frappe.throw(_('Invalid Item blueprint.'))
    _, _, packages, _ = schema_for(revision, context)
    factors = validate_packages(packages, revision.stock_uom)
    code = make_autoname(settings.default_new_item_series)
    item = frappe.get_doc({'doctype': 'Item', **blueprint, 'item_code': code,
                           'item_name': product.display_name[:140], 'item_group': product.item_group,
                           'stock_uom': revision.stock_uom, 'is_stock_item': 1, 'has_variants': 0,
                           'variant_of': None, 'disabled': 0, 'brand': identity.values['brand'],
                           'uoms': [{'uom': uom, 'conversion_factor': str(factor)} for uom, factor in factors.items()],
                           'item_defaults': [{'company': row.company, 'default_warehouse': row.default_warehouse,
                                              'income_account': row.income_account, 'expense_account': row.expense_account,
                                              'buying_cost_center': row.cost_center, 'selling_cost_center': row.cost_center}
                                             for row in revision.company_defaults]})
    # This capability is limited to a fully authorized approval. Normal installed
    # Item validators and SRV's Item override still run.
    item.insert(ignore_permissions=True)
    return item
