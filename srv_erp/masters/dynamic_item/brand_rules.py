from __future__ import annotations

import hashlib
import json
import math

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
	defaults = normalize_item_group_defaults(
		[
			row.as_dict() if callable(getattr(row, "as_dict", None)) else row
			for row in profile.get("item_group_defaults") or []
		]
	)
	return {"schema_version": 2, "attributes": attributes, "item_group_defaults": defaults}


def normalize_item_group_defaults(rows) -> list[dict]:
	result = []
	for row in rows or []:
		group = (row.get("item_group") if isinstance(row, dict) else row.item_group) or ""
		attribute = (row.get("item_attribute") if isinstance(row, dict) else row.item_attribute) or ""
		value = (row.get("attribute_value") if isinstance(row, dict) else row.attribute_value) or ""
		if group and attribute and str(value).strip():
			result.append(
				{
					"item_group": group.strip(),
					"item_attribute": attribute.strip(),
					"attribute_value": str(value).strip(),
				}
			)
	return sorted(result, key=lambda row: (row["item_group"].casefold(), row["item_attribute"].casefold()))


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
	except TypeError, ValueError:
		return None
	if not isinstance(configuration, dict):
		return None
	configuration.setdefault("schema_version", 2)
	configuration.setdefault("attributes", [])
	configuration.setdefault("item_group_defaults", [])
	return configuration


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

	validate_item_group_defaults(profile, values_by_attribute)

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


def validate_item_group_defaults(profile, values_by_attribute: dict):
	seen = set()
	for row in profile.get("item_group_defaults") or []:
		if not row.item_group or not row.item_attribute or not row.attribute_value:
			frappe.throw(_("Item Group, Item Attribute and Default Value are required on every default row."))
		if not frappe.db.exists("Item Attribute", row.item_attribute):
			frappe.throw(_("Item Attribute {0} does not exist.").format(frappe.bold(row.item_attribute)))
		if not frappe.db.exists("Item Group", row.item_group):
			frappe.throw(_("Item Group {0} does not exist.").format(frappe.bold(row.item_group)))
		key = (row.item_group, row.item_attribute)
		if key in seen:
			frappe.throw(_("Brand variant rules cannot contain duplicate Item Group defaults."))
		seen.add(key)
		if row.item_attribute.casefold() == BRAND_ATTRIBUTE.casefold():
			frappe.throw(_("Brand is selected separately and cannot have an Item Group value."))
		row.attribute_value = row.attribute_value.strip()

		if is_numeric_attribute(row.item_attribute):
			validate_numeric_default(row.item_attribute, row.attribute_value)
			continue

		allowed = {value.casefold() for value in values_by_attribute.get(row.item_attribute, [])}
		if allowed and row.attribute_value.strip().casefold() not in allowed:
			frappe.throw(
				_("Default value {0} is not an allowed value for attribute {1}.").format(
					frappe.bold(row.attribute_value), frappe.bold(row.item_attribute)
				)
			)
		from srv_erp.masters.dynamic_item.lookups import get_case_insensitive_attribute_value

		canonical_value = get_case_insensitive_attribute_value(row.item_attribute, row.attribute_value)
		if not canonical_value:
			frappe.throw(
				_("Value {0} is not configured on Item Attribute {1}.").format(
					frappe.bold(row.attribute_value), frappe.bold(row.item_attribute)
				)
			)
		row.attribute_value = canonical_value


def validate_numeric_default(attribute: str, value: str):
	try:
		number = float(value)
	except TypeError, ValueError:
		frappe.throw(
			_("Default value {0} must be a number for numeric attribute {1}.").format(
				frappe.bold(value), frappe.bold(attribute)
			)
		)
	if not math.isfinite(number):
		frappe.throw(
			_("Default value {0} must be a finite number for attribute {1}.").format(
				frappe.bold(value), frappe.bold(attribute)
			)
		)


def item_group_hierarchy(item_group: str) -> list[str]:
	hierarchy = []
	seen = set()
	current = item_group
	while current and current not in seen:
		hierarchy.append(current)
		seen.add(current)
		current = frappe.db.get_value("Item Group", current, "parent_item_group")
	return hierarchy


def resolve_item_group_defaults(profile, item_group: str) -> dict[str, str]:
	if not item_group:
		return {}
	by_group = {}
	for row in profile.get("item_group_defaults") or []:
		if row.item_group and row.item_attribute and row.attribute_value:
			by_group.setdefault(row.item_group, {})[row.item_attribute] = row.attribute_value
	resolved = {}
	for group in item_group_hierarchy(item_group):
		for attribute, value in by_group.get(group, {}).items():
			resolved.setdefault(attribute, value)
	return resolved


def resolve_published_item_group_defaults(configuration: dict, item_group: str) -> dict[str, dict]:
	if not item_group:
		return {}
	by_group = {}
	for row in (configuration or {}).get("item_group_defaults") or []:
		if row.get("item_group") and row.get("item_attribute") and row.get("attribute_value"):
			by_group.setdefault(row["item_group"], {})[row["item_attribute"]] = row["attribute_value"]
	resolved = {}
	for group in item_group_hierarchy(item_group):
		for attribute, value in by_group.get(group, {}).items():
			resolved.setdefault(attribute, {"value": value, "source_group": group})
	return resolved


def group_defaults_from_configuration(configuration: dict) -> list[dict]:
	return normalize_item_group_defaults((configuration or {}).get("item_group_defaults"))


def get_brand_profile(brand: str):
	name = frappe.db.get_value("Brand Variant Profile", {"brand": brand}, "name")
	return frappe.get_doc("Brand Variant Profile", name) if name else None
