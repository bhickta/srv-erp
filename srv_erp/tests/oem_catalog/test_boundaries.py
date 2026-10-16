import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class TestOEMBoundaries(unittest.TestCase):
    def test_domain_has_no_framework_or_legacy_imports(self):
        for path in (ROOT / 'oem_catalog/domain').glob('*.py'):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                modules = [node.module or ''] if isinstance(node, ast.ImportFrom) else [m.name for m in node.names] if isinstance(node, ast.Import) else []
                self.assertFalse(any(m.startswith(('frappe', 'erpnext', 'srv_erp.masters', 'srv_erp.selling')) for m in modules), path.name)

    def test_settings_are_disabled_and_internal_children_are_not_item_grids(self):
        for path in (ROOT / 'oem_catalog/doctype').glob('*/*.json'):
            schema = json.loads(path.read_text())
            keys = [field['fieldname'] for field in schema['fields']]
            self.assertEqual(len(keys), len(set(keys)), path.name)
            if schema.get('istable'): self.assertNotIn('item_code', keys, path.name)
            if schema['name'] == 'OEM Catalog Settings':
                fields = {f['fieldname']: f for f in schema['fields']}
                self.assertEqual(fields['mode']['default'], 'Off')
                for key in ('allow_create_items', 'allow_self_approval', 'enable_sales_order_picker', 'enable_barcode_picker'):
                    self.assertEqual(fields[key]['default'], '0')

    def test_no_transaction_commit_inside_module(self):
        for path in (ROOT / 'oem_catalog').rglob('*.py'):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotEqual(node.func.attr, 'commit', path.name)
