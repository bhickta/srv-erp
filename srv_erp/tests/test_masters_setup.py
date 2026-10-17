import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from frappe import DuplicateEntryError

from srv_erp.masters.dynamic_item.configuration import (
	APPROVER_ROLE,
	REQUESTER_ROLE,
	masters_settings_available,
)
from srv_erp.masters.setup import (
	activate_dynamic_item_creation,
	bootstrap_dynamic_variant_profiles,
	provision_masters_user_roles,
)
from srv_erp.patches.enforce_predefined_dynamic_item_attributes import execute as enforce_predefined


class TestMastersSetup(unittest.TestCase):
	def bootstrap_profile_store(self, profiles, templates):
		"""Model field autonaming and primary-key uniqueness without a live database."""
		frappe = MagicMock()
		frappe.db.exists.side_effect = lambda doctype, name: (
			True if doctype == "DocType" else name in profiles
		)
		frappe.get_all.side_effect = lambda doctype, **kwargs: (
			templates if doctype == "Item" else ["Colour"]
		)

		def new_profile(values):
			profile = SimpleNamespace(**values, attributes=[])
			profile.append = lambda field, row: getattr(profile, field).append(row)

			def insert(ignore_permissions=False, set_name=None):
				name = set_name or profile.item_template.strip()
				if name in profiles:
					raise DuplicateEntryError("Dynamic Variant Profile", name)
				profiles[name] = {
					"item_template": profile.item_template,
					"enabled": profile.enabled,
					"attributes": profile.attributes,
				}
				return profile

			profile.insert = insert
			return profile

		frappe.get_doc.side_effect = new_profile
		get_profile_name = lambda template: next(
			(name for name, profile in profiles.items() if profile["item_template"] == template), None
		)
		return frappe, get_profile_name

	def test_bootstrap_preserves_renamed_profile_and_creates_reused_template_name(self):
		existing = {"item_template": "FB 389", "enabled": 0, "attributes": [{"custom": True}]}
		profiles = {"FB 391": existing}
		frappe, get_profile_name = self.bootstrap_profile_store(profiles, ["FB 389", "FB 391"])

		with (
			patch("srv_erp.masters.setup.frappe", frappe),
			patch("srv_erp.masters.setup.get_dynamic_variant_profile_name", side_effect=get_profile_name),
		):
			self.assertEqual(bootstrap_dynamic_variant_profiles(), 1)
			created_name = get_profile_name("FB 391")
			self.assertEqual(bootstrap_dynamic_variant_profiles(), 0)

		self.assertIs(profiles["FB 391"], existing)
		self.assertEqual(existing, {"item_template": "FB 389", "enabled": 0, "attributes": [{"custom": True}]})
		self.assertEqual(created_name, "FB 391-1")
		self.assertEqual(profiles[created_name]["enabled"], 1)
		self.assertEqual(
			profiles[created_name]["attributes"],
			[{"item_attribute": "Colour", "required_parameter": 0, "allow_new_values": 0}],
		)

	def test_bootstrap_preserves_default_name_when_available(self):
		profiles = {}
		frappe, get_profile_name = self.bootstrap_profile_store(profiles, ["FB 391"])
		with (
			patch("srv_erp.masters.setup.frappe", frappe),
			patch("srv_erp.masters.setup.get_dynamic_variant_profile_name", side_effect=get_profile_name),
		):
			self.assertEqual(bootstrap_dynamic_variant_profiles(), 1)
		self.assertEqual(list(profiles), ["FB 391"])

	def test_bootstrap_alternate_name_is_stable_and_fits_name_limit(self):
		template = "F" * 140
		alternate_names = []
		for _ in range(2):
			profiles = {template: {"item_template": "RENAMED", "enabled": 1}}
			frappe, get_profile_name = self.bootstrap_profile_store(profiles, [template])
			with (
				patch("srv_erp.masters.setup.frappe", frappe),
				patch("srv_erp.masters.setup.get_dynamic_variant_profile_name", side_effect=get_profile_name),
			):
				self.assertEqual(bootstrap_dynamic_variant_profiles(), 1)
			alternate_names.append(get_profile_name(template))
		self.assertEqual(alternate_names[0], alternate_names[1])
		self.assertLessEqual(len(alternate_names[0]), 140)

	def test_bootstrap_retruncates_long_name_when_suffix_grows(self):
		template = "F" * 140
		profiles = {template: {"item_template": "RENAMED", "enabled": 1}}
		for counter in range(1, 10):
			profiles[template[:138] + f"-{counter}"] = {
				"item_template": f"RENAMED {counter}", "enabled": 1
			}
		frappe, get_profile_name = self.bootstrap_profile_store(profiles, [template])
		with (
			patch("srv_erp.masters.setup.frappe", frappe),
			patch("srv_erp.masters.setup.get_dynamic_variant_profile_name", side_effect=get_profile_name),
		):
			self.assertEqual(bootstrap_dynamic_variant_profiles(), 1)
		self.assertEqual(get_profile_name(template), template[:137] + "-10")

	def test_bootstrap_handles_repeated_rename_and_name_reuse(self):
		profiles = {
			"FB 391": {"item_template": "FB 389", "enabled": 1},
			"FB 391-1": {"item_template": "FB 390", "enabled": 0},
		}
		frappe, get_profile_name = self.bootstrap_profile_store(profiles, ["FB 391"])
		with (
			patch("srv_erp.masters.setup.frappe", frappe),
			patch("srv_erp.masters.setup.get_dynamic_variant_profile_name", side_effect=get_profile_name),
		):
			self.assertEqual(bootstrap_dynamic_variant_profiles(), 1)
			self.assertEqual(bootstrap_dynamic_variant_profiles(), 0)
		self.assertEqual(get_profile_name("FB 391"), "FB 391-2")
		self.assertEqual(profiles["FB 391-1"], {"item_template": "FB 390", "enabled": 0})

	def test_bootstrap_does_not_hide_concurrent_insert_conflicts(self):
		profiles = {}
		frappe, get_profile_name = self.bootstrap_profile_store(profiles, ["FB 391"])
		profile = MagicMock()
		profile.insert.side_effect = DuplicateEntryError("Dynamic Variant Profile", "FB 391")
		frappe.get_doc.side_effect = None
		frappe.get_doc.return_value = profile
		with (
			patch("srv_erp.masters.setup.frappe", frappe),
			patch("srv_erp.masters.setup.get_dynamic_variant_profile_name", side_effect=get_profile_name),
		):
			with self.assertRaises(DuplicateEntryError):
				bootstrap_dynamic_variant_profiles()
		profile.insert.assert_called_once_with(ignore_permissions=True)

	@patch("srv_erp.masters.setup.frappe")
	def test_profile_bootstrap_waits_for_doctype(self, frappe):
		frappe.db.exists.return_value = False
		self.assertEqual(bootstrap_dynamic_variant_profiles(), 0)
		frappe.get_all.assert_not_called()

	@patch("srv_erp.masters.setup.get_dynamic_variant_profile_name", return_value="APL  562")
	@patch("srv_erp.masters.setup.frappe")
	def test_profile_bootstrap_is_idempotent_after_template_rename(self, frappe, get_profile_name):
		frappe.db.exists.return_value = True
		frappe.get_all.return_value = ["APL 562"]

		created = bootstrap_dynamic_variant_profiles()

		self.assertEqual(created, 0)
		get_profile_name.assert_called_once_with("APL 562")
		frappe.get_doc.assert_not_called()

	@patch("srv_erp.masters.dynamic_item.configuration.frappe")
	def test_settings_are_unavailable_until_every_child_table_exists(self, frappe):
		frappe.db.exists.return_value = "Masters Settings"
		frappe.db.table_exists.side_effect = [True, False]

		self.assertFalse(masters_settings_available())
		self.assertEqual(frappe.db.table_exists.call_count, 2)
		for table_call in frappe.db.table_exists.call_args_list:
			self.assertFalse(table_call.kwargs["cached"])

	@patch("srv_erp.masters.dynamic_item.configuration.frappe")
	def test_settings_are_available_after_every_child_table_exists(self, frappe):
		frappe.db.exists.return_value = "Masters Settings"
		frappe.db.table_exists.return_value = True

		self.assertTrue(masters_settings_available())

	@patch("srv_erp.patches.enforce_predefined_dynamic_item_attributes.clear_settings_cache")
	@patch("srv_erp.patches.enforce_predefined_dynamic_item_attributes.frappe")
	def test_predefined_attribute_patch_disables_free_text_configuration(self, frappe, clear_cache):
		enforce_predefined()

		frappe.db.set_single_value.assert_called_once_with("Masters Settings", "allow_dynamic_attributes", 0)
		self.assertIn("set allow_new_values = 0", frappe.db.sql.call_args.args[0])
		clear_cache.assert_called_once_with()

	@patch("srv_erp.masters.setup.ensure_masters_roles")
	@patch("srv_erp.masters.setup.frappe.get_doc")
	@patch("srv_erp.masters.setup.frappe.get_all")
	def test_provision_assigns_requesters_and_manager_approvers(self, get_all, get_doc, _ensure_roles):
		get_all.side_effect = [
			["requester@example.com", "manager.one@example.com", "manager.two@example.com"],
			["manager.one@example.com", "manager.two@example.com"],
		]
		users = {}

		def get_user(_doctype, name):
			users.setdefault(name, MagicMock())
			return users[name]

		get_doc.side_effect = get_user

		result = provision_masters_user_roles()

		self.assertEqual(result, {"requesters": 3, "approvers": 2})
		users["requester@example.com"].add_roles.assert_called_once_with(REQUESTER_ROLE)
		users["manager.one@example.com"].add_roles.assert_called_once_with(REQUESTER_ROLE, APPROVER_ROLE)
		users["manager.two@example.com"].add_roles.assert_called_once_with(REQUESTER_ROLE, APPROVER_ROLE)

	@patch("srv_erp.masters.setup.ensure_masters_roles")
	@patch("srv_erp.masters.setup._", side_effect=lambda message: message)
	@patch("srv_erp.masters.setup.frappe.throw")
	@patch("srv_erp.masters.setup.frappe.get_all")
	def test_provision_requires_two_system_managers(self, get_all, throw, _translate, _ensure_roles):
		get_all.side_effect = [
			["requester@example.com", "manager@example.com"],
			["manager@example.com"],
		]
		throw.side_effect = RuntimeError

		with self.assertRaises(RuntimeError):
			provision_masters_user_roles()

	@patch("srv_erp.masters.setup.clear_settings_cache")
	@patch("srv_erp.masters.setup.provision_masters_user_roles")
	@patch("srv_erp.masters.setup.setup_masters_module")
	@patch("srv_erp.masters.setup.frappe")
	def test_activation_enables_requests_and_disables_legacy_bulk_sync(
		self,
		frappe,
		_setup_module,
		provision_roles,
		_clear_cache,
	):
		settings = MagicMock()
		frappe.get_single.return_value = settings
		provision_roles.return_value = {"requesters": 3, "approvers": 2}

		result = activate_dynamic_item_creation()

		self.assertEqual(result, {"requesters": 3, "approvers": 2})
		self.assertEqual(settings.enable_dynamic_item_requests, 1)
		self.assertEqual(settings.enforce_variant_approval, 1)
		self.assertEqual(settings.allow_bulk_variant_creation, 0)
		self.assertEqual(settings.allow_dynamic_attributes, 0)
		settings.save.assert_called_once_with(ignore_permissions=True)
		frappe.db.set_single_value.assert_called_once_with(
			"SRV Settings", "auto_create_variants_on_brand_update", 0
		)
