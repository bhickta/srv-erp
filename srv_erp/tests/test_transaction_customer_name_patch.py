import frappe
from frappe.tests.utils import FrappeTestCase

from srv_erp.patches.sync_transaction_customer_names import execute


class TestTransactionCustomerNamePatch(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"name": "_TEST-CUSTOMER-NAME-PATCH-" + frappe.generate_hash(length=8),
				"customer_name": "Latest Customer Name",
			}
		)
		# Lightweight persisted fixtures avoid unrelated transaction validation and Customer hooks.
		self.customer.db_insert()

	def transaction(self, doctype, customer_name, docstatus=0, customer=None):
		doc = frappe.get_doc(
			{
				"doctype": doctype,
				"name": "_TEST-NAME-PATCH-" + frappe.generate_hash(length=8),
				"customer": self.customer.name if customer is None else customer,
				"customer_name": customer_name,
				"docstatus": docstatus,
				"status": {0: "Draft", 1: "To Bill", 2: "Cancelled"}[docstatus],
				"modified": "2026-01-01 12:34:56.123456",
				"modified_by": "Administrator",
				"grand_total": 125,
				"address_display": "Historical address",
				**({"title": "Historical document title"} if doctype == "Delivery Note" else {}),
			}
		)
		doc.db_insert()
		return doc

	def snapshot(self, doc):
		return frappe.get_doc(doc.doctype, doc.name).as_dict(convert_dates_to_str=True)

	def test_syncs_all_document_states_and_changes_only_customer_name(self):
		docs = [
			self.transaction(doctype, "Old Customer Name", docstatus)
			for doctype in ("Sales Order", "Delivery Note")
			for docstatus in (0, 1, 2)
		]
		before = [self.snapshot(doc) for doc in docs]
		execute()
		for doc, expected in zip(docs, before, strict=True):
			expected["customer_name"] = self.customer.customer_name
			self.assertEqual(self.snapshot(doc), expected)

	def test_fills_blank_names_and_applies_case_only_changes(self):
		for doctype in ("Sales Order", "Delivery Note"):
			for name in (None, "", "latest customer name", "Latest Customer Name "):
				doc = self.transaction(doctype, name)
				execute()
				self.assertEqual(
					frappe.db.get_value(doctype, doc.name, "customer_name"), self.customer.customer_name
				)

	def test_unlinked_and_missing_customers_are_untouched(self):
		docs = [
			self.transaction(doctype, "Keep this name", customer=customer)
			for doctype in ("Sales Order", "Delivery Note")
			for customer in ("", "_MISSING-CUSTOMER-NAME-PATCH")
		]
		before = [self.snapshot(doc) for doc in docs]
		execute()
		self.assertEqual([self.snapshot(doc) for doc in docs], before)

	def test_repeat_runs_are_safe_and_use_the_latest_master_name(self):
		docs = [self.transaction(doctype, "Old name") for doctype in ("Sales Order", "Delivery Note")]
		execute()
		first = [self.snapshot(doc) for doc in docs]
		execute()
		self.assertEqual([self.snapshot(doc) for doc in docs], first)
		frappe.db.set_value("Customer", self.customer.name, "customer_name", "Renamed Customer")
		execute()
		for doc in docs:
			self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "customer_name"), "Renamed Customer")

	def test_clears_cached_transaction_names(self):
		for doctype in ("Sales Order", "Delivery Note"):
			doc = self.transaction(doctype, "Cached old name")
			self.assertEqual(frappe.get_cached_doc(doctype, doc.name).customer_name, "Cached old name")
			execute()
			self.assertEqual(
				frappe.get_cached_doc(doctype, doc.name).customer_name, self.customer.customer_name
			)
