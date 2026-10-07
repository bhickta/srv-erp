import json
from decimal import Decimal

import frappe

from srv_erp.oem_catalog.domain.models import Attribute, Package, Schema
from srv_erp.oem_catalog.permissions import readable


def schema_for(revision, context, publication=False):
    attributes, choices = [], {}
    for row in revision.attribute_definitions:
        options = []
        if row.data_type == 'Enum':
            option_set = readable('OEM Option Set', row.option_set)
            options = [{'value': option_set.code + ':' + v.value_code, 'label': v.label, 'image': v.image}
                       for v in option_set.values if not v.retired]
        elif row.data_type == 'MasterLink':
            if row.allowed_master_type not in {'Brand', 'Color', 'Branding Type'}:
                frappe.throw('Unsupported master type')
            filters = {'name': context['brand']} if row.allowed_master_type == 'Brand' and context.get('brand') else {}
            options = [{'value': v.name, 'label': v.name} for v in frappe.get_list(row.allowed_master_type, filters=filters, limit_page_length=500)]
        elif row.data_type == 'AssetRevision':
            asset_names = frappe.get_list('OEM Asset', filters={'kind': row.asset_kind}, pluck='name', limit_page_length=500)
            for asset in asset_names:
                record = readable('OEM Asset', asset)
                if record.permitted_brand and record.permitted_brand != context.get('brand') and not publication:
                    continue
                for rev in frappe.get_list('OEM Asset Revision', filters={'asset': asset, 'state': 'Approved'}, fields=['name', 'physical_reference'], limit_page_length=500):
                    options.append({'value': rev.name, 'label': rev.physical_reference or rev.name})
        choices[row.attribute_key] = options
        attributes.append(Attribute(key=row.attribute_key, kind=row.data_type, identity=row.role == 'Identity',
                                    required=bool(row.required), choices=tuple(v['value'] for v in options),
                                    precision=row.decimal_precision or 0, minimum=row.min_value or None, maximum=row.max_value or None,
                                    step=row.increment or None, unit=row.decimal_unit or None, max_length=row.max_text_length or 500,
                                    multiple=bool(row.multi_select)))
    schema = Schema(revision.product, revision.identity_namespace, revision.stock_uom, tuple(attributes))
    packages = tuple(Package(row.code, row.transaction_uom, Decimal(row.conversion_factor), bool(frappe.db.get_value('UOM', row.transaction_uom, 'must_be_whole_number')))
                     for row in revision.packaging_choices if row.enabled)
    rules = [json.loads(row.rule_json) for row in revision.constraint_rules if row.enabled]
    return schema, choices, packages, rules
