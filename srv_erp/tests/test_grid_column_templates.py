from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from frappe import _dict

from srv_erp.grid_column_templates import (
	add_grid_column_templates_to_boot,
	publish_grid_columns,
)


class TestGridColumnTemplates(TestCase):
	@patch("srv_erp.grid_column_templates.frappe")
	def test_boot_contains_templates_and_publish_permission(self, frappe):
		frappe.db.get_single_value.side_effect = ["Sales Manager", '{"Sales Order": {}}']
		frappe.get_roles.return_value = ["Sales User", "Sales Manager"]
		bootinfo = _dict()

		add_grid_column_templates_to_boot(bootinfo)

		self.assertTrue(bootinfo.srv_erp_grid_columns["can_publish"])
		self.assertEqual(bootinfo.srv_erp_grid_columns["templates"], {"Sales Order": {}})

	@patch("srv_erp.grid_column_templates.frappe")
	def test_publishes_validated_columns(self, frappe):
		frappe.db.get_single_value.side_effect = ["Sales Manager", "{}"]
		frappe.get_roles.return_value = ["Sales Manager"]
		frappe.parse_json.return_value = [
			{"fieldname": "item_code", "columns": 3},
			{"fieldname": "qty", "columns": 2},
		]
		frappe.get_meta.side_effect = [
			SimpleNamespace(get_table_fields=lambda: [SimpleNamespace(options="Sales Order Item")]),
			SimpleNamespace(
				get_field=lambda fieldname: SimpleNamespace(fieldname=fieldname, fieldtype="Data", hidden=0)
			),
		]

		result = publish_grid_columns.__wrapped__("Sales Order", "Sales Order Item", "[]")

		self.assertEqual(result["columns"][0], {"fieldname": "item_code", "columns": 3})
		frappe.db.set_single_value.assert_called_once()
		frappe.cache.delete_key.assert_called_once_with("bootinfo")

	@patch("srv_erp.grid_column_templates._", lambda message: message)
	@patch("srv_erp.grid_column_templates.frappe")
	def test_rejects_user_without_configured_role(self, frappe):
		frappe.db.get_single_value.return_value = "Sales Manager"
		frappe.get_roles.return_value = ["Sales User"]
		frappe.PermissionError = PermissionError
		frappe.throw.side_effect = PermissionError

		with self.assertRaises(PermissionError):
			publish_grid_columns.__wrapped__("Sales Order", "Sales Order Item", [])
