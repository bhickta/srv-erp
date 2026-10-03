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
	LEGACY_STATE_CANCEL,
	LEGACY_STATE_MIGRATION,
	LEGACY_STATE_PENDING,
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
# Legacy states carried over from the superseded "Sales Approval" workflow.
LEGACY_WORKFLOW_STATE_STYLES = {
	LEGACY_STATE_PENDING: "Warning",
	LEGACY_STATE_CANCEL: "Inverse",
}
WORKFLOW_ACTIONS = (ACTION_SUBMIT, ACTION_SEND_FOR_APPROVAL, ACTION_APPROVE, ACTION_REJECT)
# Remembers the active Sales Order workflow our feature replaced, so it can be
# restored when the feature is disabled. Stored as a hidden SRV Settings field.
DISPLACED_WORKFLOW_SETTING = "sales_order_item_approval_displaced_workflow"
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
			# Legacy states inherited from the superseded "Sales Approval"
			# workflow. They are kept valid (with outbound transitions) so any
			# document that has not been migrated yet can still progress.
			{"state": LEGACY_STATE_PENDING, "doc_status": "0", "allow_edit": EDIT_ROLE},
			{
				"state": LEGACY_STATE_CANCEL,
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
			# Legacy "Pending" can be approved/rejected like the new pending state.
			{
				"state": LEGACY_STATE_PENDING,
				"action": ACTION_APPROVE,
				"next_state": STATE_APPROVED,
				"allowed": approver_role,
				"allow_self_approval": 0,
			},
			{
				"state": LEGACY_STATE_PENDING,
				"action": ACTION_REJECT,
				"next_state": STATE_REJECTED,
				"allowed": approver_role,
				"allow_self_approval": 0,
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
	for state, style in {**WORKFLOW_STATE_STYLES, **LEGACY_WORKFLOW_STATE_STYLES}.items():
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


def get_other_active_sales_order_workflow() -> str | None:
	"""Return another active Sales Order workflow that ours would deactivate."""
	return frappe.db.get_value(
		"Workflow",
		{
			"document_type": SALES_ORDER,
			"is_active": 1,
			"name": ["!=", WORKFLOW_NAME],
		},
		"name",
	)


def remember_displaced_workflow():
	"""Record the active Sales Order workflow (if any) that ours replaces."""
	displaced = get_other_active_sales_order_workflow()
	if displaced:
		frappe.db.set_single_value("SRV Settings", DISPLACED_WORKFLOW_SETTING, displaced)


def restore_displaced_workflow():
	"""Re-activate the workflow ours replaced, if it still exists."""
	displaced = frappe.db.get_single_value("SRV Settings", DISPLACED_WORKFLOW_SETTING)
	if displaced and frappe.db.exists("Workflow", displaced):
		frappe.db.set_value("Workflow", displaced, "is_active", 1)
	frappe.db.set_single_value("SRV Settings", DISPLACED_WORKFLOW_SETTING, None)


def sync_sales_order_item_approval_workflow():
	"""Create/activate the workflow when enabled, deactivate it when disabled.

	Frappe allows a single active Workflow per DocType, so activating ours
	deactivates any other (e.g. the legacy "Sales Approval"). We remember it and
	restore it when the feature is turned off instead of silently clobbering it.
	"""
	if is_enabled():
		ensure_workflow_states()
		ensure_workflow_action_masters()
		remember_displaced_workflow()
		upsert_sales_order_item_approval_workflow(get_approver_role())
	elif frappe.db.exists("Workflow", WORKFLOW_NAME):
		frappe.db.set_value("Workflow", WORKFLOW_NAME, "is_active", 0)
		restore_displaced_workflow()

	frappe.clear_cache(doctype=SALES_ORDER)


def backfill_sales_order_workflow_states():
	if not frappe.db.has_column(SALES_ORDER, WORKFLOW_STATE_FIELD):
		return

	# Migrate legacy "Sales Approval" states onto the canonical states.
	when_clauses = " ".join(
		f"WHEN %(legacy_{idx})s THEN %(target_{idx})s"
		for idx in range(len(LEGACY_STATE_MIGRATION))
	)
	params: dict = {"legacy_states": tuple(LEGACY_STATE_MIGRATION)}
	for idx, (legacy, target) in enumerate(LEGACY_STATE_MIGRATION.items()):
		params[f"legacy_{idx}"] = legacy
		params[f"target_{idx}"] = target
	frappe.db.sql(
		f"""
		UPDATE `tabSales Order`
		SET workflow_state = CASE workflow_state
			{when_clauses}
			ELSE workflow_state
		END
		WHERE workflow_state IN %(legacy_states)s
		""",
		params,
	)

	if not is_enabled():
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
