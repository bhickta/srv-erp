"""Backfill transaction customer names from their linked Customer master."""

import frappe


def execute():
	for doctype in ("Sales Order", "Delivery Note"):
		# A direct update also covers submitted/cancelled records and preserves audit timestamps.
		# Binary comparison catches case-only changes and trailing spaces in display names.
		frappe.db.sql(
			f"""
			UPDATE `tab{doctype}` transaction_doc
			INNER JOIN `tabCustomer` customer ON customer.name = transaction_doc.customer
			SET transaction_doc.customer_name = customer.customer_name
			WHERE NOT (BINARY transaction_doc.customer_name <=> BINARY customer.customer_name)
			"""
		)
		frappe.clear_document_cache(doctype)
