from decimal import Decimal

import frappe
from frappe import _

from srv_erp.oem_catalog.infrastructure.commands import Receipt, audit, digest, encoded, insert, lock
from srv_erp.oem_catalog.permissions import authorize_context, readable
from .configure import active_binding


def generate(specification, context, package_code, count, idempotency_key):
    spec = frappe.get_doc('OEM Specification', specification)
    cfg = authorize_context(context, spec.product, write=True)
    if not cfg.enable_barcode_picker:
        frappe.throw(_('OEM barcode generation is disabled.'))
    if isinstance(count, bool) or str(count) != str(int(count)) or not 1 <= int(count) <= min(500, cfg.max_barcode_batch_size):
        frappe.throw(_('INVALID_INPUT: label count must be a whole number within the batch limit.'))
    if not frappe.has_permission('Package Barcode Batch', 'create'):
        frappe.throw(_('Barcode generation permission is required.'), frappe.PermissionError)
    receipt = Receipt('generate_barcodes', idempotency_key, {'specification': specification, 'context': context, 'package': package_code, 'count': count})
    if receipt.replay:
        from srv_erp.oem_catalog.hooks.barcode import authorize_batch
        authorize_batch(receipt.replay['batch'])
        return receipt.replay
    spec = lock('OEM Specification', specification)
    binding, item = active_binding(spec.name, context)
    if not binding: frappe.throw(_('Physical Item is not released.'))
    binding = lock('OEM Item Binding', binding.name)
    item = lock('Item', item.name)
    revision = readable('OEM Product Revision', spec.product_revision)
    package = next((row for row in revision.packaging_choices if row.code == package_code and row.enabled), None)
    if not package: frappe.throw(_('Choose an approved package.'))
    factor = next((row.conversion_factor for row in item.uoms if row.uom == package.transaction_uom), 1 if item.stock_uom == package.transaction_uom else None)
    if factor is None or Decimal(str(factor)) != Decimal(package.conversion_factor):
        frappe.throw(_('UNSUPPORTED_SCAN_UOM: package factor does not match stock.'))
    from srv_erp.oem_catalog.application.assets import verified_bytes
    if package.asset_revision: verified_bytes(readable('OEM Asset Revision', package.asset_revision), context)
    from srv_erp.package_barcode.service import PackageBarcodeGenerator
    result = dict(PackageBarcodeGenerator(item_code=item.name, uom=package.transaction_uom, no_of_barcodes=int(count)).generate())
    snapshot = {'code': package.code, 'uom': package.transaction_uom, 'factor': str(factor), 'asset_revision': package.asset_revision}
    intent = insert('OEM Barcode Intent', command_key=receipt.key, specification=spec.name, binding=binding.name,
                    package_choice_snapshot_json=encoded(snapshot), conversion_factor_snapshot=str(factor),
                    customer=context.get('customer'), company=context.get('company'), requested_count=count,
                    barcode_batch=result['batch'], status='Completed')
    batch = frappe.get_doc('Package Barcode Batch', result['batch'])
    batch.oem_specification, batch.oem_barcode_intent = spec.name, intent.name
    batch.oem_package_snapshot_json, batch.oem_package_snapshot_hash = encoded(snapshot), digest(snapshot)
    batch.save(ignore_permissions=True)
    audit('generate_barcodes', intent, receipt.key)
    result.update(stock_quantity=str(Decimal(str(factor)) * int(count)), stock_uom=item.stock_uom, intent=intent.name)
    return receipt.finish(result)
