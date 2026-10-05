from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from srv_erp.selling.sales_order_item_approval import (
	ACTION_APPROVE,
	ACTION_CANCEL,
	ACTION_REJECT,
	ACTION_SEND_FOR_APPROVAL,
	ACTION_SUBMIT,
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
	LEGACY_STATE_MIGRATION,
	LOOKBACK_MONTHS_SETTING,
	REQUESTER_ROLE,
	SALES_ORDER,
	SALES_ORDER_ITEM,
	STATE_APPROVED,
	STATE_CANCELLED,
	STATE_DRAFT,
	STATE_PENDING,
	STATE_REJECTED,
	WORKFLOW_NAME,
	WORKFLOW_STATE_FIELD,
	get_approver_role,
	is_enabled,
	is_self_approval_allowed,
)

WORKFLOW_STATE_STYLES = {
	STATE_DRAFT: "Info",
	STATE_PENDING: "Warning",
	STATE_APPROVED: "Success",
	STATE_REJECTED: "Danger",
	STATE_CANCELLED: "Inverse",
}
WORKFLOW_ACTIONS = (
	ACTION_SUBMIT,
	ACTION_SEND_FOR_APPROVAL,
	ACTION_APPROVE,
	ACTION_REJECT,
	ACTION_CANCEL,
)
# Remembers the active Sales Order workflow our feature replaced, so it can be
# restored when the feature is disabled. Stored as a hidden SRV Settings field.
DISPLACED_WORKFLOW_SETTING = "sales_order_item_approval_displaced_workflow"

# Workflow condition checks the derived parent scalar. Frappe's workflow engine
# (`safe_eval`) cannot read child-table rows, so the per-row truth is aggregated
# onto the parent by the validate hook.
# `Send for Approval` applies when at least one row needs approval; the
# complementary `Submit` applies when none do.
ITEMS_REQUIRE_APPROVAL_CONDITION = f"doc.{APPROVAL_REQUIRED_FIELD} == 1"
NO_ITEMS_REQUIRE_APPROVAL_CONDITION = f"doc.{APPROVAL_REQUIRED_FIELD} != 1"


def build_sales_order_item_approval_workflow(
	approver_role: str, allow_self_approval: bool = False
) -> dict:
	"""Return the Workflow definition for the given approver role."""
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
			{
				"state": STATE_DRAFT,
				"doc_status": "0",
				"allow_edit": REQUESTER_ROLE,
				"avoid_status_override": 1,
			},
			{"state": STATE_PENDING, "doc_status": "0", "allow_edit": approver_role},
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
				"state": STATE_DRAFT,
				"action": ACTION_SUBMIT,
				"next_state": STATE_APPROVED,
				"allowed": REQUESTER_ROLE,
				"allow_self_approval": 1,
				# No new items: submit directly, no approval needed.
				"condition": NO_ITEMS_REQUIRE_APPROVAL_CONDITION,
			},
			{
				"state": STATE_DRAFT,
				"action": ACTION_SEND_FOR_APPROVAL,
				"next_state": STATE_PENDING,
				"allowed": REQUESTER_ROLE,
				"allow_self_approval": 1,
				# At least one new item: route through approval.
				"condition": ITEMS_REQUIRE_APPROVAL_CONDITION,
			},
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


# Parent custom fields replaced by the child-table source of truth. Removed on
# migration so existing installs converge on the new model.
DEPRECATED_SALES_ORDER_FIELDS = (
	"custom_sales_order_item_approval_required",
	"custom_sales_order_unapproved_items",
)
# The pre-refactor parent flag is read here (under its old name) before removal.
LEGACY_PARENT_APPROVAL_REQUIRED_FIELD = "custom_sales_order_item_approval_required"
LEGACY_PARENT_UNAPPROVED_ITEMS_FIELD = "custom_sales_order_unapproved_items"


def remove_deprecated_sales_order_item_approval_fields():
	for fieldname in DEPRECATED_SALES_ORDER_FIELDS:
		field_name = f"{SALES_ORDER}-{fieldname}"
		if frappe.db.exists("Custom Field", field_name):
			frappe.delete_doc("Custom Field", field_name, ignore_permissions=True, force=True)
	frappe.clear_cache(doctype=SALES_ORDER)

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
		upsert_sales_order_item_approval_workflow(
			get_approver_role(), is_self_approval_allowed()
		)
	elif frappe.db.exists("Workflow", WORKFLOW_NAME):
		frappe.db.set_value("Workflow", WORKFLOW_NAME, "is_active", 0)
		restore_displaced_workflow()

	frappe.clear_cache(doctype=SALES_ORDER)


def backfill_item_approval_flags():
	"""Move the old parent-level truth onto the child rows before dropping it.

	Older installs stored `custom_sales_order_item_approval_required` on the
	parent and the item codes in `custom_sales_order_unapproved_items`. Populate
	per-row `custom_item_requires_approval` from the item-code list when present,
	otherwise from the parent flag (all rows flagged).
	"""
	if not frappe.db.has_column(SALES_ORDER_ITEM, ITEM_APPROVAL_FIELD):
		return

	has_required_flag = frappe.db.has_column(SALES_ORDER, LEGACY_PARENT_APPROVAL_REQUIRED_FIELD)
	has_item_text = frappe.db.has_column(SALES_ORDER, LEGACY_PARENT_UNAPPROVED_ITEMS_FIELD)

	if not has_required_flag and not has_item_text:
		return

	if has_item_text:
		# Flag rows whose item_code is listed in the legacy text blob.
		frappe.db.sql(
			f"""
			UPDATE `tabSales Order Item` soi
			INNER JOIN `tabSales Order` so ON so.name = soi.parent
			SET soi.{ITEM_APPROVAL_FIELD} = 1
			WHERE so.{LEGACY_PARENT_UNAPPROVED_ITEMS_FIELD} IS NOT NULL
				AND so.{LEGACY_PARENT_UNAPPROVED_ITEMS_FIELD} != ''
				AND FIND_IN_SET(soi.item_code,
					REPLACE(so.{LEGACY_PARENT_UNAPPROVED_ITEMS_FIELD}, '\\n', ',')) > 0
			"""
		)
	else:
		# No item list: fall back to flagging every row of orders marked required.
		frappe.db.sql(
			f"""
			UPDATE `tabSales Order Item` soi
			INNER JOIN `tabSales Order` so ON so.name = soi.parent
			SET soi.{ITEM_APPROVAL_FIELD} = 1
			WHERE so.{LEGACY_PARENT_APPROVAL_REQUIRED_FIELD} = 1
			"""
		)


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
	backfill_item_approval_flags()
	remove_deprecated_sales_order_item_approval_fields()
	sync_sales_order_item_approval_workflow()
	backfill_sales_order_workflow_states()
