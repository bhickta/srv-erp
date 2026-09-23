from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from srv_erp.masters.dynamic_item.brand_rules import (
	canonical_json,
	draft_configuration,
	get_brand_profile,
	get_published_configuration,
	is_numeric_attribute,
	validate_draft,
)
from srv_erp.masters.dynamic_item.configuration import (
	are_brand_variant_rules_enabled,
	user_has_approver_role,
)


def require_rule_manager():
	if "System Manager" not in frappe.get_roles() and not user_has_approver_role():
		frappe.throw(_("Not permitted to manage Brand variant rules."), frappe.PermissionError)


@frappe.whitelist()
def get_brand_variant_rules_state(brand: str) -> dict:
	if not frappe.db.exists("Brand", brand):
		frappe.throw(_("Brand {0} does not exist.").format(frappe.bold(brand)))
	profile = get_brand_profile(brand)
	return {
		"enabled": are_brand_variant_rules_enabled(),
		"can_manage": "System Manager" in frappe.get_roles() or user_has_approver_role(),
		"brand": brand,
		"profile": profile.name if profile else None,
		"publication_status": profile.publication_status if profile else "Draft",
		"published_revision": cint(profile.published_revision) if profile else 0,
		"sync_status": profile.sync_status if profile else "Not Queued",
		"last_sync_on": profile.last_sync_on if profile else None,
		"last_sync_message": profile.last_sync_message if profile else None,
		"rules": draft_rules_for_client(profile) if profile else [],
	}


def draft_rules_for_client(profile) -> list[dict]:
	configuration = draft_configuration(profile)
	rows = {row.item_attribute: row for row in profile.get("attributes") or []}
	return [
		{
			**rule,
			"confidence": rows[rule["attribute"]].suggestion_confidence or "",
			"note": rows[rule["attribute"]].suggestion_note or "",
		}
		for rule in configuration["attributes"]
	]


@frappe.whitelist()
def save_brand_variant_rules_draft(brand: str, rules) -> dict:
	require_rule_manager()
	rules = frappe.parse_json(rules) if isinstance(rules, str) else rules or []
	profile = get_brand_profile(brand) or frappe.new_doc("Brand Variant Profile")
	if profile.is_new():
		profile.brand = brand
	profile.set("attributes", [])
	profile.set("allowed_values", [])
	for rule in rules:
		rule = frappe._dict(rule)
		profile.append(
			"attributes",
			{
				"item_attribute": rule.attribute,
				"required_parameter": cint(rule.required),
				"suggestion_confidence": rule.confidence or "",
				"suggestion_note": rule.note or "",
			},
		)
		for value in rule.get("values") or []:
			profile.append("allowed_values", {"item_attribute": rule.attribute, "attribute_value": value})
	profile.save(ignore_permissions=True)
	return get_brand_variant_rules_state(brand)


@frappe.whitelist()
def publish_brand_variant_rules(brand: str) -> dict:
	require_rule_manager()
	if not are_brand_variant_rules_enabled():
		frappe.throw(_("Enable Brand Variant Rules in Masters Settings before publishing."))
	profile = get_brand_profile(brand)
	if not profile:
		frappe.throw(_("Save Brand variant rules before publishing."))
	validate_draft(profile, publishing=True)
	previous = get_published_configuration(profile) or {"attributes": []}
	profile.previous_configuration = canonical_json(previous)
	profile.published_configuration = canonical_json(draft_configuration(profile))
	profile.published_revision = cint(profile.published_revision) + 1
	profile.published_on = now_datetime()
	profile.published_by = frappe.session.user
	profile.sync_status = "Pending"
	profile.last_sync_message = _("Revision {0} is queued.").format(profile.published_revision)
	profile.save(ignore_permissions=True)
	from srv_erp.masters.dynamic_item.brand_rule_sync import enqueue_brand_rule_sync

	enqueue_brand_rule_sync(profile.name, profile.published_revision, previous)
	return get_brand_variant_rules_state(brand)


@frappe.whitelist()
def retry_brand_variant_rule_sync(brand: str) -> dict:
	require_rule_manager()
	if not are_brand_variant_rules_enabled():
		frappe.throw(_("Brand Variant Rules are disabled."))
	profile = get_brand_profile(brand)
	if not profile or not cint(profile.published_revision):
		frappe.throw(_("Publish Brand variant rules before synchronizing."))
	profile.db_set("sync_status", "Pending", update_modified=False)
	from srv_erp.masters.dynamic_item.brand_rule_sync import enqueue_brand_rule_sync

	enqueue_brand_rule_sync(profile.name, profile.published_revision)
	return get_brand_variant_rules_state(brand)


@frappe.whitelist()
def generate_brand_variant_rule_suggestions(brand: str) -> list[dict]:
	require_rule_manager()
	brand_variants = frappe.db.sql(
		"""
		select distinct item.name, item.variant_of
		from `tabItem` item
		inner join `tabItem Variant Attribute` brand
			on brand.parent = item.name and lower(brand.attribute) = 'brand'
		where item.variant_of is not null and item.variant_of != ''
			and lower(brand.attribute_value) = lower(%s)
		""",
		brand,
		as_dict=True,
	)
	total_variants = len(brand_variants)
	rows = frappe.db.sql(
		"""
		select other.attribute, other.attribute_value, item.variant_of, item.name
		from `tabItem` item
		inner join `tabItem Variant Attribute` brand
			on brand.parent = item.name and lower(brand.attribute) = 'brand'
		inner join `tabItem Variant Attribute` other
			on other.parent = item.name and lower(other.attribute) != 'brand'
		where item.variant_of is not null and item.variant_of != ''
			and lower(brand.attribute_value) = lower(%s)
		""",
		brand,
		as_dict=True,
	)
	grouped = {}
	for row in rows:
		entry = grouped.setdefault(row.attribute, {"values": set(), "templates": set(), "items": set()})
		entry["values"].add(row.attribute_value)
		entry["templates"].add(row.variant_of)
		entry["items"].add(row.name)
	observed_templates = sorted({row.variant_of for row in brand_variants if row.variant_of})
	if observed_templates:
		profile_rows = frappe.db.sql(
			"""
			select attribute.item_attribute, profile.item_template
			from `tabDynamic Variant Profile` profile
			inner join `tabDynamic Variant Profile Attribute` attribute
				on attribute.parent = profile.name
			where profile.item_template in %(templates)s
				and lower(attribute.item_attribute) != 'brand'
			""",
			{"templates": tuple(observed_templates)},
			as_dict=True,
		)
		for row in profile_rows:
			entry = grouped.setdefault(
				row.item_attribute, {"values": set(), "templates": set(), "items": set()}
			)
			entry["templates"].add(row.item_template)
	return [
		{
			"attribute": attribute,
			"required": len(data["items"]) == total_variants,
			"values": [] if is_numeric_attribute(attribute) else sorted(data["values"], key=str.casefold),
			"confidence": "High" if len(data["templates"]) > 1 else "Low",
			"note": _("Observed on {0} variant(s) across {1} template(s).").format(
				len(data["items"]), len(data["templates"])
			),
		}
		for attribute, data in sorted(grouped.items())
	]
