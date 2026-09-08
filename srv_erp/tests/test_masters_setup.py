import unittest
from unittest.mock import MagicMock, patch

from srv_erp.masters.dynamic_item.configuration import (
	APPROVER_ROLE,
	REQUESTER_ROLE,
	masters_settings_available,
)
from srv_erp.masters.setup import activate_dynamic_item_creation, provision_masters_user_roles


class TestMastersSetup(unittest.TestCase):
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
		users["manager.one@example.com"].add_roles.assert_called_once_with(
			REQUESTER_ROLE, APPROVER_ROLE
		)
		users["manager.two@example.com"].add_roles.assert_called_once_with(
			REQUESTER_ROLE, APPROVER_ROLE
		)

	@patch("srv_erp.masters.setup.ensure_masters_roles")
	@patch("srv_erp.masters.setup._", side_effect=lambda message: message)
	@patch("srv_erp.masters.setup.frappe.throw")
	@patch("srv_erp.masters.setup.frappe.get_all")
	def test_provision_requires_two_system_managers(
		self, get_all, throw, _translate, _ensure_roles
	):
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
		settings.save.assert_called_once_with(ignore_permissions=True)
		frappe.db.set_single_value.assert_called_once_with(
			"SRV Settings", "auto_create_variants_on_brand_update", 0
		)
