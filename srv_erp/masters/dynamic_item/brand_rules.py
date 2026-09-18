from __future__ import annotations

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import cint

BRAND_ATTRIBUTE = "Brand"


def draft_configuration(profile) -> dict:
	values = {}
	for row in profile.get("allowed_values") or []:
		if row.item_attribute and row.attribute_value:
			values.setdefault(row.item_attribute, []).append(row.attribute_value.strip())
	attributes = []
	for row in profile.get("attributes") or []:
		if not row.item_attribute:
			continue
		attributes.append(
			{
				"attribute": row.item_attribute,
				"required": bool(cint(row.required_parameter)),
				"values": sorted(set(values.get(row.item_attribute, [])), key=str.casefold),
			}
		)
	return {"attributes": attributes}


def canonical_json(configuration: dict) -> str:
	return json.dumps(configuration, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def configuration_hash(configuration: dict) -> str:
	return hashlib.sha256(canonical_json(configuration).encode()).hexdigest()


def get_published_configuration(profile) -> dict | None:
	if (
		not profile
		or not cint(profile.get("published_revision"))
		or not profile.get("published_configuration")
	):
		return None
	try:
		configuration = json.loads(profile.published_configuration)
	except (TypeError, ValueError):
		return None
	return configuration if isinstance(configuration, dict) else None


def update_profile_publication_state(profile):
	validate_draft(profile, publishing=False)
	configuration = draft_configuration(profile)
	profile.draft_hash = configuration_hash(configuration)
	published = get_published_configuration(profile)
	if not published:
		profile.publication_status = "Draft"
	elif configuration_hash(published) == profile.draft_hash:
		profile.publication_status = "Published"
	else:
		profile.publication_status = "Changes Pending"


def validate_draft(profile, publishing=False):
	attributes = [row.item_attribute for row in profile.get("attributes") or [] if row.item_attribute]
	if len(attributes) != len(set(attributes)):
		frappe.throw(_("Brand variant rules cannot contain duplicate Item Attributes."))
	if any(attribute.casefold() == BRAND_ATTRIBUTE.casefold() for attribute in attributes):
		frappe.throw(_("Brand is implicit and must not be added as a Brand variant rule."))

	configured = set(attributes)
	seen_values = set()
	values_by_attribute = {}
	for row in profile.get("allowed_values") or []:
		key = (row.item_attribute, (row.attribute_value or "").casefold())
		if not row.item_attribute or not row.attribute_value:
			frappe.throw(_("Item Attribute and Allowed Value are required on every value row."))
		if row.item_attribute not in configured:
			frappe.throw(_("Allowed values must belong to a configured Brand attribute rule."))
		if key in seen_values:
			frappe.throw(_("Brand variant rules cannot contain duplicate allowed values."))
		seen_values.add(key)
		values_by_attribute.setdefault(row.item_attribute, []).append(row.attribute_value)
		validate_global_value(row.item_attribute, row.attribute_value)

	if not publishing:
		return
	for attribute in attributes:
		if is_numeric_attribute(attribute):
			continue
		if not values_by_attribute.get(attribute):
			frappe.throw(
				_("Select at least one allowed value for categorical attribute {0}.").format(
					frappe.bold(attribute)
				)
			)


def validate_global_value(attribute: str, value: str):
	if is_numeric_attribute(attribute):
		frappe.throw(_("Numeric attributes use the range configured on each Item template."))
	found = frappe.db.exists(
		"Item Attribute Value",
		{"parent": attribute, "attribute_value": value},
	)
	if not found:
		frappe.throw(
			_("Value {0} is not configured on Item Attribute {1}.").format(
				frappe.bold(value), frappe.bold(attribute)
			)
		)


def is_numeric_attribute(attribute: str) -> bool:
	return bool(cint(frappe.db.get_value("Item Attribute", attribute, "numeric_values")))


def get_brand_profile(brand: str):
	name = frappe.db.get_value("Brand Variant Profile", {"brand": brand}, "name")
	return frappe.get_doc("Brand Variant Profile", name) if name else None
