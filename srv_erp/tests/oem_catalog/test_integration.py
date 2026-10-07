import json
from uuid import uuid4

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.test_runner import make_test_records
from frappe.utils import add_days, today

from srv_erp.oem_catalog import api
from srv_erp.oem_catalog.infrastructure.commands import encoded
from srv_erp.oem_catalog.infrastructure.documents import internal_command


class TestOEMIntegration(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user('Administrator')
        self.requester, self.approver = 'oem-requester@example.com', 'oem-approver@example.com'
        for email, role in ((self.requester, 'OEM Catalog User'), (self.approver, 'OEM Catalog Approver')):
            if not frappe.db.exists('User', email):
                frappe.get_doc({'doctype': 'User', 'email': email, 'first_name': 'OEM Synthetic', 'send_welcome_email': 0,
                                'roles': [{'role': role}, {'role': 'Sales User'}, {'role': 'Stock User'}]}).insert(ignore_permissions=True)
        cfg = frappe.get_doc('OEM Catalog Settings')
        cfg.mode, cfg.allow_create_items, cfg.enable_sales_order_picker, cfg.enable_barcode_picker = 'Active', 1, 1, 1
        cfg.save(ignore_permissions=True)
        self.company, self.customer = 'OEM Example Company', 'OEM Example Customer'
        if not frappe.db.exists('Customer', self.customer):
            frappe.get_doc({'doctype': 'Customer', 'customer_name': self.customer, 'customer_type': 'Company', 'customer_group': 'Commercial', 'territory': 'India'}).insert()
        if not frappe.db.exists('Brand', 'OEM Example Brand'):
            frappe.get_doc({'doctype': 'Brand', 'brand': 'OEM Example Brand'}).insert()
        self.context = {'customer': self.customer, 'company': self.company, 'brand': 'OEM Example Brand'}
        if not frappe.db.exists('OEM Customer Brand', {'customer': self.customer, 'brand': self.context['brand']}):
            with internal_command():
                frappe.get_doc({'doctype': 'OEM Customer Brand', 'customer': self.customer, 'brand': self.context['brand'],
                                'enabled': 1, 'approved_by': 'Administrator'}).insert(ignore_permissions=True)
        self.product = frappe.get_doc({'doctype': 'OEM Product', 'catalogue_code': 'OEM-TEST-' + frappe.generate_hash(length=8),
                                      'display_name': 'Synthetic enclosure', 'item_group': 'All Item Groups'}).insert()
        self.revision = frappe.get_doc({'doctype': 'OEM Product Revision', 'product': self.product.name, 'revision': 1,
            'stock_uom': 'Nos', 'identity_namespace': 'oem-v1', 'item_blueprint_json': '{}',
            'attribute_definitions': [
                {'attribute_key': 'brand', 'label': 'Brand', 'data_type': 'MasterLink', 'allowed_master_type': 'Brand', 'role': 'Identity', 'required': 1, 'input_widget': 'MasterPicker'},
                {'attribute_key': 'printed_text', 'label': 'Printed text', 'data_type': 'Text', 'role': 'Identity', 'required': 1, 'input_widget': 'Text'}],
            'packaging_choices': [{'code': 'unit', 'label': 'Unit', 'transaction_uom': 'Nos', 'conversion_factor': '1', 'enabled': 1}],
            'company_defaults': [{'company': self.company}]}).insert()
        api.publish_product_revision(self.revision.name, str(uuid4()), str(self.revision.modified))
        frappe.set_user(self.requester)
        config = api.get_configuration(self.product.name, self.context)
        self.payload = {'api_version': 1, 'product': self.product.name, 'configuration_token': config['configuration_token'],
                        'values': {'printed_text': 'EXAMPLE'}, 'package_choice': 'unit', 'context': self.context,
                        'source': {'adapter': 'standalone', 'row_intent_id': str(uuid4())}}

    def tearDown(self):
        frappe.set_user('Administrator')
        super().tearDown()

    def test_preview_submit_replay_and_approval(self):
        before = {dt: frappe.db.count(dt) for dt in ('Item', 'OEM Specification', 'OEM Configuration Request', 'OEM Command Receipt')}
        for _ in range(3): self.assertEqual(api.preview_configuration(self.payload)['outcome'], 'MISSING')
        self.assertEqual(before, {dt: frappe.db.count(dt) for dt in before})
        key = str(uuid4()); result = api.submit_configuration(self.payload, key)
        self.assertEqual(result, api.submit_configuration(self.payload, key))
        self.assertEqual(frappe.db.count('Item'), before['Item'])
        request = frappe.get_doc('OEM Configuration Request', result['request'])
        frappe.set_user(self.approver)
        approved = api.approve_request(request.name, str(request.modified), str(uuid4()))
        item = frappe.get_doc('Item', approved['item_code'])
        self.assertFalse(item.has_variants); self.assertFalse(item.variant_of)
        self.assertEqual(frappe.db.count('OEM Item Binding', {'specification': result['specification']}), 1)
        frappe.set_user(self.requester)
        self.assertEqual(api.submit_configuration(self.payload, str(uuid4()))['item_code'], item.name)

    def test_idempotency_conflict_and_self_approval(self):
        key = str(uuid4()); result = api.submit_configuration(self.payload, key)
        with self.assertRaises(frappe.ValidationError):
            api.submit_configuration(dict(self.payload, values={'printed_text': 'CHANGED'}), key)
        request = frappe.get_doc('OEM Configuration Request', result['request'])
        frappe.set_user('Administrator'); user = frappe.get_doc('User', self.requester)
        user.append('roles', {'role': 'OEM Catalog Approver'}); user.save(ignore_permissions=True)
        frappe.set_user(self.requester)
        with self.assertRaises(frappe.ValidationError): api.approve_request(request.name, str(request.modified), str(uuid4()))
        self.assertEqual(frappe.db.count('OEM Item Binding', {'specification': result['specification']}), 0)

    def test_pending_only_actual_order(self):
        self.payload['source'] = {'adapter': 'sales_order', 'doctype': 'Sales Order', 'field': 'items', 'row_intent_id': str(uuid4())}
        result = api.submit_configuration(self.payload, str(uuid4()))
        line = {'row_intent_id': result['row_intent_id'], 'product': self.product.name, 'product_revision': self.revision.name,
                'specification': result['specification'], 'configuration_request': result['request'], 'request_source': result['source'],
                'configuration_snapshot_json': encoded(result['snapshot']), 'physical_summary': 'Synthetic enclosure', 'proposed_qty': '5',
                'proposed_uom': 'Nos', 'proposed_package_code': 'unit', 'delivery_date': add_days(today(), 7), 'status': 'Pending', 'estimated_unit_rate': 10}
        saved = api.save_pending_sales_order({'customer': self.customer, 'company': self.company, 'brand_filter': self.context['brand'],
                    'transaction_date': today(), 'delivery_date': add_days(today(), 7), 'oem_order_entry_enabled': 1,
                    'oem_pending_lines': [line]}, str(uuid4()))
        doc = frappe.get_doc('Sales Order', saved['name'])
        self.assertEqual(doc.docstatus, 0); self.assertEqual(len(doc.items), 0); self.assertEqual(len(doc.oem_pending_lines), 1)
        self.assertEqual(doc.grand_total, 0); self.assertEqual(doc.oem_estimated_pending_amount, 50)
        with self.assertRaises(frappe.ValidationError): doc.submit()
        doc.reload(); doc.save()
        self.assertEqual(doc.oem_pending_lines[0].proposed_qty, '5')

    def test_forged_empty_order_and_direct_workflow_insert(self):
        with self.assertRaises(frappe.MandatoryError):
            frappe.get_doc({'doctype': 'Sales Order', 'customer': self.customer, 'company': self.company,
                            'transaction_date': today(), 'delivery_date': add_days(today(), 7), 'oem_order_entry_enabled': 1}).insert()
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc({'doctype': 'OEM Configuration Request', 'status': 'Approved'}).insert()

    def test_barcode_replay_old_route_denial_and_frozen_factors(self):
        result = api.submit_configuration(self.payload, str(uuid4()))
        request = frappe.get_doc('OEM Configuration Request', result['request'])
        frappe.set_user(self.approver)
        approved = api.approve_request(request.name, str(request.modified), str(uuid4()))
        frappe.set_user('Administrator')
        operator = 'oem-barcode@example.com'
        if not frappe.db.exists('User', operator):
            frappe.get_doc({'doctype': 'User', 'email': operator, 'first_name': 'Synthetic Barcode Operator', 'send_welcome_email': 0,
                'roles': [{'role': 'OEM Catalog User'}, {'role': 'Stock Manager'}, {'role': 'Sales User'}]}).insert(ignore_permissions=True)
        frappe.set_user(operator)
        key = str(uuid4())
        generated = api.generate_barcodes(result['specification'], self.context, 'unit', 2, key)
        self.assertEqual(generated, api.generate_barcodes(result['specification'], self.context, 'unit', 2, key))
        self.assertEqual(frappe.db.count('Package Barcode', {'generation_batch': generated['batch']}), 2)
        from srv_erp.package_barcode.api import generate_package_barcodes
        with self.assertRaises(frappe.PermissionError): generate_package_barcodes(approved['item_code'], 'Nos', 2)
        frappe.set_user('Administrator')
        item = frappe.get_doc('Item', approved['item_code'])
        item.uoms[0].conversion_factor = 2
        with self.assertRaises(frappe.ValidationError): item.save()

    def test_materializer_failure_rolls_back_receipt_and_item(self):
        result = api.submit_configuration(self.payload, str(uuid4()))
        request = frappe.get_doc('OEM Configuration Request', result['request'])
        before = {dt: frappe.db.count(dt) for dt in ('Item', 'OEM Item Binding', 'OEM Command Receipt', 'OEM Audit Event')}
        frappe.set_user(self.approver)
        from unittest.mock import patch
        from srv_erp.oem_catalog.application.approve import materialize
        def fail_after_insert(*args):
            materialize(*args)
            raise frappe.ValidationError('Synthetic controller failure after insertion')
        with patch('srv_erp.oem_catalog.application.approve.materialize', side_effect=fail_after_insert):
            with self.assertRaises(frappe.ValidationError): api.approve_request(request.name, str(request.modified), str(uuid4()))
        self.assertEqual(before, {dt: frappe.db.count(dt) for dt in before})
        self.assertEqual(frappe.db.get_value('OEM Configuration Request', request.name, 'status'), 'Pending')

    def test_missing_association_and_generic_request_read_denied(self):
        result = api.submit_configuration(self.payload, str(uuid4()))
        self.assertFalse(frappe.has_permission('OEM Configuration Request', doc=frappe.get_doc('OEM Configuration Request', result['request'])))
        self.assertEqual(api.get_request_status(result['request'])['status'], 'Pending')
        frappe.set_user('Administrator')
        if not frappe.db.exists('Brand', 'OEM Other Brand'):
            frappe.get_doc({'doctype': 'Brand', 'brand': 'OEM Other Brand'}).insert()
        frappe.set_user(self.requester)
        with self.assertRaises(frappe.PermissionError):
            api.get_configuration(self.product.name, dict(self.context, brand='OEM Other Brand'))
