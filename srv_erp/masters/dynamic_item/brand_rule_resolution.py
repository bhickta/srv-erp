from __future__ import annotations

from collections import defaultdict

import frappe
from frappe.utils import cint

from srv_erp.masters.dynamic_item.brand_rules import (
	BRAND_ATTRIBUTE,
	get_brand_profile,
	get_published_configuration,
)
from srv_erp.masters.dynamic_item.configuration import are_brand_variant_rules_enabled


def resolve_effective_rules(template, profile, selected_brand=None) -> dict:
	current = current_profile_configuration(profile)
	if not are_brand_variant_rules_enabled():
		return result(current, "Template Profile", None)
	if (profile.get("configuration_mode") or "Inherit Brand Rules") == "Template Override":
		return result(override_configuration(profile), "Template Override", None)
	if not any(
		rule.get("attribute", "").casefold() == BRAND_ATTRIBUTE.casefold()
		for rule in current.get("attributes", [])
	):
		return result(current, "Template Profile", None)
	if not selected_brand:
		return {
			"configuration": brand_selection_configuration(current),
			"source": "Brand Selection",
			"revision": None,
			"requires_brand_selection": True,
			"fallback": False,
		}
	brand_profile = get_brand_profile(selected_brand)
	published = get_published_configuration(brand_profile)
	if not published:
		fallback = constrain_brand(current, selected_brand)
		resolved = result(fallback, "Template Profile Fallback", None)
		resolved["fallback"] = True
		return resolved
	configuration = {"attributes": [implicit_brand_rule(selected_brand), *published.get("attributes", [])]}
	return result(configuration, "Brand", cint(brand_profile.published_revision))


def current_profile_configuration(profile) -> dict:
	return {
		"attributes": [
			{"attribute": row.item_attribute, "required": bool(cint(row.required_parameter)), "values": []}
			for row in profile.get("attributes") or []
			if row.item_attribute
		]
	}


def override_configuration(profile) -> dict:
	values = defaultdict(list)
	for row in profile.get("allowed_values") or []:
		if row.item_attribute and row.attribute_value:
			values[row.item_attribute].append(row.attribute_value)
	return {
		"attributes": [
			{
				"attribute": row.item_attribute,
				"required": bool(cint(row.required_parameter)),
				"values": values.get(row.item_attribute, []),
			}
			for row in profile.get("attributes") or []
			if row.item_attribute
		]
	}


def brand_selection_configuration(configuration: dict) -> dict:
	brand = next(
		(
			rule
			for rule in configuration.get("attributes", [])
			if rule.get("attribute", "").casefold() == BRAND_ATTRIBUTE.casefold()
		),
		None,
	)
	return {"attributes": [brand or {"attribute": BRAND_ATTRIBUTE, "required": True, "values": []}]}


def implicit_brand_rule(brand: str) -> dict:
	return {"attribute": BRAND_ATTRIBUTE, "required": True, "values": [brand]}


def constrain_brand(configuration: dict, brand: str) -> dict:
	return {
		"attributes": [
			implicit_brand_rule(brand)
			if rule.get("attribute", "").casefold() == BRAND_ATTRIBUTE.casefold()
			else rule
			for rule in configuration.get("attributes", [])
		]
	}


def result(configuration, source, revision):
	return {
		"configuration": configuration,
		"source": source,
		"revision": revision,
		"requires_brand_selection": False,
		"fallback": False,
	}
