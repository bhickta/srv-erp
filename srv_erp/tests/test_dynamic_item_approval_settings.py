from unittest import TestCase
from unittest.mock import patch

from frappe import _dict

from srv_erp.masters.dynamic_item.configuration import (
	get_approver_role,
	is_requester_self_approval_allowed,
)


class TestDynamicItemApprovalSettings(TestCase):
	@patch("srv_erp.masters.dynamic_item.configuration.frappe")
	def test_self_approval_comes_from_srv_settings(self, frappe):
		frappe.get_cached_doc.return_value = _dict(
			allow_dynamic_item_requester_self_approval=1
		)

		self.assertTrue(is_requester_self_approval_allowed())
		frappe.get_cached_doc.assert_called_once_with("SRV Settings")

	@patch("srv_erp.masters.dynamic_item.configuration.get_settings")
	@patch("srv_erp.masters.dynamic_item.configuration.frappe")
	def test_approver_role_can_be_overridden_in_srv_settings(self, frappe, get_settings):
		frappe.get_cached_doc.return_value = _dict(dynamic_item_approver_role="Item Manager")

		self.assertEqual(get_approver_role(), "Item Manager")
		get_settings.assert_not_called()
