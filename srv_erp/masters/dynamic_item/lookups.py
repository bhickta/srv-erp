from __future__ import annotations

import frappe
from frappe import _


def get_case_insensitive_name(doctype: str, value: str) -> str | None:
	table = {
		"Item Attribute": "`tabItem Attribute`",
		"Item Attribute Value": "`tabItem Attribute Value`",
		"Brand": "`tabBrand`",
		"UOM": "`tabUOM`",
	}.get(doctype)
	if not table:
		frappe.throw(_("Unsupported master lookup: {0}").format(doctype))

	field = "attribute_value" if doctype == "Item Attribute Value" else "name"
	if doctype == "Item Attribute Value":
		frappe.throw(_("Item Attribute Value lookup requires an attribute."))
	rows = frappe.db.sql(
		f"select `{field}` from {table} where lower(`{field}`) = lower(%(value)s) order by creation limit 1",
		{"value": value},
	)
	return rows[0][0] if rows else None


def get_case_insensitive_attribute_value(attribute: str, value: str) -> str | None:
	rows = frappe.db.sql(
		"""
		select attribute_value
		from `tabItem Attribute Value`
		where parent = %(attribute)s
			and lower(attribute_value) = lower(%(value)s)
		order by idx
		limit 1
		""",
		{"attribute": attribute, "value": value},
	)
	return rows[0][0] if rows else None


def canonicalize_known_masters(attributes: dict[str, str]) -> dict[str, str]:
	canonical = {}
	for attribute, value in attributes.items():
		canonical_attribute = get_case_insensitive_name("Item Attribute", attribute) or attribute
		canonical_value = (
			get_case_insensitive_attribute_value(canonical_attribute, value)
			if frappe.db.exists("Item Attribute", canonical_attribute)
			else None
		)
		canonical[canonical_attribute] = canonical_value or value
	return canonical
