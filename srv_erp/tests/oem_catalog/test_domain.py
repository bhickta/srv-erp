import unittest
from dataclasses import replace
from decimal import Decimal

from srv_erp.oem_catalog.domain.canonicalization import canonicalize
from srv_erp.oem_catalog.domain.models import Attribute, CatalogError, Package, Schema
from srv_erp.oem_catalog.domain.packaging import quantities, validate_packages
from srv_erp.oem_catalog.domain.transitions import decide


class TestIdentity(unittest.TestCase):
    def setUp(self):
        self.schema = Schema('model-1', 'oem-v1', 'Nos', (
            Attribute('brand', 'Enum', choices=('brand-a', 'unbranded')),
            Attribute('colour', 'Enum', choices=('ivory', 'na')),
            Attribute('printed_text', 'Text'),
            Attribute('length', 'Decimal', precision=2, minimum='1', maximum='20', step='.25'),
            Attribute('discount', 'Decimal', identity=False, required=False),
        ))
        self.values = {'brand': 'brand-a', 'colour': 'ivory', 'printed_text': '  Café  ', 'length': '2.00'}

    def test_order_normalization_and_preferences_do_not_split_stock(self):
        first = canonicalize(self.schema, self.values)
        second = canonicalize(self.schema, dict(reversed(list(self.values.items()))) | {'discount': '5'})
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first.values['length'], '2')
        self.assertEqual(first.values['printed_text'], 'Café')
        third = canonicalize(self.schema, self.values | {'printed_text': 'Cafe\u0301'})
        self.assertEqual(first.digest, third.digest)

    def test_physical_changes_split_and_case_remains_meaningful(self):
        first = canonicalize(self.schema, self.values)
        for change in ({'brand': 'unbranded'}, {'colour': 'na'}, {'printed_text': 'CAFÉ'}, {'length': '2.25'}):
            self.assertNotEqual(first.digest, canonicalize(self.schema, self.values | change).digest)

    def test_unknown_missing_and_unapproved_are_rejected(self):
        for change in ({'colour': ''}, {'colour': None}, {'colour': 'unknown'}, {'customer': 'example.com'}, {'length': float('nan')}, {'length': 'NaN'}, {'length': 'Infinity'}, {'length': '2.001'}, {'length': '2.1'}, {'length': '-1'}):
            with self.subTest(change=change), self.assertRaises(CatalogError):
                canonicalize(self.schema, self.values | change)

    def test_revision_label_is_not_identity(self):
        self.assertEqual(canonicalize(self.schema, self.values).digest, canonicalize(replace(self.schema), self.values).digest)

    def test_sets_sorted_and_deduplicated(self):
        schema = Schema('p', 'v1', 'Nos', (Attribute('marks', 'Enum', choices=('a', 'b'), multiple=True),))
        self.assertEqual(canonicalize(schema, {'marks': ['b', 'a', 'a']}).digest,
                         canonicalize(schema, {'marks': ['a', 'b']}).digest)

    def test_package_conversion_and_factor_immutability(self):
        package = Package('box12', 'Box', Decimal(12), True)
        self.assertEqual(quantities(package, '5'), (Decimal(5), Decimal(60)))
        with self.assertRaises(CatalogError):
            quantities(package, '1.5')
        with self.assertRaises(CatalogError):
            validate_packages((package, Package('box24', 'Box', Decimal(24))), 'Nos')
        with self.assertRaises(CatalogError):
            validate_packages((Package('nos', 'Nos', Decimal(2)),), 'Nos')

    def test_maker_checker_and_terminal_states(self):
        with self.assertRaises(CatalogError):
            decide('Pending', 'Approved', 'a@example.com', 'a@example.com', '')
        self.assertEqual(decide('Pending', 'Approved', 'a@example.com', 'b@example.com', ''), 'Approved')
        with self.assertRaises(CatalogError):
            decide('Approved', 'Cancelled', 'a', 'b', 'reason')
