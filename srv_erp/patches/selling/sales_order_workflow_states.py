from __future__ import annotations

import frappe

SALES_ORDER = "Sales Order"
WORKFLOW_STATE_FIELD = "workflow_state"

# Non-canonical `workflow_state` values written by the superseded "Sales
# Approval" workflow ("Cancle") and by the earlier conditional revision of the
# Sales Order Item Approval workflow ("Draft", "Pending Item Approval"), mapped
# onto the merged workflow's canonical states. A stored document is only
# touched when it carries one of these exact values, so no canonical or
# unrelated state is ever overwritten. The legacy "Pending" is already the
# canonical entry state and is therefore left as-is.
STATE_RENAMES = {
	"Draft": "Pending",
	"Pending Item Approval": "Pending",
	"Cancle": "Cancelled",
}


def execute():
	if not frappe.db.has_column(SALES_ORDER, WORKFLOW_STATE_FIELD):
		return

	for old_state, new_state in STATE_RENAMES.items():
		frappe.db.sql(
			f"""
			UPDATE `tab{SALES_ORDER}`
			SET `{WORKFLOW_STATE_FIELD}` = %s
			WHERE `{WORKFLOW_STATE_FIELD}` = %s
			""",
			(new_state, old_state),
		)
