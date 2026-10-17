"""Framework-free service regressions with isolated transport/persistence doubles."""
import dataclasses
from datetime import date
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from srv_erp.oem_catalog.domain.models import Attribute, Package, Schema
from srv_erp.oem_catalog.domain.uoms import factors_match, transaction_factor

ROOT = Path(__file__).resolve().parents[2] / 'oem_catalog'


def module(**values):
    result = ModuleType('test_double')
    result.__dict__.update(values)
    return result


def load_service(name, doubles):
    """Load without leaving Frappe doubles or service modules in sys.modules."""
    full_name = 'srv_erp.oem_catalog.' + name
    spec = importlib.util.spec_from_file_location(full_name, ROOT / (name.replace('.', '/') + '.py'))
    result = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {**doubles, full_name: result}):
        spec.loader.exec_module(result)
    return result


def fail(message, *args):
    raise ValueError(message)


class TestConfigurationServices(unittest.TestCase):
    def setUp(self):
        self.frappe = module(_=lambda text: text, throw=fail, local=SimpleNamespace(site='test.localhost'),
                             get_list=Mock(return_value=[]))
        self.authorize = Mock()
        self.readable = Mock()
        self.schema = Schema('PRODUCT', 'namespace', 'Nos', (Attribute('size', 'Text'),))
        self.package = Package('single', 'Nos', Decimal('1'))
        self.product = SimpleNamespace(name='PRODUCT', lifecycle='Active', current_revision='REVISION')
        self.revision = SimpleNamespace(name='REVISION', product='PRODUCT', state='Published',
                                        publication_hash='published', revision=1, attribute_definitions=[],
                                        packaging_choices=[SimpleNamespace(code='single', physical_pack_value=None)])
        self.readable.side_effect = lambda doctype, name: self.product if doctype == 'OEM Product' else self.revision
        self.digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str).encode()).hexdigest()
        doubles = {
            'frappe': self.frappe,
            'frappe.utils': module(getdate=lambda value: date.fromisoformat(value), today=lambda: '2026-10-17'),
            'srv_erp.oem_catalog.infrastructure.commands': module(digest=self.digest),
            'srv_erp.oem_catalog.infrastructure.dto': module(configuration_input=lambda value: value),
            'srv_erp.oem_catalog.infrastructure.schema_reader': module(schema_for=Mock(return_value=(self.schema, {}, (self.package,), []))),
            'srv_erp.oem_catalog.permissions': module(authorize_context=self.authorize, readable=self.readable),
        }
        self.service = load_service('application.configuration', doubles)
        self.doubles = doubles
        self.payload = {'product': 'PRODUCT', 'context': {}, 'values': {'size': 'Small'}, 'package_choice': 'single'}

    def test_loaded_named_result_preserves_token_inputs_and_legacy_tuple(self):
        loaded = self.service.load_configuration('PRODUCT', {})
        self.assertEqual(loaded.token, self.digest(['test.localhost', 'PRODUCT', 'published', [], {}, '2026-10-17', {}, 'oem-adapter-v1']))
        self.assertIs(loaded.schema, self.schema)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            loaded.token = 'changed'
        package = module(configuration=self.service)
        doubles = {**self.doubles, 'srv_erp.oem_catalog.application': package,
                   'srv_erp.oem_catalog.application.configuration': self.service,
                   'srv_erp.oem_catalog.application.bindings': module(active_binding=Mock())}
        facade = load_service('application.configure', doubles)
        self.assertEqual(facade.load_configuration('PRODUCT', {}), (self.product, self.revision, self.schema, {}, (self.package,), [], [], {}, loaded.token))
        self.payload['configuration_token'] = loaded.token
        result = self.service.validate_configuration(self.payload)
        self.assertEqual(facade.validated(self.payload), (result.payload, result.product, result.revision, result.identity, result.provenance, result.package))

    def test_stale_token_rejected_before_canonicalization(self):
        self.payload['configuration_token'] = 'stale'
        with patch.object(self.service, 'canonicalize') as canonicalize:
            with self.assertRaisesRegex(ValueError, 'STALE_CONFIGURATION'):
                self.service.validate_configuration(self.payload)
            canonicalize.assert_not_called()

    def test_validation_named_identity_and_package_checks(self):
        self.payload['configuration_token'] = self.service.load_configuration('PRODUCT', {}).token
        result = self.service.validate_configuration(self.payload)
        self.assertEqual(result.identity.values, {'size': 'Small'})
        self.assertIs(result.package, self.package)
        self.payload['package_choice'] = 'unapproved'
        with self.assertRaisesRegex(ValueError, 'approved package'):
            self.service.validate_configuration(self.payload)
        self.payload['package_choice'] = 'single'
        self.revision.packaging_choices[0].physical_pack_value = 'Box'
        with self.assertRaisesRegex(ValueError, 'packaging does not match'):
            self.service.validate_configuration(self.payload)

    def test_preview_rejects_hash_collision_before_binding_lookup(self):
        self.payload['configuration_token'] = self.service.load_configuration('PRODUCT', {}).token
        self.frappe.db = SimpleNamespace(get_value=Mock(return_value=SimpleNamespace(name='SPEC', canonical_json='different canonical bytes')))
        binding = Mock()
        doubles = {**self.doubles,
                   'srv_erp.oem_catalog.application': module(configuration=self.service),
                   'srv_erp.oem_catalog.application.configuration': self.service,
                   'srv_erp.oem_catalog.application.bindings': module(active_binding=binding)}
        facade = load_service('application.configure', doubles)
        with self.assertRaisesRegex(ValueError, 'identity collision'):
            facade.preview(self.payload)
        binding.assert_not_called()

    def test_unpublished_revision_and_profile_cap_remain_rejected(self):
        self.revision.state = 'Draft'
        with self.assertRaisesRegex(ValueError, 'revision is not published'):
            self.service.load_configuration('PRODUCT', {})
        self.revision.state = 'Published'
        self.frappe.get_list.return_value = ['profile'] * 201
        with self.assertRaisesRegex(ValueError, 'too many applicable'):
            self.service.load_configuration('PRODUCT', {})


class TestBindings(unittest.TestCase):
    def setUp(self):
        self.binding = SimpleNamespace(binding_state='Active', stock_item='ITEM', expected_stock_fingerprint='expected')
        self.item = SimpleNamespace(disabled=False, has_variants=False, check_permission=Mock(), as_dict=lambda: {'name': 'ITEM'})
        self.frappe = module(_=lambda text: text, throw=fail, db=SimpleNamespace(get_value=Mock(return_value='BINDING')),
                             get_doc=Mock(side_effect=lambda doctype, name, **kw: self.item if doctype == 'Item' else self.binding))
        self.service = load_service('application.bindings', {'frappe': self.frappe})
        self.fingerprint = patch.object(self.service, 'fingerprint', return_value='expected')
        self.fingerprint.start()
        self.addCleanup(self.fingerprint.stop)

    def test_missing_binding_and_current_read_locks(self):
        self.assertEqual(self.service.active_binding('SPEC', {}, current=True), (self.binding, self.item))
        self.item.check_permission.assert_called_once_with('read')
        self.frappe.db.get_value.assert_called_with('OEM Item Binding', {'specification': 'SPEC'}, 'name', for_update=True)
        self.frappe.get_doc.assert_any_call('OEM Item Binding', 'BINDING', for_update=True)
        self.frappe.get_doc.assert_any_call('Item', 'ITEM', for_update=True)
        self.frappe.db.get_value.return_value = None
        self.assertEqual(self.service.active_binding('SPEC', {}), (None, None))

    def test_permission_denial_and_explicit_existing_transaction_bypass(self):
        self.item.check_permission.side_effect = PermissionError('denied')
        with self.assertRaises(PermissionError):
            self.service.active_binding('SPEC', {})
        self.assertEqual(self.service.active_binding('SPEC', {}, permission=False), (self.binding, self.item))

    def test_quarantined_disabled_template_and_drift_rejected(self):
        self.binding.binding_state = 'Quarantined'
        with self.assertRaisesRegex(ValueError, 'ITEM_DRIFT'):
            self.service.active_binding('SPEC', {})
        self.binding.binding_state = 'Active'
        for field in ('disabled', 'has_variants'):
            setattr(self.item, field, True)
            with self.assertRaisesRegex(ValueError, 'DISABLED_MATCH'):
                self.service.active_binding('SPEC', {})
            setattr(self.item, field, False)
        self.binding.expected_stock_fingerprint = 'old'
        with self.assertRaisesRegex(ValueError, 'ITEM_DRIFT'):
            self.service.active_binding('SPEC', {})


class TestTransactionUOMs(unittest.TestCase):
    def test_explicit_factor_precedes_stock_fallback_and_preserves_representation(self):
        factor = Decimal('1.000')
        self.assertIs(transaction_factor('Nos', [('Nos', factor)], 'Nos'), factor)
        self.assertEqual(str(transaction_factor('Nos', [('Box', '10.00')], 'Box')), '10.00')
        self.assertEqual(transaction_factor('Nos', [], 'Nos'), 1)
        self.assertIsNone(transaction_factor('Nos', [], 'Box'))
        self.assertEqual(transaction_factor('Nos', [('Box', 10), ('Box', 20)], 'Box'), 10)

    def test_exact_comparison_distinguishes_missing_and_conflicting(self):
        self.assertTrue(factors_match('10.00', Decimal('10')))
        self.assertFalse(factors_match('10.0000000000000001', Decimal('10')))
        self.assertFalse(factors_match(None, 1))
