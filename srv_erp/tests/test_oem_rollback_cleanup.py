from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from srv_erp.patches import remove_rolled_back_oem_custom_fields as cleanup


class TestOEMRollbackCleanup(TestCase):
	def setUp(self):
		self.fields = {
			f"{doctype}-{fieldname}": (doctype, fieldname)
			for doctype, fieldnames in cleanup.OEM_CUSTOM_FIELDS.items()
			for fieldname in fieldnames
		}
		self.fields.update({
			"Sales Order-custom_oem_note": ("Sales Order", "custom_oem_note"),
			"Sales Order-customer_note": ("Sales Order", "customer_note"),
			"Other-oem_pending_lines": ("Other", "oem_pending_lines"),
		})
		self.frappe = SimpleNamespace(
			get_module_list=Mock(return_value=["Srv Erp", "Masters"]),
			get_all=Mock(side_effect=self.get_fields),
			delete_doc=Mock(side_effect=self.delete_field),
			clear_cache=Mock(),
		)

	def get_fields(self, doctype, filters, pluck):
		self.assertEqual((doctype, pluck), ("Custom Field", "name"))
		operator, fieldnames = filters["fieldname"]
		self.assertEqual(operator, "in")
		return [
			name for name, (parent, fieldname) in self.fields.items()
			if parent == filters["dt"] and fieldname in fieldnames
		]

	def delete_field(self, doctype, name, ignore_permissions):
		self.assertEqual(doctype, "Custom Field")
		self.assertTrue(ignore_permissions)
		del self.fields[name]

	def test_detaches_missing_child_table_and_preserves_unrelated_fields(self):
		with patch.object(cleanup, "frappe", self.frappe):
			cleanup.execute()

		self.assertEqual(set(self.fields), {
			"Sales Order-custom_oem_note",
			"Sales Order-customer_note",
			"Other-oem_pending_lines",
		})
		self.assertEqual(self.frappe.delete_doc.call_count, 15)
		self.assertEqual(
			[call.kwargs["doctype"] for call in self.frappe.clear_cache.call_args_list],
			["Sales Order", "Sales Order Item", "Package Barcode Batch"],
		)

	def test_rerun_does_not_delete_anything_else(self):
		with patch.object(cleanup, "frappe", self.frappe):
			cleanup.execute()
			remaining = self.fields.copy()
			self.frappe.delete_doc.reset_mock()
			cleanup.execute()

		self.assertEqual(self.fields, remaining)
		self.frappe.delete_doc.assert_not_called()

	def test_site_that_never_installed_oem_is_unchanged(self):
		self.fields.clear()
		with patch.object(cleanup, "frappe", self.frappe):
			cleanup.execute()

		self.frappe.delete_doc.assert_not_called()

	def test_intentional_oem_rollout_is_preserved(self):
		self.frappe.get_module_list.return_value.append("OEM Catalog")
		original = self.fields.copy()
		with patch.object(cleanup, "frappe", self.frappe):
			cleanup.execute()

		self.assertEqual(self.fields, original)
		self.frappe.get_all.assert_not_called()
		self.frappe.delete_doc.assert_not_called()
