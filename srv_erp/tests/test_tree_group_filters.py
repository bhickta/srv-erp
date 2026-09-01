from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import call, patch

from frappe import _dict

from srv_erp.tree_group_filters import configure_tree_group_list_filters


class TestTreeGroupFilters(TestCase):
	@patch("srv_erp.tree_group_filters.frappe")
	def test_configures_indexed_customer_group_filters(self, frappe):
		def get_meta(doctype):
			if doctype in ("Sales Order", "Delivery Note"):
				return SimpleNamespace(
					name=doctype,
					get_field=lambda fieldname: _dict({
						"fieldname": fieldname,
						"fieldtype": "Link",
						"options": "Customer Group",
						"in_standard_filter": 0,
						"search_index": 0,
						"label": "Customer Group",
					}),
				)
			return SimpleNamespace(is_tree=True)

		frappe.get_meta.side_effect = get_meta

		configure_tree_group_list_filters()

		expected_setters = []
		for doctype in ("Sales Order", "Delivery Note"):
			for property_name, value, property_type in (
				("in_standard_filter", 1, "Check"),
				("search_index", 1, "Check"),
				("label", "Tour", "Data"),
			):
				expected_setters.append(
					call(
						{
							"doctype": doctype,
							"doctype_or_field": "DocField",
							"fieldname": "customer_group",
							"property": property_name,
							"value": value,
							"property_type": property_type,
						}
					)
				)

		self.assertEqual(frappe.make_property_setter.call_args_list, expected_setters)
		self.assertEqual(
			frappe.clear_cache.call_args_list,
			[call(doctype="Sales Order"), call(doctype="Delivery Note")],
		)
		self.assertEqual(
			frappe.db.updatedb.call_args_list,
			[call("Sales Order"), call("Delivery Note")],
		)

	@patch("srv_erp.tree_group_filters.frappe")
	def test_accepts_additional_tree_group_config(self, frappe):
		frappe.get_meta.side_effect = [
			SimpleNamespace(
				name="Purchase Receipt",
				get_field=lambda _fieldname: _dict({
					"fieldtype": "Link",
					"options": "Supplier Group",
					"in_standard_filter": 1,
					"search_index": 1,
					"label": "Supplier Group",
				}),
			),
			SimpleNamespace(is_tree=True),
		]

		configure_tree_group_list_filters(
			({"doctype": "Purchase Receipt", "fieldname": "supplier_group", "label": "Supplier Group"},)
		)

		frappe.make_property_setter.assert_not_called()
		frappe.clear_cache.assert_called_once_with(doctype="Purchase Receipt")
		frappe.db.updatedb.assert_called_once_with("Purchase Receipt")
