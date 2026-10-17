"""Configuration response presenters and legacy helper compatibility."""
import frappe
from frappe import _

from . import configuration
from .bindings import active_binding


def load_configuration(product_name, context):
    """Retain the historical tuple contract for external Python callers."""
    loaded = configuration.load_configuration(product_name, context)
    return (loaded.product, loaded.revision, loaded.schema, loaded.choices,
            loaded.packages, loaded.rules, loaded.defaults, loaded.provenance, loaded.token)


def validated(payload):
    """Retain the historical tuple contract for external Python callers."""
    result = configuration.validate_configuration(payload)
    return (result.payload, result.product, result.revision, result.identity,
            result.provenance, result.package)


def get_configuration(product, context):
    loaded = configuration.load_configuration(product, context)
    record, revision, schema = loaded.product, loaded.revision, loaded.schema
    choices, packages, provenance, token, rules = loaded.choices, loaded.packages, loaded.provenance, loaded.token, loaded.rules
    fields = []
    for row in revision.attribute_definitions:
        fields.append({key: row.get(key) for key in ('attribute_key', 'label', 'description', 'data_type', 'role', 'input_widget', 'required', 'decimal_precision', 'min_value', 'max_value', 'increment', 'multi_select')}
                      | {'options': choices[row.attribute_key], 'default': provenance.get(row.attribute_key)})
    return {'api_version': 1, 'product': product, 'display_name': record.display_name, 'revision': revision.name,
            'fields': fields, 'packages': [{'code': p.code, 'label': next(r.label for r in revision.packaging_choices if r.code == p.code), 'uom': p.uom, 'factor': str(p.factor), 'stock_uom': schema.stock_uom} for p in packages],
            'configuration_token': token, 'rules': rules}


def preview(payload):
    validated_config = configuration.validate_configuration(payload)
    payload, product, revision = validated_config.payload, validated_config.product, validated_config.revision
    identity, provenance, package = validated_config.identity, validated_config.provenance, validated_config.package
    specification = frappe.db.get_value('OEM Specification', {'identity_hash': identity.digest}, ['name', 'canonical_json'], as_dict=True)
    binding, item = (None, None)
    if specification:
        if specification.canonical_json != identity.canonical_json:
            frappe.throw(_('CONFIGURATION_CONFLICT: identity collision.'))
        binding, item = active_binding(specification.name, payload['context'])
    from .readiness import readiness
    return {'api_version': 1, 'outcome': 'EXISTING' if binding else 'MISSING', 'identity_hash': identity.digest,
            'summary': product.display_name, 'values': identity.values, 'provenance': provenance,
            'item_code': item.name if item else None, 'specification': specification.name if specification else None,
            'package': {'code': package.code, 'uom': package.uom, 'factor': str(package.factor), 'stock_uom': revision.stock_uom},
            'readiness': readiness(item, revision, payload['context'], package) if item else {'physical': False, 'sales': False, 'barcode': False, 'manufacturing': False}}
