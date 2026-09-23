import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from srv_erp.masters.dynamic_item.brand_rule_resolution import resolve_effective_rules
from srv_erp.masters.dynamic_item.brand_rule_sync import brand_templates, sync_brand_rule_revision
from srv_erp.masters.dynamic_item.brand_rules import (
	configuration_hash,
	draft_configuration,
	resolve_item_group_defaults,
	update_profile_publication_state,
)
from srv_erp.masters.dynamic_item.profile import validate_requested_attributes


def profile(mode="Inherit Brand Rules"):
	rows = [
		SimpleNamespace(item_attribute="Brand", required_parameter=1),
		SimpleNamespace(item_attribute="Colour", required_parameter=0),
	]
	return frappe._dict(
		configuration_mode=mode,
		attributes=rows,
		allowed_values=[],
		published_revision=0,
		published_configuration=None,
	)


class TestBrandRuleResolution(unittest.TestCase):
	def test_feature_flag_schema_default_is_off(self):
		settings_path = (
			Path(__file__).resolve().parents[1]
			/ "masters"
			/ "doctype"
			/ "masters_settings"
			/ "masters_settings.json"
		)
		settings = json.loads(settings_path.read_text())
		field = next(row for row in settings["fields"] if row["fieldname"] == "enable_brand_variant_rules")

		self.assertEqual(field["default"], "0")

	@patch(
		"srv_erp.masters.dynamic_item.brand_rule_resolution.are_brand_variant_rules_enabled",
		return_value=False,
	)
	def test_feature_off_preserves_current_template_profile(self, _enabled):
		resolved = resolve_effective_rules(MagicMock(), profile(), "Acme")

		self.assertEqual(resolved["source"], "Template Profile")
		self.assertFalse(resolved["requires_brand_selection"])
		self.assertEqual(
			[rule["attribute"] for rule in resolved["configuration"]["attributes"]],
			["Brand", "Colour"],
		)

	@patch(
		"srv_erp.masters.dynamic_item.brand_rule_resolution.are_brand_variant_rules_enabled",
		return_value=True,
	)
	def test_inherited_profile_requests_brand_before_loading_rules(self, _enabled):
		resolved = resolve_effective_rules(MagicMock(), profile())

		self.assertTrue(resolved["requires_brand_selection"])
		self.assertEqual(resolved["configuration"]["attributes"][0]["attribute"], "Brand")

	@patch("srv_erp.masters.dynamic_item.brand_rule_resolution.get_brand_profile")
	@patch(
		"srv_erp.masters.dynamic_item.brand_rule_resolution.are_brand_variant_rules_enabled",
		return_value=True,
	)
	def test_published_brand_configuration_is_effective(self, _enabled, get_profile):
		get_profile.return_value = frappe._dict(
			published_revision=3,
			published_configuration=json.dumps(
				{"attributes": [{"attribute": "Colour", "required": True, "values": ["Red"]}]}
			),
		)

		resolved = resolve_effective_rules(MagicMock(), profile(), "Acme")

		self.assertEqual(resolved["source"], "Brand")
		self.assertEqual(resolved["revision"], 3)
		self.assertEqual(resolved["configuration"]["attributes"][0]["values"], ["Acme"])
		self.assertEqual(resolved["configuration"]["attributes"][1]["values"], ["Red"])

	@patch("srv_erp.masters.dynamic_item.brand_rule_resolution.get_brand_profile", return_value=None)
	@patch(
		"srv_erp.masters.dynamic_item.brand_rule_resolution.are_brand_variant_rules_enabled",
		return_value=True,
	)
	def test_unconfigured_brand_falls_back_without_blocking(self, _enabled, _get_profile):
		resolved = resolve_effective_rules(MagicMock(), profile(), "Acme")

		self.assertTrue(resolved["fallback"])
		self.assertEqual(resolved["source"], "Template Profile Fallback")
		self.assertEqual(resolved["configuration"]["attributes"][0]["values"], ["Acme"])


class TestBrandRulePublication(unittest.TestCase):
	@patch("srv_erp.masters.dynamic_item.brand_rules.validate_global_value")
	def test_draft_hash_is_stable_and_published_snapshot_is_separate(self, _validate):
		attribute = SimpleNamespace(
			item_attribute="Colour",
			required_parameter=1,
		)
		value = SimpleNamespace(item_attribute="Colour", attribute_value="Red")
		doc = frappe._dict(
			attributes=[attribute],
			allowed_values=[value],
			published_revision=1,
			published_configuration=json.dumps(
				{"attributes": [{"attribute": "Colour", "required": True, "values": ["Red"]}]}
			),
		)

		update_profile_publication_state(doc)

		self.assertEqual(doc.publication_status, "Published")
		self.assertEqual(doc.draft_hash, configuration_hash(draft_configuration(doc)))


class TestBrandRuleValidation(unittest.TestCase):
	@patch("srv_erp.masters.dynamic_item.profile._", side_effect=lambda message: message)
	@patch(
		"srv_erp.masters.dynamic_item.profile.get_case_insensitive_attribute_value",
		return_value="Blue",
	)
	@patch("srv_erp.masters.dynamic_item.profile.resolve_effective_rules")
	@patch("srv_erp.masters.dynamic_item.profile.frappe")
	def test_value_outside_effective_brand_rule_is_rejected(
		self, frappe_mock, resolve, _known_value, _translate
	):
		frappe_mock._dict.side_effect = frappe._dict
		frappe_mock.db.exists.return_value = True
		frappe_mock.db.get_value.return_value = 0
		frappe_mock.throw.side_effect = frappe.ValidationError
		resolve.return_value = {
			"configuration": {"attributes": [{"attribute": "Colour", "required": True, "values": ["Red"]}]}
		}
		template = frappe._dict(name="Template", attributes=[frappe._dict(attribute="Colour")])

		with self.assertRaises(frappe.ValidationError):
			validate_requested_attributes(template, profile(), {"Colour": "Blue"})


class TestBrandRuleSyncSafety(unittest.TestCase):
	@patch("srv_erp.masters.dynamic_item.brand_rule_sync.frappe")
	def test_schema_sync_selects_templates_not_variant_rows(self, frappe_mock):
		frappe_mock.db.sql_list.return_value = ["Template"]

		self.assertEqual(brand_templates(), ["Template"])
		query = frappe_mock.db.sql_list.call_args.args[0]
		self.assertIn("item.has_variants = 1", query)
		self.assertIn("item.variant_based_on = 'Item Attribute'", query)

	@patch("srv_erp.masters.dynamic_item.brand_rule_sync.frappe")
	@patch(
		"srv_erp.masters.dynamic_item.brand_rule_sync.are_brand_variant_rules_enabled",
		return_value=True,
	)
	def test_stale_revision_exits_before_template_changes(self, _enabled, frappe_mock):
		profile_doc = frappe._dict(name="Acme", published_revision=4)
		frappe_mock.get_doc.return_value = profile_doc

		result = sync_brand_rule_revision("Acme", 3)

		self.assertEqual(result, {"stale": 1})
		frappe_mock.get_all.assert_not_called()


class TestItemGroupDefaults(unittest.TestCase):
	@patch("srv_erp.masters.dynamic_item.brand_rules.frappe")
	def test_nearest_ancestor_wins_per_attribute(self, frappe_mock):
		parents = {
			"LED Bulbs": "Lights",
			"Lights": "All Item Groups",
			"All Item Groups": None,
		}
		frappe_mock.db.get_value.side_effect = lambda doctype, name, field: parents.get(name)
		profile_doc = frappe._dict(
			item_group_defaults=[
				SimpleNamespace(item_group="Lights", item_attribute="Colour", attribute_value="White"),
				SimpleNamespace(item_group="LED Bulbs", item_attribute="Colour", attribute_value="Warm"),
				SimpleNamespace(item_group="LED Bulbs", item_attribute="Wattage", attribute_value="12"),
			]
		)

		resolved = resolve_item_group_defaults(profile_doc, "LED Bulbs")

		# nearest definition wins for Colour, and the parent supplies fallbacks
		self.assertEqual(resolved["Colour"], "Warm")
		self.assertEqual(resolved["Wattage"], "12")

	def test_no_item_group_returns_empty(self):
		self.assertEqual(resolve_item_group_defaults(frappe._dict(item_group_defaults=[]), None), {})
