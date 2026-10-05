from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from srv_erp.selling.sales_order_item_approval import (
	ACTION_APPROVE,
	ACTION_CANCEL,
	ACTION_REJECT,
	ACTION_SEND_FOR_APPROVAL,
	ALLOW_FIRST_ORDER_SETTING,
	ALLOW_SELF_APPROVAL_SETTING,
	APPROVAL_REQUIRED_FIELD,
	APPROVAL_SUMMARY_FIELD,
	APPROVED_FIELD,
	APPROVER_ROLE_SETTING,
	DEFAULT_APPROVER_ROLE,
	DEFAULT_LOOKBACK_MONTHS,
	ENABLE_SETTING,
	ITEM_APPROVAL_FIELD,
	LOOKBACK_MONTHS_SETTING,
	REQUESTER_ROLE,
	SALES_ORDER,
	SALES_ORDER_ITEM,
	STATE_APPROVED,
	STATE_CANCELLED,
	STATE_PENDING,
	STATE_REJECTED,
	WORKFLOW_NAME,
	WORKFLOW_STATE_FIELD,
	get_approver_role,
	is_enabled,
	is_self_approval_allowed,
)

WORKFLOW_STATE_STYLES = {
	STATE_PENDING: "Warning",
	STATE_APPROVED: "Success",
	STATE_REJECTED: "Danger",
	STATE_CANCELLED: "Inverse",
}
WORKFLOW_ACTIONS = (
	ACTION_SEND_FOR_APPROVAL,
	ACTION_APPROVE,
	ACTION_REJECT,
	ACTION_CANCEL,
)


def build_sales_order_item_approval_workflow(
	approver_role: str, allow_self_approval: bool = False
) -> dict:
	"""Return the single, unconditional Sales Order approval workflow.

	Every order enters at `Pending` (as the superseded "Sales Approval" workflow
	did) and a manager approves or rejects it. Which items are new is still
	computed per row and shown to the approver; it no longer changes the route.
	"""
	self_approval = 1 if allow_self_approval else 0
	return {
		"doctype": "Workflow",
		"workflow_name": WORKFLOW_NAME,
		"document_type": SALES_ORDER,
		"workflow_state_field": WORKFLOW_STATE_FIELD,
		"is_active": 1,
		"override_status": 1,
		"send_email_alert": 0,
		"states": [
			# Requester owns the order while it waits for review; a rejected
			# order stays editable so it can be corrected and sent back.
			{"state": STATE_PENDING, "doc_status": "0", "allow_edit": REQUESTER_ROLE},
			{
				"state": STATE_APPROVED,
				"doc_status": "1",
				"allow_edit": approver_role,
				"update_field": APPROVED_FIELD,
				"update_value": "1",
				# Submitted orders fall back to the list indicator (status/Closed)
				# instead of showing the raw workflow state.
				"avoid_status_override": 1,
			},
			{"state": STATE_REJECTED, "doc_status": "0", "allow_edit": REQUESTER_ROLE},
			{
				"state": STATE_CANCELLED,
				"doc_status": "2",
				"allow_edit": approver_role,
				"update_field": APPROVED_FIELD,
				"update_value": "0",
				"avoid_status_override": 1,
			},
		],
		"transitions": [
			{
				"state": STATE_PENDING,
				"action": ACTION_APPROVE,
				"next_state": STATE_APPROVED,
				"allowed": approver_role,
				"allow_self_approval": self_approval,
			},
			{
				"state": STATE_PENDING,
				"action": ACTION_REJECT,
				"next_state": STATE_REJECTED,
				"allowed": approver_role,
				"allow_self_approval": self_approval,
			},
			{
				"state": STATE_REJECTED,
				"action": ACTION_SEND_FOR_APPROVAL,
				"next_state": STATE_PENDING,
				"allowed": REQUESTER_ROLE,
				"allow_self_approval": 1,
			},
			# A submitted order can only be cancelled through the workflow; the
			# native Cancel button is suppressed once a cancelling state exists.
			{
				"state": STATE_APPROVED,
				"action": ACTION_CANCEL,
				"next_state": STATE_CANCELLED,
				"allowed": approver_role,
				"allow_self_approval": self_approval,
			},
		],
	}


def create_sales_order_item_approval_custom_fields():
	create_custom_fields(
		{
			SALES_ORDER: [
				{
					"fieldname": "custom_item_approval_section",
					"fieldtype": "Section Break",
					"label": "Item Approval",
					"insert_after": "status",
				},
				{
					"description": "Derived from the order items on every save. Read-only.",
					"fieldname": APPROVAL_SUMMARY_FIELD,
					"fieldtype": "HTML",
					"insert_after": "custom_item_approval_section",
					"label": "Item Approval Summary",
				},
				{
					"default": "0",
					"description": "Derived: any order row requires approval. Used by the approval workflow condition. Read-only.",
					"fieldname": APPROVAL_REQUIRED_FIELD,
					"fieldtype": "Check",
					"hidden": 1,
					"in_standard_filter": 1,
					"insert_after": APPROVAL_SUMMARY_FIELD,
					"label": "Items Require Approval",
					"no_copy": 1,
					"read_only": 1,
				},
				{
					"allow_on_submit": 1,
					"default": "0",
					"fieldname": APPROVED_FIELD,
					"fieldtype": "Check",
					"hidden": 1,
					"insert_after": APPROVAL_REQUIRED_FIELD,
					"label": "Items Approved",
					"no_copy": 1,
					"read_only": 1,
				},
			],
			SALES_ORDER_ITEM: [
				{
					"default": "0",
					"description": "Set automatically when the customer has not bought this item within the configured history window. Such items require approval before the Sales Order can be submitted.",
					"fieldname": ITEM_APPROVAL_FIELD,
					"fieldtype": "Check",
					"hidden": 1,
					"insert_after": "item_code",
					"label": "Requires Item Approval",
					"no_copy": 1,
					"read_only": 1,
				},
			],
		},
		update=True,
	)


def set_sales_order_item_approval_defaults():
	defaults = (
		(ENABLE_SETTING, 1),
		(LOOKBACK_MONTHS_SETTING, DEFAULT_LOOKBACK_MONTHS),
		(ALLOW_FIRST_ORDER_SETTING, 0),
		(ALLOW_SELF_APPROVAL_SETTING, 0),
	)
	for fieldname, value in defaults:
		if frappe.db.get_single_value("SRV Settings", fieldname) is None:
			frappe.db.set_single_value("SRV Settings", fieldname, value)

	if not frappe.db.get_single_value("SRV Settings", APPROVER_ROLE_SETTING):
		frappe.db.set_single_value("SRV Settings", APPROVER_ROLE_SETTING, DEFAULT_APPROVER_ROLE)


def ensure_workflow_states():
	for state, style in WORKFLOW_STATE_STYLES.items():
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": state, "style": style}
			).insert(ignore_permissions=True)


def ensure_workflow_action_masters():
	for action in WORKFLOW_ACTIONS:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)


def upsert_sales_order_item_approval_workflow(approver_role: str, allow_self_approval: bool = False):
	payload = build_sales_order_item_approval_workflow(approver_role, allow_self_approval)

	if frappe.db.exists("Workflow", WORKFLOW_NAME):
		workflow = frappe.get_doc("Workflow", WORKFLOW_NAME)
		workflow.states = []
		workflow.transitions = []
		for key, value in payload.items():
			if key in ("doctype", "states", "transitions"):
				continue
			workflow.set(key, value)
		for state in payload["states"]:
			workflow.append("states", state)
		for transition in payload["transitions"]:
			workflow.append("transitions", transition)
		workflow.save(ignore_permissions=True)
		return

	frappe.get_doc(payload).insert(ignore_permissions=True)


def sync_sales_order_item_approval_workflow():
	"""Create/activate the workflow when enabled, deactivate it when disabled."""
	if is_enabled():
		ensure_workflow_states()
		ensure_workflow_action_masters()
		upsert_sales_order_item_approval_workflow(
			get_approver_role(), is_self_approval_allowed()
		)
	elif frappe.db.exists("Workflow", WORKFLOW_NAME):
		frappe.db.set_value("Workflow", WORKFLOW_NAME, "is_active", 0)

	frappe.clear_cache(doctype=SALES_ORDER)


def backfill_sales_order_workflow_states():
	if not frappe.db.has_column(SALES_ORDER, WORKFLOW_STATE_FIELD):
		return

	if not is_enabled():
		return

	# Orders saved before the workflow existed (or imported) have no state yet;
	# seed it from docstatus. Historical non-canonical states are handled once by
	# the `sales_order_workflow_states` patch and by normalization on save.
	frappe.db.sql(
		"""
		UPDATE `tabSales Order`
		SET workflow_state = CASE docstatus
			WHEN 1 THEN %(approved)s
			WHEN 2 THEN %(cancelled)s
			ELSE %(pending)s
		END
		WHERE IFNULL(workflow_state, '') = ''
		""",
		{
			"approved": STATE_APPROVED,
			"cancelled": STATE_CANCELLED,
			"pending": STATE_PENDING,
		},
	)

	if frappe.db.has_column(SALES_ORDER, APPROVED_FIELD):
		frappe.db.sql(
			f"""
			UPDATE `tabSales Order`
			SET {APPROVED_FIELD} = 1
			WHERE docstatus = 1 AND IFNULL({APPROVED_FIELD}, 0) = 0
			"""
		)


def setup_sales_order_item_approval():
	set_sales_order_item_approval_defaults()
	create_sales_order_item_approval_custom_fields()
	sync_sales_order_item_approval_workflow()
	backfill_sales_order_workflow_states()
