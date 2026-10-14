import unittest
from srv_erp.oem_catalog.domain.defaults import Default, resolve
from srv_erp.oem_catalog.domain.models import Attribute, CatalogError
from srv_erp.oem_catalog.domain.rules import apply_rules, validate_rules


class TestRulesDefaults(unittest.TestCase):
    def test_precedence_specificity_ties_and_locks(self):
        values = [Default('colour', 'ivory', 'product_revision', 'p'),
                  Default('colour', 'white', 'brand_group', 'root', specificity=1),
                  Default('colour', 'black', 'brand_group', 'leaf', specificity=3)]
        self.assertEqual(resolve(values)['colour']['source_record'], 'leaf')
        with self.assertRaises(CatalogError):
            resolve(values + [Default('colour', 'white', 'brand_group', 'tie', specificity=3)])
        with self.assertRaises(CatalogError):
            resolve(values + [Default('colour', 'white', 'brand', 'locked', locked=True)])
        self.assertEqual(resolve(values + [Default('colour', 'red', 'user', 'actor')])['colour']['value'], 'red')

    def test_rules_intersect_and_cannot_execute_code(self):
        attrs = (Attribute('method', 'Enum', choices=('sticker', 'plain')), Attribute('colour', 'Enum', choices=('a', 'b')))
        rule = {'when': {'field': 'method', 'op': 'eq', 'value': 'sticker'}, 'allowed': {'colour': ['a']}, 'require': ['colour']}
        apply_rules([rule], {'method': 'sticker', 'colour': 'a'}, attrs)
        with self.assertRaises(CatalogError):
            apply_rules([rule], {'method': 'sticker', 'colour': 'b'}, attrs)
        for invalid in ({'when': {'eval': '__import__("os")'}}, {'when': {'field': 'unknown', 'op': 'eq', 'value': 'a'}}, {'when': {'field': 'colour', 'op': 'gt', 'value': 'a'}}):
            with self.assertRaises(CatalogError):
                validate_rules([invalid], attrs)

    def test_depth_and_operation_limits(self):
        attrs = (Attribute('x', 'Text'),)
        node = {'field': 'x', 'op': 'exists'}
        for _ in range(6):
            node = {'not': node}
        with self.assertRaises(CatalogError):
            validate_rules([{'when': node}], attrs)
        with self.assertRaises(CatalogError):
            validate_rules([{'when': {'all': [{'field': 'x', 'op': 'exists'}] * 201}}], attrs)
