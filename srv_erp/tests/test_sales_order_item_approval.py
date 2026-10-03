from unittest import TestCase
from unittest.mock import patch

import frappe

from srv_erp.selling.sales_order_item_approval import (
	ALLOW_FIRST_ORDER_SETTING,
	APPROVAL_REQUIRED_FIELD,
	APPROVED_FIELD,
	APPROVER_ROLE_SETTING,
	ENABLE_SETTING,
	LOOKBACK_MONTHS_SETTING,
	UNAPPROVED_ITEMS_FIELD,
	get_customer_item_history,
	get_items_requiring_approval,
	validate_sales_order_item_approval_submission,
	validate_sales_order_item_history,
)
from srv_erp.selling.sales_order_item_approval_setup import (
	ACTION_APPROVE,
	ACTION_REJECT,
	ACTION_SEND_FOR_APPROVAL,
	ACTION_SUBMIT,
	STATE_APPROVED,
	STATE_CANCELLED,
	STATE_DRAFT,
	STATE_PENDING,
	STATE_REJECTED,
	build_sales_order_item_approval_workflow,
	sync_sales_order_item_approval_workflow,
	upsert_sales_order_item_approval_workflow,
)


class FakeDoc(frappe._dict):
	def is_new(self):
		return bool(self.get("__islocal"))

	def set(self, key, value):
		self[key] = value


def configure_settings(frappe, *, enabled=1, lookback=12, allow_first=0, approver="Sales Manager"):
	values = {
		ENABLE_SETTING: enabled,
		LOOKBACK_MONTHS_SETTING: lookback,
		ALLOW_FIRST_ORDER_SETTING: allow_first,
		APPROVER_ROLE_SETTING: approver,
	}
	frappe.db.get_single_value.side_effect = lambda doctype, field: values.get(field)


class TestSalesOrderItemApproval(TestCase):
	def setUp(self):
		nowdate = patch(
			"srv_erp.selling.sales_order_item_approval.nowdate", return_value="2026-01-01"
		)
		add_months = patch(
			"srv_erp.selling.sales_order_item_approval.add_months", return_value="2025-07-01"
		)
		nowdate.start()
		add_months.start()
		self.addCleanup(nowdate.stop)
		self.addCleanup(add_months.stop)

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_disabled_feature_requires_no_approval(self, frappe_mock):
		configure_settings(frappe_mock, enabled=0)
		doc = FakeDoc(customer="CUST-1", docstatus=0, items=[{"item_code": "ITEM-1"}])

		self.assertEqual(get_items_requiring_approval(doc), [])
		frappe_mock.db.sql.assert_not_called()

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_returns_and_cancelled_orders_are_ignored(self, frappe_mock):
		configure_settings(frappe_mock)
		items = [{"item_code": "ITEM-1"}]

		self.assertEqual(
			get_items_requiring_approval(FakeDoc(customer="CUST-1", docstatus=0, is_return=1, items=items)),
			[],
		)
		self.assertEqual(
			get_items_requiring_approval(FakeDoc(customer="CUST-1", docstatus=2, items=items)),
			[],
		)
		frappe_mock.db.sql.assert_not_called()

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_missing_customer_is_ignored(self, frappe_mock):
		configure_settings(frappe_mock)
		doc = FakeDoc(docstatus=0, items=[{"item_code": "ITEM-1"}])

		self.assertEqual(get_items_requiring_approval(doc), [])

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_only_items_outside_history_require_approval(self, frappe_mock):
		configure_settings(frappe_mock)
		frappe_mock.db.exists.return_value = True
		frappe_mock.db.sql.return_value = [("ITEM-1",), ("ITEM-2",)]
		doc = FakeDoc(
			customer="CUST-1",
			docstatus=0,
			items=[
				{"item_code": "ITEM-1"},
				{"item_code": "ITEM-3"},
				{"item_code": "ITEM-3"},
				{"item_code": "ITEM-2"},
			],
		)

		self.assertEqual(get_items_requiring_approval(doc), ["ITEM-3"])

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_unknown_customer_requires_approval_when_first_order_not_allowed(self, frappe_mock):
		configure_settings(frappe_mock, allow_first=0)
		frappe_mock.db.sql.return_value = []
		doc = FakeDoc(customer="NEW-CUST", docstatus=0, items=[{"item_code": "ITEM-1"}])

		self.assertEqual(get_items_requiring_approval(doc), ["ITEM-1"])

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_first_order_allowed_when_customer_has_no_history(self, frappe_mock):
		configure_settings(frappe_mock, allow_first=1)
		frappe_mock.db.exists.return_value = False
		doc = FakeDoc(customer="NEW-CUST", docstatus=0, items=[{"item_code": "ITEM-1"}])

		self.assertEqual(get_items_requiring_approval(doc), [])
		frappe_mock.db.sql.assert_not_called()

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_all_time_history_has_no_date_cutoff(self, frappe_mock):
		configure_settings(frappe_mock, lookback=0)
		frappe_mock.db.sql.return_value = []

		get_customer_item_history("CUST-1")

		params = frappe_mock.db.sql.call_args.args[1]
		self.assertNotIn("cutoff", params)

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_lookback_adds_date_cutoff(self, frappe_mock):
		configure_settings(frappe_mock, lookback=6)
		frappe_mock.db.sql.return_value = []

		get_customer_item_history("CUST-1")

		params = frappe_mock.db.sql.call_args.args[1]
		self.assertIn("cutoff", params)

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_validate_sets_flags_and_resets_stale_approval_on_new_docs(self, frappe_mock):
		configure_settings(frappe_mock)
		frappe_mock.db.sql.return_value = [("ITEM-1",)]
		doc = FakeDoc(
			__islocal=1,
			customer="CUST-1",
			docstatus=0,
			items=[{"item_code": "ITEM-1"}, {"item_code": "ITEM-2"}],
		)

		validate_sales_order_item_history(doc)

		self.assertEqual(doc[APPROVAL_REQUIRED_FIELD], 1)
		self.assertEqual(doc[UNAPPROVED_ITEMS_FIELD], "ITEM-2")
		self.assertEqual(doc[APPROVED_FIELD], 0)

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_validate_clears_flags_when_all_items_known(self, frappe_mock):
		configure_settings(frappe_mock)
		frappe_mock.db.sql.return_value = [("ITEM-1",)]
		doc = FakeDoc(customer="CUST-1", docstatus=0, items=[{"item_code": "ITEM-1"}])

		validate_sales_order_item_history(doc)

		self.assertEqual(doc[APPROVAL_REQUIRED_FIELD], 0)
		self.assertEqual(doc[UNAPPROVED_ITEMS_FIELD], "")

	@patch("srv_erp.selling.sales_order_item_approval._", lambda message, *a, **k: message)
	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_submission_blocked_without_approval(self, frappe_mock):
		configure_settings(frappe_mock)
		frappe_mock.db.sql.return_value = []
		frappe_mock.bold.side_effect = lambda value: value
		frappe_mock.throw.side_effect = frappe.ValidationError
		doc = FakeDoc(customer="CUST-1", docstatus=0, items=[{"item_code": "ITEM-1"}])

		with self.assertRaises(frappe.ValidationError):
			validate_sales_order_item_approval_submission(doc)

		frappe_mock.throw.assert_called_once()

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_submission_allowed_with_approval(self, frappe_mock):
		configure_settings(frappe_mock)
		frappe_mock.db.sql.return_value = []
		doc = FakeDoc(
			customer="CUST-1",
			docstatus=0,
			items=[{"item_code": "ITEM-1"}],
			**{APPROVED_FIELD: 1},
		)

		validate_sales_order_item_approval_submission(doc)

		frappe_mock.throw.assert_not_called()

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_submission_allowed_when_no_new_items(self, frappe_mock):
		configure_settings(frappe_mock)
		frappe_mock.db.sql.return_value = [("ITEM-1",)]
		doc = FakeDoc(customer="CUST-1", docstatus=0, items=[{"item_code": "ITEM-1"}])

		validate_sales_order_item_approval_submission(doc)

		frappe_mock.throw.assert_not_called()


class TestSalesOrderItemApprovalWorkflowDefinition(TestCase):
	def test_workflow_uses_configured_approver_role(self):
		workflow = build_sales_order_item_approval_workflow("Special Approver")

		self.assertTrue(all(state["allow_edit"] == "All" for state in workflow["states"]))

		for action in (ACTION_APPROVE, ACTION_REJECT):
			transition = next(t for t in workflow["transitions"] if t["action"] == action)
			self.assertEqual(transition["allowed"], "Special Approver")

	def test_approval_transitions_do_not_allow_self_approval(self):
		workflow = build_sales_order_item_approval_workflow("Sales Manager")

		for action in (ACTION_APPROVE, ACTION_REJECT):
			transition = next(t for t in workflow["transitions"] if t["action"] == action)
			self.assertEqual(transition["allow_self_approval"], 0)

	def test_submit_and_approval_conditions_gate_on_required_flag(self):
		workflow = build_sales_order_item_approval_workflow("Sales Manager")
		transitions = {(t["state"], t["action"]): t for t in workflow["transitions"]}

		submit = transitions[(STATE_DRAFT, ACTION_SUBMIT)]
		self.assertEqual(submit["next_state"], STATE_APPROVED)
		self.assertIn(f"{APPROVAL_REQUIRED_FIELD} != 1", submit["condition"])

		send = transitions[(STATE_DRAFT, ACTION_SEND_FOR_APPROVAL)]
		self.assertEqual(send["next_state"], STATE_PENDING)
		self.assertIn(f"{APPROVAL_REQUIRED_FIELD} == 1", send["condition"])

	def test_approved_state_submits_and_sets_approval_flag(self):
		workflow = build_sales_order_item_approval_workflow("Sales Manager")
		approved = next(s for s in workflow["states"] if s["state"] == STATE_APPROVED)

		self.assertEqual(approved["doc_status"], "1")
		self.assertEqual(approved["update_field"], APPROVED_FIELD)
		self.assertEqual(approved["update_value"], "1")

	def test_workflow_preserves_status_display(self):
		workflow = build_sales_order_item_approval_workflow("Sales Manager")

		self.assertEqual(workflow["workflow_state_field"], "workflow_state")
		self.assertEqual(workflow["override_status"], 1)
		self.assertEqual(workflow["document_type"], "Sales Order")

	def test_submitted_and_inactive_states_defer_to_status_indicator(self):
		"""Submitted/Closed orders must fall back to the list indicator.

		Otherwise a Closed order that is in the Approved workflow state would
		render "Approved" in the list view instead of "Closed".
		"""
		workflow = build_sales_order_item_approval_workflow("Sales Manager")
		avoid = {
			state["state"]
			for state in workflow["states"]
			if state.get("avoid_status_override")
		}

		self.assertEqual(avoid, {STATE_DRAFT, STATE_APPROVED, STATE_CANCELLED})

		pending = next(s for s in workflow["states"] if s["state"] == STATE_PENDING)
		rejected = next(s for s in workflow["states"] if s["state"] == STATE_REJECTED)
		self.assertFalse(pending.get("avoid_status_override"))
		self.assertFalse(rejected.get("avoid_status_override"))

	def test_rejected_order_can_be_resubmitted_for_approval(self):
		workflow = build_sales_order_item_approval_workflow("Sales Manager")
		transition = next(
			t
			for t in workflow["transitions"]
			if t["state"] == STATE_REJECTED and t["action"] == ACTION_SEND_FOR_APPROVAL
		)

		self.assertEqual(transition["next_state"], STATE_PENDING)


class TestSalesOrderItemApprovalProvisioning(TestCase):
	@patch("srv_erp.selling.sales_order_item_approval_setup.frappe")
	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_sync_creates_workflow_when_enabled(self, core_frappe, setup_frappe):
		core_frappe.db.get_single_value.side_effect = lambda doctype, field: {
			ENABLE_SETTING: 1,
			APPROVER_ROLE_SETTING: "Sales Manager",
		}.get(field)
		setup_frappe.db.exists.return_value = False

		sync_sales_order_item_approval_workflow()

		inserted_doctypes = [
			call.args[0].get("doctype") for call in setup_frappe.get_doc.call_args_list
		]
		self.assertIn("Workflow State", inserted_doctypes)
		self.assertIn("Workflow Action Master", inserted_doctypes)
		self.assertIn("Workflow", inserted_doctypes)

	@patch("srv_erp.selling.sales_order_item_approval_setup.frappe")
	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_sync_deactivates_workflow_when_disabled(self, core_frappe, setup_frappe):
		core_frappe.db.get_single_value.side_effect = lambda doctype, field: {
			ENABLE_SETTING: 0,
		}.get(field)
		setup_frappe.db.exists.return_value = True

		sync_sales_order_item_approval_workflow()

		setup_frappe.db.set_value.assert_called_once()
		self.assertEqual(setup_frappe.db.set_value.call_args.args[2], "is_active")
		self.assertEqual(setup_frappe.db.set_value.call_args.args[3], 0)

	@patch("srv_erp.selling.sales_order_item_approval_setup.frappe")
	def test_upsert_updates_existing_workflow_in_place(self, frappe_mock):
		frappe_mock.db.exists.return_value = True
		workflow_mock = frappe_mock.get_doc.return_value

		upsert_sales_order_item_approval_workflow("Sales Manager")

		self.assertEqual(workflow_mock.states, [])
		self.assertEqual(workflow_mock.transitions, [])
		self.assertTrue(workflow_mock.append.called)
		workflow_mock.save.assert_called_once_with(ignore_permissions=True)

	@patch("srv_erp.selling.sales_order_item_approval_setup.frappe")
	def test_upsert_inserts_when_missing(self, frappe_mock):
		frappe_mock.db.exists.return_value = False

		upsert_sales_order_item_approval_workflow("Sales Manager")

		payload = frappe_mock.get_doc.call_args.args[0]
		self.assertEqual(payload["doctype"], "Workflow")
		frappe_mock.get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)
