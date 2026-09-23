from __future__ import annotations

import hashlib
import json

import frappe
from frappe.utils import now_datetime


def audit_existing_variants(profile, configuration, revision, previous_configuration) -> int:
	rules = {row["attribute"]: row for row in configuration.get("attributes", [])}
	previous = {row["attribute"]: row for row in previous_configuration.get("attributes", [])}
	removed_attributes = set(previous) - set(rules)
	removed_values = {
		attribute: set(previous[attribute].get("values", [])) - set(rules[attribute].get("values", []))
		for attribute in set(previous).intersection(rules)
	}
	variants = variants_for_brand(profile.brand)
	conflicts = 0
	for item_code, variant in variants.items():
		for attribute, rule in rules.items():
			value = variant["attributes"].get(attribute)
			if rule.get("required") and not value:
				add_conflict(
					profile, revision, "Missing Required Attribute", variant["template"], attribute, item_code
				)
				conflicts += 1
			elif value and rule.get("values") and value not in rule["values"]:
				add_conflict(
					profile,
					revision,
					"Disallowed Existing Value",
					variant["template"],
					attribute,
					item_code,
					value,
				)
				conflicts += 1
		for attribute in removed_attributes:
			if variant["attributes"].get(attribute):
				add_conflict(
					profile,
					revision,
					"Removed Attribute In Use",
					variant["template"],
					attribute,
					item_code,
					variant["attributes"][attribute],
				)
				conflicts += 1
		for attribute, values in removed_values.items():
			if variant["attributes"].get(attribute) in values:
				add_conflict(
					profile,
					revision,
					"Removed Value In Use",
					variant["template"],
					attribute,
					item_code,
					variant["attributes"][attribute],
				)
				conflicts += 1
	return conflicts


def variants_for_brand(brand: str) -> dict:
	rows = frappe.db.sql(
		"""
		select item.name, item.variant_of, attribute.attribute, attribute.attribute_value
		from `tabItem` item
		inner join `tabItem Variant Attribute` selected_brand
			on selected_brand.parent = item.name and lower(selected_brand.attribute) = 'brand'
		left join `tabItem Variant Attribute` attribute on attribute.parent = item.name
		where lower(selected_brand.attribute_value) = lower(%s)
		""",
		brand,
		as_dict=True,
	)
	variants = {}
	for row in rows:
		variant = variants.setdefault(row.name, {"template": row.variant_of, "attributes": {}})
		if row.attribute:
			variant["attributes"][row.attribute] = row.attribute_value
	return variants


def add_conflict(
	profile, revision, conflict_type, template, attribute=None, item_code=None, value=None, details=None
):
	filters = {
		"profile": profile.name,
		"revision": revision,
		"conflict_type": conflict_type,
		"template_item": template,
		"item_code": item_code or "",
		"item_attribute": attribute or "",
		"attribute_value": value or "",
	}
	conflict_key = hashlib.sha256(json.dumps(filters, sort_keys=True).encode()).hexdigest()
	existing = frappe.db.exists("Brand Variant Rule Conflict", conflict_key)
	if existing:
		frappe.db.set_value(
			"Brand Variant Rule Conflict",
			existing,
			{"status": "Open", "detected_on": now_datetime(), "details": details},
			update_modified=False,
		)
		return
	frappe.get_doc(
		{
			"doctype": "Brand Variant Rule Conflict",
			"conflict_key": conflict_key,
			"brand": profile.brand,
			**filters,
			"details": details,
			"detected_on": now_datetime(),
		}
	).insert(ignore_permissions=True)


def resolve_open_conflicts(profile):
	frappe.db.sql(
		"""update `tabBrand Variant Rule Conflict`
		set status = 'Resolved'
		where profile = %s and status = 'Open'""",
		profile.name,
	)
