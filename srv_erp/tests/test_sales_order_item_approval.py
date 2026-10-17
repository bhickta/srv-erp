from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from srv_erp.selling.sales_order_item_approval import (
	ALLOW_FIRST_ORDER_SETTING,
	ALLOW_SELF_APPROVAL_SETTING,
	APPROVAL_REQUIRED_FIELD,
	APPROVAL_SUMMARY_FIELD,
	APPROVED_FIELD,
	APPROVER_ROLE_SETTING,
	ENABLE_SETTING,
	ITEM_APPROVAL_FIELD,
	LOOKBACK_MONTHS_SETTING,
	REQUESTER_ROLE,
	WORKFLOW_STATE_FIELD,
	add_sales_order_item_approval_to_boot,
	build_approval_summary,
	customer_has_order_history,
	get_customer_item_history,
	get_items_requiring_approval,
	is_self_approval_allowed,
	mark_items_requiring_approval,
	normalize_sales_order_workflow_state,
	validate_sales_order_item_approval_submission,
	validate_sales_order_item_history,
)
from srv_erp.selling.sales_order_item_approval_setup import (
	ACTION_APPROVE,
	ACTION_CANCEL,
	ACTION_REJECT,
	ACTION_SEND_FOR_APPROVAL,
	STATE_APPROVED,
	STATE_CANCELLED,
	STATE_PENDING,
	STATE_REJECTED,
	backfill_sales_order_workflow_states,
	build_sales_order_item_approval_workflow,
	sync_sales_order_item_approval_workflow,
	upsert_sales_order_item_approval_workflow,
)


class FakeDoc(frappe._dict):
	def is_new(self):
		return bool(self.get("__islocal"))

	def set(self, key, value):
		self[key] = value

	def get_doc_before_save(self):
		return None


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
	def test_cancelled_orders_are_ignored(self, frappe_mock):
		configure_settings(frappe_mock)
		items = [{"item_code": "ITEM-1"}]

		self.assertEqual(
			get_items_requiring_approval(FakeDoc(customer="CUST-1", docstatus=2, items=items)),
			[],
		)
		frappe_mock.db.sql.assert_not_called()

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_history_queries_do_not_reference_is_return(self, frappe_mock):
		"""Sales Order has no `is_return` column; the query must not use it."""
		configure_settings(frappe_mock)
		frappe_mock.db.sql.return_value = []

		get_customer_item_history("CUST-1")
		query = frappe_mock.db.sql.call_args.args[0]
		self.assertNotIn("is_return", query)

		customer_has_order_history("CUST-1")
		exists_filter = frappe_mock.db.exists.call_args.args[1]
		self.assertNotIn("is_return", exists_filter)

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

	@patch("srv_erp.selling.sales_order_item_approval._", lambda message, *a, **k: message)
	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_validate_marks_child_rows_and_sets_derived_fields(self, frappe_mock):
		configure_settings(frappe_mock)
		frappe_mock.db.sql.return_value = [("ITEM-1",)]
		frappe_mock.bold.side_effect = lambda value: value
		frappe_mock.as_unicode.side_effect = lambda value: value
		doc = FakeDoc(
			__islocal=1,
			customer="CUST-1",
			docstatus=0,
			items=[{"item_code": "ITEM-1"}, {"item_code": "ITEM-2"}],
		)

		validate_sales_order_item_history(doc)

		# Derived parent scalar + approval flag.
		self.assertEqual(doc[APPROVAL_REQUIRED_FIELD], 1)
		self.assertEqual(doc[APPROVED_FIELD], 0)
		# Per-row source of truth.
		self.assertEqual(doc["items"][0][ITEM_APPROVAL_FIELD], 0)
		self.assertEqual(doc["items"][1][ITEM_APPROVAL_FIELD], 1)
		# Display-only summary mentions the new item.
		self.assertIn("ITEM-2", doc[APPROVAL_SUMMARY_FIELD])

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_validate_clears_flags_when_all_items_known(self, frappe_mock):
		configure_settings(frappe_mock)
		frappe_mock.db.sql.return_value = [("ITEM-1",)]
		frappe_mock.bold.side_effect = lambda value: value
		frappe_mock.as_unicode.side_effect = lambda value: value
		doc = FakeDoc(customer="CUST-1", docstatus=0, items=[{"item_code": "ITEM-1"}])

		validate_sales_order_item_history(doc)

		self.assertEqual(doc[APPROVAL_REQUIRED_FIELD], 0)
		self.assertEqual(doc["items"][0][ITEM_APPROVAL_FIELD], 0)
		self.assertEqual(doc[APPROVAL_SUMMARY_FIELD], "")

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_mark_items_requires_approval_sets_row_flag(self, frappe_mock):
		configure_settings(frappe_mock)
		frappe_mock.db.sql.return_value = [("ITEM-1",)]
		doc = FakeDoc(
			customer="CUST-1",
			docstatus=0,
			items=[{"item_code": "ITEM-1"}, {"item_code": "ITEM-NEW"}],
		)

		required = mark_items_requiring_approval(doc)

		self.assertEqual(required, ["ITEM-NEW"])
		self.assertEqual(doc["items"][0][ITEM_APPROVAL_FIELD], 0)
		self.assertEqual(doc["items"][1][ITEM_APPROVAL_FIELD], 1)

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_mark_items_clears_rows_when_approval_not_applicable(self, frappe_mock):
		configure_settings(frappe_mock, enabled=0)
		doc = FakeDoc(
			customer="CUST-1",
			docstatus=0,
			items=[{"item_code": "ITEM-1", ITEM_APPROVAL_FIELD: 1}],
		)

		self.assertEqual(mark_items_requiring_approval(doc), [])
		self.assertEqual(doc["items"][0][ITEM_APPROVAL_FIELD], 0)

	def test_build_approval_summary_is_empty_without_items(self):
		self.assertEqual(build_approval_summary([]), "")

	@patch("srv_erp.selling.sales_order_item_approval._", lambda message, *a, **k: message)
	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_build_approval_summary_includes_item_codes(self, frappe_mock):
		frappe_mock.bold.side_effect = lambda value: value
		frappe_mock.as_unicode.side_effect = lambda value: value

		summary = build_approval_summary(["ITEM-A", "ITEM-B"])

		self.assertIn("ITEM-A", summary)
		self.assertIn("ITEM-B", summary)

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

		states = {s["state"]: s for s in workflow["states"]}
		# The requester owns pending and rejected orders; the approver owns the
		# approved and cancelled states.
		self.assertEqual(states[STATE_PENDING]["allow_edit"], REQUESTER_ROLE)
		self.assertEqual(states[STATE_REJECTED]["allow_edit"], REQUESTER_ROLE)
		for state in (STATE_APPROVED, STATE_CANCELLED):
			self.assertEqual(states[state]["allow_edit"], "Special Approver")

		for action in (ACTION_APPROVE, ACTION_REJECT, ACTION_CANCEL):
			transition = next(t for t in workflow["transitions"] if t["action"] == action)
			self.assertEqual(transition["allowed"], "Special Approver")

	def test_approval_transitions_do_not_allow_self_approval(self):
		workflow = build_sales_order_item_approval_workflow("Sales Manager")

		for action in (ACTION_APPROVE, ACTION_REJECT):
			transition = next(t for t in workflow["transitions"] if t["action"] == action)
			self.assertEqual(transition["allow_self_approval"], 0)

	def test_workflow_is_single_unconditional_flow(self):
		"""Every order enters at Pending; which items are new is informational."""
		workflow = build_sales_order_item_approval_workflow("Sales Manager")

		self.assertEqual(workflow["states"][0]["state"], STATE_PENDING)

		transitions = {(t["state"], t["action"]): t for t in workflow["transitions"]}
		self.assertEqual(
			set(transitions),
			{
				(STATE_PENDING, ACTION_APPROVE),
				(STATE_PENDING, ACTION_REJECT),
				(STATE_REJECTED, ACTION_SEND_FOR_APPROVAL),
				(STATE_APPROVED, ACTION_CANCEL),
			},
		)
		for transition in workflow["transitions"]:
			self.assertFalse(transition.get("condition"))

	def test_approved_state_submits_and_sets_approval_flag(self):
		workflow = build_sales_order_item_approval_workflow("Sales Manager")
		approved = next(s for s in workflow["states"] if s["state"] == STATE_APPROVED)

		self.assertEqual(approved["doc_status"], "1")
		self.assertEqual(approved["update_field"], APPROVED_FIELD)
		self.assertEqual(approved["update_value"], "1")

	def test_workflow_preserves_status_display(self):
		workflow = build_sales_order_item_approval_workflow("Sales Manager")

		self.assertEqual(workflow["workflow_state_field"], "workflow_state")
		self.assertEqual(workflow["override_status"], 0)
		self.assertEqual(workflow["document_type"], "Sales Order")

	def test_submitted_and_inactive_states_defer_to_status_indicator(self):
		"""Approved orders fall through to the list indicator so a Closed order
		shows "Closed" while an open one shows "Approved".

		Pending/Rejected must NOT avoid the override, otherwise they would fall
		through to the draft indicator and render "Draft" instead of their
		workflow state.
		"""
		workflow = build_sales_order_item_approval_workflow("Sales Manager")
		avoid = {
			state["state"]
			for state in workflow["states"]
			if state.get("avoid_status_override")
		}

		self.assertEqual(avoid, {STATE_APPROVED, STATE_CANCELLED})

		pending = next(s for s in workflow["states"] if s["state"] == STATE_PENDING)
		rejected = next(s for s in workflow["states"] if s["state"] == STATE_REJECTED)
		self.assertFalse(pending.get("avoid_status_override"))
		self.assertFalse(rejected.get("avoid_status_override"))

	def test_approved_order_can_be_cancelled_via_workflow(self):
		"""A submitted order has no native Cancel button once a cancelling state
		exists, so the workflow must expose a Cancel action from Approved."""
		workflow = build_sales_order_item_approval_workflow("Sales Manager")
		transition = next(
			t
			for t in workflow["transitions"]
			if t["state"] == STATE_APPROVED and t["action"] == ACTION_CANCEL
		)

		self.assertEqual(transition["next_state"], STATE_CANCELLED)

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

		first_call = setup_frappe.db.set_value.call_args_list[0]
		self.assertEqual(first_call.args[0], "Workflow")
		self.assertEqual(first_call.args[2], "is_active")
		self.assertEqual(first_call.args[3], 0)

	@patch("srv_erp.selling.sales_order_item_approval_setup.frappe")
	def test_upsert_updates_existing_workflow_in_place(self, frappe_mock):
		frappe_mock.db.exists.return_value = True
		workflow_mock = self.persisted_workflow()
		workflow_mock.states[0].allow_edit = "Old Requester"
		frappe_mock.get_doc.return_value = workflow_mock

		upsert_sales_order_item_approval_workflow("Sales Manager")

		self.assertEqual(workflow_mock.states, [])
		self.assertEqual(workflow_mock.transitions, [])
		self.assertTrue(workflow_mock.append.called)
		workflow_mock.save.assert_called_once_with(ignore_permissions=True)

	@staticmethod
	def persisted_workflow():
		workflow = FakeDoc(build_sales_order_item_approval_workflow("Sales Manager"))
		workflow.states = [
			FakeDoc(
				{
					"name": f"state-{index}",
					"idx": index,
					"is_optional_state": 0,
					"avoid_status_override": 0,
					"send_email": 1,
					"update_field": None,
					"update_value": None,
					"message": None,
					"next_action_email_template": None,
					**row,
				}
			)
			for index, row in enumerate(workflow.states, 1)
		]
		workflow.transitions = [
			FakeDoc(
				{
					"name": f"transition-{index}",
					"idx": index,
					"condition": None,
					"send_email_to_creator": 0,
					**row,
				}
			)
			for index, row in enumerate(workflow.transitions, 1)
		]
		workflow.save = MagicMock()
		workflow.append = MagicMock()
		return workflow

	@patch("srv_erp.selling.sales_order_item_approval_setup.frappe")
	def test_repeated_provisioning_does_not_save_matching_workflow(self, frappe_mock):
		workflow = self.persisted_workflow()
		frappe_mock.db.exists.side_effect = lambda doctype, name: isinstance(name, str)
		frappe_mock.get_doc.return_value = workflow
		original_states = workflow.states
		original_transitions = workflow.transitions
		workflow.save.side_effect = AssertionError("Workflow save would run Sales Order backfill")

		upsert_sales_order_item_approval_workflow("Sales Manager")
		upsert_sales_order_item_approval_workflow("Sales Manager")

		workflow.save.assert_not_called()
		workflow.append.assert_not_called()
		self.assertIs(workflow.states, original_states)
		self.assertIs(workflow.transitions, original_transitions)

	@patch("srv_erp.selling.sales_order_item_approval_setup.frappe")
	def test_checks_normalize_database_strings(self, frappe_mock):
		workflow = self.persisted_workflow()
		workflow.is_active = True
		for row in [workflow, *workflow.states, *workflow.transitions]:
			for fieldname, value in row.items():
				if isinstance(value, int) and not isinstance(value, bool):
					row[fieldname] = str(value)
		frappe_mock.db.exists.side_effect = lambda doctype, name: isinstance(name, str)
		frappe_mock.get_doc.return_value = workflow

		upsert_sales_order_item_approval_workflow("Sales Manager")

		workflow.save.assert_not_called()

	@patch("srv_erp.selling.sales_order_item_approval_setup.frappe")
	def test_matching_workflow_still_saves_to_deactivate_competing_workflows(self, frappe_mock):
		workflow = self.persisted_workflow()
		frappe_mock.db.exists.return_value = True
		frappe_mock.get_doc.return_value = workflow

		upsert_sales_order_item_approval_workflow("Sales Manager")

		workflow.save.assert_called_once_with(ignore_permissions=True)
		filters = frappe_mock.db.exists.call_args.args[1]
		self.assertEqual(filters["document_type"], "Sales Order")
		self.assertEqual(filters["is_active"], 1)
		self.assertEqual(filters["name"], ["!=", workflow.workflow_name])

	@patch("srv_erp.selling.sales_order_item_approval_setup.frappe")
	def test_matching_workflow_still_saves_to_recreate_missing_state_field(self, frappe_mock):
		workflow = self.persisted_workflow()
		frappe_mock.db.exists.side_effect = lambda doctype, name: isinstance(name, str)
		frappe_mock.get_doc.return_value = workflow
		frappe_mock.get_meta.return_value.get_field.return_value = None

		upsert_sales_order_item_approval_workflow("Sales Manager")

		workflow.save.assert_called_once_with(ignore_permissions=True)
		frappe_mock.get_meta.assert_called_once_with("Sales Order")
		frappe_mock.get_meta.return_value.get_field.assert_called_once_with(WORKFLOW_STATE_FIELD)

	@patch("srv_erp.selling.sales_order_item_approval_setup.frappe")
	def test_provisioning_still_reconciles_changed_workflow(self, frappe_mock):
		changes = {
			"inactive": lambda doc: doc.set("is_active", 0),
			"indicator": lambda doc: doc.set("override_status", 1),
			"state field": lambda doc: doc.set("workflow_state_field", "old_state"),
			"optional state": lambda doc: doc.states[0].set("is_optional_state", 1),
			"state email": lambda doc: doc.states[0].set("send_email", 0),
			"state update": lambda doc: doc.states[0].set("update_value", "1"),
			"legacy condition": lambda doc: doc.transitions[0].set("condition", "doc.total > 100"),
			"approval permission": lambda doc: doc.transitions[0].set("allow_self_approval", 1),
			"transition role": lambda doc: doc.transitions[0].set("allowed", "Old Approver"),
			"state ordering": lambda doc: doc.states.reverse(),
			"transition ordering": lambda doc: doc.transitions.reverse(),
			"extra state": lambda doc: doc.states.append(FakeDoc(state="Legacy")),
			"missing transition": lambda doc: doc.transitions.pop(),
		}
		frappe_mock.db.exists.return_value = True
		for description, change in changes.items():
			with self.subTest(description=description):
				workflow = self.persisted_workflow()
				change(workflow)
				frappe_mock.get_doc.return_value = workflow

				upsert_sales_order_item_approval_workflow("Sales Manager")

				workflow.save.assert_called_once_with(ignore_permissions=True)

	@patch("srv_erp.selling.sales_order_item_approval_setup.frappe")
	def test_setting_changes_still_save_workflow(self, frappe_mock):
		frappe_mock.db.exists.return_value = True
		for role, self_approval in (("New Approver", False), ("Sales Manager", True)):
			with self.subTest(role=role, self_approval=self_approval):
				workflow = self.persisted_workflow()
				frappe_mock.get_doc.return_value = workflow

				upsert_sales_order_item_approval_workflow(role, self_approval)

				workflow.save.assert_called_once_with(ignore_permissions=True)

	@patch("srv_erp.selling.sales_order_item_approval_setup.frappe")
	def test_upsert_inserts_when_missing(self, frappe_mock):
		frappe_mock.db.exists.return_value = False

		upsert_sales_order_item_approval_workflow("Sales Manager")

		payload = frappe_mock.get_doc.call_args.args[0]
		self.assertEqual(payload["doctype"], "Workflow")
		frappe_mock.get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)

	@patch("srv_erp.selling.sales_order_item_approval_setup.is_enabled", return_value=True)
	@patch("srv_erp.selling.sales_order_item_approval_setup.frappe")
	def test_backfill_skips_updates_when_no_orders_need_repair(self, frappe_mock, enabled):
		frappe_mock.db.has_column.return_value = True
		frappe_mock.db.sql.return_value = []

		backfill_sales_order_workflow_states()

		self.assertEqual(frappe_mock.db.sql.call_count, 2)
		for query in frappe_mock.db.sql.call_args_list:
			self.assertTrue(query.args[0].lstrip().startswith("SELECT"))

	@patch("srv_erp.selling.sales_order_item_approval_setup.is_enabled", return_value=True)
	@patch("srv_erp.selling.sales_order_item_approval_setup.frappe")
	def test_backfill_preserves_repairs_for_existing_orders(self, frappe_mock, enabled):
		frappe_mock.db.has_column.return_value = True
		frappe_mock.db.sql.side_effect = [[("SO-1",)], [], [("SO-2",)], []]

		backfill_sales_order_workflow_states()

		queries = frappe_mock.db.sql.call_args_list
		self.assertEqual(len(queries), 4)
		self.assertIn("WHERE IFNULL(workflow_state, '') = ''", queries[1].args[0])
		self.assertEqual(queries[1].args[1]["approved"], STATE_APPROVED)
		self.assertIn(f"WHERE docstatus = 1 AND IFNULL({APPROVED_FIELD}, 0) = 0", queries[3].args[0])

	@patch("srv_erp.selling.sales_order_item_approval_setup.is_enabled", return_value=True)
	@patch("srv_erp.selling.sales_order_item_approval_setup.frappe")
	def test_backfill_checks_each_repair_independently(self, frappe_mock, enabled):
		frappe_mock.db.has_column.return_value = True
		for responses, expected_update in (
			([[("SO-1",)], [], []], "SET workflow_state"),
			([[], [("SO-2",)], []], f"SET {APPROVED_FIELD}"),
		):
			with self.subTest(expected_update=expected_update):
				frappe_mock.db.sql.reset_mock()
				frappe_mock.db.sql.side_effect = responses

				backfill_sales_order_workflow_states()

				updates = [
					call.args[0] for call in frappe_mock.db.sql.call_args_list
					if call.args[0].lstrip().startswith("UPDATE")
				]
				self.assertEqual(len(updates), 1)
				self.assertIn(expected_update, updates[0])

class TestSalesOrderWorkflowStateNormalization(TestCase):
	NEW_STATE_ROWS = (
		SimpleNamespace(state=STATE_PENDING, doc_status="0"),
		SimpleNamespace(state=STATE_APPROVED, doc_status="1"),
		SimpleNamespace(state=STATE_REJECTED, doc_status="0"),
		SimpleNamespace(state=STATE_CANCELLED, doc_status="2"),
	)

	@staticmethod
	def _active_workflow(state_rows):
		return SimpleNamespace(states=state_rows)

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_unknown_state_resets_to_the_state_for_docstatus(self, frappe_mock):
		frappe_mock.db.get_value.return_value = "Sales Order Item Approval"
		frappe_mock.get_doc.return_value = self._active_workflow(self.NEW_STATE_ROWS)
		doc = FakeDoc(__islocal=1, docstatus=0, **{WORKFLOW_STATE_FIELD: "Draft"})

		normalize_sales_order_workflow_state(doc)

		self.assertEqual(doc[WORKFLOW_STATE_FIELD], STATE_PENDING)

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_cancelled_doc_with_legacy_typo_state_maps_to_cancelled(self, frappe_mock):
		frappe_mock.db.get_value.return_value = "Sales Order Item Approval"
		frappe_mock.get_doc.return_value = self._active_workflow(self.NEW_STATE_ROWS)
		doc = FakeDoc(docstatus=2, **{WORKFLOW_STATE_FIELD: "Cancle"})

		normalize_sales_order_workflow_state(doc)

		self.assertEqual(doc[WORKFLOW_STATE_FIELD], STATE_CANCELLED)

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_valid_state_is_left_untouched(self, frappe_mock):
		frappe_mock.db.get_value.return_value = "Sales Order Item Approval"
		frappe_mock.get_doc.return_value = self._active_workflow(self.NEW_STATE_ROWS)
		doc = FakeDoc(__islocal=1, docstatus=0, **{WORKFLOW_STATE_FIELD: STATE_PENDING})

		normalize_sales_order_workflow_state(doc)

		self.assertEqual(doc[WORKFLOW_STATE_FIELD], STATE_PENDING)

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_normalization_mirrors_state_into_doc_before_save(self, frappe_mock):
		frappe_mock.db.get_value.return_value = "Sales Order Item Approval"
		frappe_mock.get_doc.return_value = self._active_workflow(self.NEW_STATE_ROWS)
		previous = FakeDoc(docstatus=2, **{WORKFLOW_STATE_FIELD: "Cancle"})

		class DocWithPrevious(FakeDoc):
			def get_doc_before_save(self):
				return previous

		doc = DocWithPrevious(docstatus=2, **{WORKFLOW_STATE_FIELD: "Cancle"})

		normalize_sales_order_workflow_state(doc)

		self.assertEqual(doc[WORKFLOW_STATE_FIELD], STATE_CANCELLED)
		self.assertEqual(previous[WORKFLOW_STATE_FIELD], STATE_CANCELLED)

	def test_workflow_only_has_canonical_states(self):
		workflow = build_sales_order_item_approval_workflow("Sales Manager")
		state_names = {s["state"] for s in workflow["states"]}

		self.assertEqual(
			state_names, {STATE_PENDING, STATE_APPROVED, STATE_REJECTED, STATE_CANCELLED}
		)


class TestSalesOrderItemSelfApproval(TestCase):
	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_is_self_approval_allowed_reads_setting(self, frappe_mock):
		frappe_mock.db.get_single_value.side_effect = lambda doctype, field: {
			ALLOW_SELF_APPROVAL_SETTING: 1
		}.get(field)

		self.assertTrue(is_self_approval_allowed())

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_workflow_builder_sets_self_approval_on_approval_transitions(self, frappe_mock):
		on = build_sales_order_item_approval_workflow("Sales Manager", allow_self_approval=True)
		off = build_sales_order_item_approval_workflow("Sales Manager", allow_self_approval=False)

		for workflow, expected in ((on, 1), (off, 0)):
			for action in (ACTION_APPROVE, ACTION_REJECT, ACTION_CANCEL):
				transitions = [t for t in workflow["transitions"] if t["action"] == action]
				self.assertTrue(transitions)
				for transition in transitions:
					self.assertEqual(transition["allow_self_approval"], expected)

	@patch("srv_erp.selling.sales_order_item_approval.frappe")
	def test_boot_exposes_approval_config(self, frappe_mock):
		frappe_mock.db.get_single_value.side_effect = lambda doctype, field: {
			ENABLE_SETTING: 1,
			ALLOW_SELF_APPROVAL_SETTING: 1,
			APPROVER_ROLE_SETTING: "Sales Manager",
		}.get(field)
		bootinfo = frappe._dict()

		add_sales_order_item_approval_to_boot(bootinfo)

		config = bootinfo.srv_erp_sales_order_item_approval
		self.assertTrue(config["enabled"])
		self.assertTrue(config["allow_self_approval"])
		self.assertEqual(config["approver_role"], "Sales Manager")
