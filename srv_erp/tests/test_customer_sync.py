from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from frappe import _dict

from srv_erp.customer.customer import (
	sync_address_linked_docs,
	sync_customer_linked_docs,
	sync_customer_linked_docs_after_rename,
)


def make_field(fieldname, fieldtype, fetch_from=None, default=None, options=None):
	return _dict(
		fieldname=fieldname,
		fieldtype=fieldtype,
		fetch_from=fetch_from,
		default=default,
		options=options,
	)


class TestCustomerSync(TestCase):
	def make_meta(self, doctype):
		fields = {
			"Sales Order": {
				"customer_name": make_field(
					"customer_name", "Data", "customer.customer_name"
				),
				"tax_id": make_field("tax_id", "Data", "customer.tax_id"),
				"customer_address": make_field(
					"customer_address", "Link", options="Address"
				),
				"address_display": make_field("address_display", "Small Text"),
				"shipping_address_name": make_field(
					"shipping_address_name", "Link", options="Address"
				),
				"shipping_address": make_field("shipping_address", "Small Text"),
			},
			"Delivery Note": {
				"customer_name": make_field(
					"customer_name", "Data", "customer.customer_name"
				),
				"tax_id": make_field("tax_id", "Data", "customer.tax_id"),
				"title": make_field("title", "Data", default="{customer_name}"),
				"customer_address": make_field(
					"customer_address", "Link", options="Address"
				),
				"address_display": make_field("address_display", "Small Text"),
				"shipping_address_name": make_field(
					"shipping_address_name", "Link", options="Address"
				),
				"shipping_address": make_field("shipping_address", "Small Text"),
			},
		}[doctype]
		return SimpleNamespace(
			is_virtual=False,
			fields_by_fieldname=fields,
			has_field=lambda fieldname: fieldname in fields,
			get_field=lambda fieldname: fields.get(fieldname),
			get_fields_to_fetch=lambda link_fieldname: [
				field
				for field in fields.values()
				if field.fetch_from and field.fetch_from.startswith(f"{link_fieldname}.")
			],
			get_link_fields=lambda: [
				field for field in fields.values() if field.options == "Address"
			],
			get_title_field=lambda: "title" if doctype == "Delivery Note" else "customer_name",
		)

	@patch("srv_erp.customer.customer.get_party_shipping_address", return_value="ADDR-SHIP")
	@patch("srv_erp.customer.customer.render_address", side_effect=lambda address, **kwargs: address["name"])
	@patch("srv_erp.customer.customer.get_link_fields")
	@patch("srv_erp.customer.customer.frappe")
	def test_syncs_fetched_fields_title_and_addresses(
		self, frappe, get_link_fields, _render_address, _get_shipping_address
	):
		customer = SimpleNamespace(
			name="CUST-001",
			as_dict=lambda: {
				"name": "CUST-001",
				"customer_name": "Updated Customer",
				"tax_id": "TAX-NEW",
			},
		)
		get_link_fields.return_value = [
			{"parent": "Sales Order", "fieldname": "customer", "issingle": 0},
			{"parent": "Delivery Note", "fieldname": "customer", "issingle": 0},
			{"parent": "Customer Settings", "fieldname": "customer", "issingle": 1},
		]
		frappe.get_meta.side_effect = self.make_meta
		frappe.db.get_value.return_value = "ADDR-BILL"
		frappe.get_doc.side_effect = lambda doctype, name: SimpleNamespace(
			as_dict=lambda: {"name": name}
		)
		frappe.get_all.side_effect = [
			[_dict(name="SO-001", customer="CUST-001")],
			[_dict(name="DN-001", customer="CUST-001", customer_name="Old Customer")],
		]

		sync_customer_linked_docs(customer, "on_update")

		updates = {
			call.args[1]: call.args[2]
			for call in frappe.db.set_value.call_args_list
		}
		self.assertEqual(updates["SO-001"]["customer_name"], "Updated Customer")
		self.assertEqual(updates["SO-001"]["tax_id"], "TAX-NEW")
		self.assertEqual(updates["SO-001"]["customer_address"], "ADDR-BILL")
		self.assertEqual(updates["SO-001"]["address_display"], "ADDR-BILL")
		self.assertEqual(updates["SO-001"]["shipping_address_name"], "ADDR-SHIP")
		self.assertEqual(updates["SO-001"]["shipping_address"], "ADDR-SHIP")
		self.assertEqual(updates["DN-001"]["title"], "Updated Customer")

	@patch("srv_erp.customer.customer.get_party_shipping_address", return_value=None)
	@patch("srv_erp.customer.customer.render_address")
	@patch("srv_erp.customer.customer.get_link_fields")
	@patch("srv_erp.customer.customer.frappe")
	def test_uses_renamed_customer_id_for_linked_docs(
		self, frappe, get_link_fields, _render_address, _get_shipping_address
	):
		customer = SimpleNamespace(
			name="RENAMED-CUSTOMER",
			as_dict=lambda: {
				"name": "RENAMED-CUSTOMER",
				"customer_name": "Updated Customer",
				"tax_id": "TAX-NEW",
			},
		)
		get_link_fields.return_value = [
			{"parent": "Sales Order", "fieldname": "customer", "issingle": 0},
		]
		frappe.get_meta.side_effect = self.make_meta
		frappe.db.get_value.return_value = None
		frappe.get_all.return_value = [_dict(name="SO-001", customer="RENAMED-CUSTOMER")]

		sync_customer_linked_docs_after_rename(
			customer, "after_rename", "OLD-CUSTOMER", "RENAMED-CUSTOMER"
		)

		self.assertEqual(
			frappe.get_all.call_args.kwargs["filters"],
			{"customer": "RENAMED-CUSTOMER"},
		)
		self.assertEqual(
			frappe.db.set_value.call_args.args[2]["customer_name"],
			"Updated Customer",
		)

	@patch("srv_erp.customer.customer._sync_address_display_for_customer")
	@patch("srv_erp.customer.customer._sync_customer_linked_docs")
	@patch("srv_erp.customer.customer._get_customer_address_values")
	@patch("srv_erp.customer.customer.render_address", return_value="Updated address display")
	@patch("srv_erp.customer.customer.frappe")
	def test_address_change_refreshes_default_and_selected_address_docs(
		self,
		frappe,
		_render_address,
		get_customer_address_values,
		sync_customer,
		sync_address_display,
	):
		address = SimpleNamespace(
			name="ADDR-1",
			get=lambda fieldname, default=None: (
				[_dict(link_doctype="Customer", link_name="CUST-001")]
				if fieldname == "links"
				else default
			),
			get_doc_before_save=lambda: None,
			as_dict=lambda: {"name": "ADDR-1"},
		)
		frappe.get_doc.return_value = SimpleNamespace(name="CUST-001")
		get_customer_address_values.return_value = {
			"billing_address": "ADDR-1",
			"shipping_address": "ADDR-SHIP",
		}

		sync_address_linked_docs(address, "on_update")

		sync_customer.assert_called_once_with(frappe.get_doc.return_value)
		sync_address_display.assert_not_called()

		get_customer_address_values.return_value = {
			"billing_address": "ADDR-BILL",
			"shipping_address": "ADDR-SHIP",
		}
		sync_customer.reset_mock()
		sync_address_display.reset_mock()
		sync_address_linked_docs(address, "on_update")

		sync_customer.assert_not_called()
		sync_address_display.assert_called_once_with(
			"CUST-001",
			"ADDR-1",
			"Updated address display",
		)
