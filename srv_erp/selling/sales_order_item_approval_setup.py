from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from srv_erp.selling.sales_order_item_approval import (
	ACTION_APPROVE,
	ACTION_REJECT,
	ACTION_SEND_FOR_APPROVAL,
	ACTION_SUBMIT,
	ALLOW_FIRST_ORDER_SETTING,
	APPROVAL_REQUIRED_FIELD,
	APPROVED_FIELD,
	APPROVER_ROLE_SETTING,
	DEFAULT_APPROVER_ROLE,
	DEFAULT_LOOKBACK_MONTHS,
	ENABLE_SETTING,
	LOOKBACK_MONTHS_SETTING,
	SALES_ORDER,
	STATE_APPROVED,
	STATE_CANCELLED,
	STATE_DRAFT,
	STATE_PENDING,
	STATE_REJECTED,
	UNAPPROVED_ITEMS_FIELD,
	WORKFLOW_NAME,
	WORKFLOW_STATE_FIELD,
	get_approver_role,
	is_enabled,
)

WORKFLOW_STATE_STYLES = {
	STATE_DRAFT: "Info",
	STATE_PENDING: "Warning",
	STATE_APPROVED: "Success",
	STATE_REJECTED: "Danger",
	STATE_CANCELLED: "Inverse",
}
WORKFLOW_ACTIONS = (ACTION_SUBMIT, ACTION_SEND_FOR_APPROVAL, ACTION_APPROVE, ACTION_REJECT)
# Edit access is not used to gate approvals here; keep it open so activating the
# workflow never locks users out of the form. Who can approve is enforced by the
# transition `allowed` roles instead.
EDIT_ROLE = "All"


def build_sales_order_item_approval_workflow(approver_role: str) -> dict:
	"""Return the Workflow definition for the given approver role."""
	approval_required = APPROVAL_REQUIRED_FIELD

	return {
		"doctype": "Workflow",
		"workflow_name": WORKFLOW_NAME,
		"document_type": SALES_ORDER,
		"workflow_state_field": WORKFLOW_STATE_FIELD,
		"is_active": 1,
		"override_status": 1,
		"send_email_alert": 0,
		"states": [
			{
				"state": STATE_DRAFT,
				"doc_status": "0",
				"allow_edit": EDIT_ROLE,
				"avoid_status_override": 1,
			},
			{"state": STATE_PENDING, "doc_status": "0", "allow_edit": EDIT_ROLE},
			{
				"state": STATE_APPROVED,
				"doc_status": "1",
				"allow_edit": EDIT_ROLE,
				"update_field": APPROVED_FIELD,
				"update_value": "1",
				"evaluate_as_expression": 0,
				# Submitted orders fall back to the list indicator (status/Closed)
				# instead of showing the raw workflow state.
				"avoid_status_override": 1,
			},
			{"state": STATE_REJECTED, "doc_status": "0", "allow_edit": EDIT_ROLE},
			{
				"state": STATE_CANCELLED,
				"doc_status": "2",
				"allow_edit": EDIT_ROLE,
				"avoid_status_override": 1,
			},
		],
		"transitions": [
			{
				"state": STATE_DRAFT,
				"action": ACTION_SUBMIT,
				"next_state": STATE_APPROVED,
				"allowed": EDIT_ROLE,
				"allow_self_approval": 1,
				"condition": f"doc.{approval_required} != 1",
			},
			{
				"state": STATE_DRAFT,
				"action": ACTION_SEND_FOR_APPROVAL,
				"next_state": STATE_PENDING,
				"allowed": EDIT_ROLE,
				"allow_self_approval": 1,
				"condition": f"doc.{approval_required} == 1",
			},
			{
				"state": STATE_PENDING,
				"action": ACTION_APPROVE,
				"next_state": STATE_APPROVED,
				"allowed": approver_role,
				"allow_self_approval": 0,
			},
			{
				"state": STATE_PENDING,
				"action": ACTION_REJECT,
				"next_state": STATE_REJECTED,
				"allowed": approver_role,
				"allow_self_approval": 0,
			},
			{
				"state": STATE_REJECTED,
				"action": ACTION_SEND_FOR_APPROVAL,
				"next_state": STATE_PENDING,
				"allowed": EDIT_ROLE,
				"allow_self_approval": 1,
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
					"default": "0",
					"description": "Set automatically when the order uses items the customer has not bought within the configured history window.",
					"fieldname": APPROVAL_REQUIRED_FIELD,
					"fieldtype": "Check",
					"in_standard_filter": 1,
					"insert_after": "custom_item_approval_section",
					"label": "New Items Need Approval",
					"no_copy": 1,
					"read_only": 1,
				},
				{
					"default": "0",
					"fieldname": APPROVED_FIELD,
					"fieldtype": "Check",
					"hidden": 1,
					"insert_after": APPROVAL_REQUIRED_FIELD,
					"label": "Items Approved",
					"no_copy": 1,
					"read_only": 1,
				},
				{
					"depends_on": f"eval:doc.{APPROVAL_REQUIRED_FIELD}==1",
					"fieldname": UNAPPROVED_ITEMS_FIELD,
					"fieldtype": "Small Text",
					"insert_after": APPROVED_FIELD,
					"label": "Items Requiring Approval",
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


def upsert_sales_order_item_approval_workflow(approver_role: str):
	payload = build_sales_order_item_approval_workflow(approver_role)

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
		upsert_sales_order_item_approval_workflow(get_approver_role())
	elif frappe.db.exists("Workflow", WORKFLOW_NAME):
		frappe.db.set_value("Workflow", WORKFLOW_NAME, "is_active", 0)

	frappe.clear_cache(doctype=SALES_ORDER)


def backfill_sales_order_workflow_states():
	if not is_enabled():
		return

	if not frappe.db.has_column(SALES_ORDER, WORKFLOW_STATE_FIELD):
		return

	frappe.db.sql(
		"""
		UPDATE `tabSales Order`
		SET workflow_state = CASE docstatus
			WHEN 1 THEN %(approved)s
			WHEN 2 THEN %(cancelled)s
			ELSE %(draft)s
		END
		WHERE IFNULL(workflow_state, '') = ''
		""",
		{
			"approved": STATE_APPROVED,
			"cancelled": STATE_CANCELLED,
			"draft": STATE_DRAFT,
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
