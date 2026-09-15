from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from srv_erp.masters.dynamic_item.assignments import (
	assign_request_to_approvers,
	close_approval_assignments,
)


class TestDynamicItemAssignments(TestCase):
	@patch("frappe.desk.form.assign_to._add")
	@patch("srv_erp.masters.dynamic_item.assignments.is_requester_self_approval_allowed")
	@patch("srv_erp.masters.dynamic_item.assignments.get_approver_users")
	def test_assignment_uses_supported_internal_api(self, get_approvers, self_approval, add):
		self_approval.return_value = False
		get_approvers.return_value = ["approver@example.com"]
		request = SimpleNamespace(
			doctype="Dynamic Item Request",
			name="DIR-TEST-0001",
			requested_by="requester@example.com",
			request_type="Create Variant",
			template_item="ITEM-TEMPLATE",
		)

		with patch("srv_erp.masters.dynamic_item.assignments._", lambda text: text):
			assign_request_to_approvers(request)

		add.assert_called_once()
		get_approvers.assert_called_once_with(exclude_user="requester@example.com")
		self.assertTrue(add.call_args.kwargs["ignore_permissions"])
		self.assertEqual(add.call_args.args[0]["assign_to"], ["approver@example.com"])

	@patch("frappe.desk.form.assign_to._add")
	@patch("srv_erp.masters.dynamic_item.assignments.is_requester_self_approval_allowed")
	@patch("srv_erp.masters.dynamic_item.assignments.get_approver_users")
	def test_self_approval_includes_requester_as_approver(self, get_approvers, self_approval, add):
		self_approval.return_value = True
		get_approvers.return_value = ["requester@example.com"]
		request = SimpleNamespace(
			doctype="Dynamic Item Request",
			name="DIR-TEST-0001",
			requested_by="requester@example.com",
			request_type="Create Variant",
			template_item="ITEM-TEMPLATE",
		)

		with patch("srv_erp.masters.dynamic_item.assignments._", lambda text: text):
			assign_request_to_approvers(request)

		get_approvers.assert_called_once_with(exclude_user=None)
		self.assertEqual(add.call_args.args[0]["assign_to"], ["requester@example.com"])

	@patch("frappe.desk.form.assign_to._remove")
	@patch("srv_erp.masters.dynamic_item.assignments.frappe")
	def test_assignment_cleanup_uses_supported_internal_api(self, frappe, remove):
		frappe.get_all.return_value = ["approver@example.com"]
		request = SimpleNamespace(doctype="Dynamic Item Request", name="DIR-TEST-0001")

		close_approval_assignments(request)

		remove.assert_called_once_with(
			"Dynamic Item Request",
			"DIR-TEST-0001",
			"approver@example.com",
			ignore_permissions=True,
		)
