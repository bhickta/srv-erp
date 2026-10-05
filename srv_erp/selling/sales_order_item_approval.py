from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_months, cint, cstr, nowdate

SALES_ORDER = "Sales Order"

ENABLE_SETTING = "enable_sales_order_item_approval"
LOOKBACK_MONTHS_SETTING = "sales_order_item_history_months"
APPROVER_ROLE_SETTING = "sales_order_item_approver_role"
ALLOW_FIRST_ORDER_SETTING = "allow_first_sales_order_without_history"
ALLOW_SELF_APPROVAL_SETTING = "allow_sales_order_item_requester_self_approval"
DEFAULT_LOOKBACK_MONTHS = 12
DEFAULT_APPROVER_ROLE = "Sales Manager"

# Per-row truth: does this Sales Order Item need approval because the customer
# has not bought it within the history window?
ITEM_APPROVAL_FIELD = "custom_item_requires_approval"
# Document-level approval flag, set by the approval workflow transition.
APPROVED_FIELD = "custom_sales_order_item_approved"
# Derived parent scalar: `any(row.custom_item_requires_approval)`. Written on every
# save. It exists only because Frappe's workflow condition engine (safe_eval)
# cannot read child table rows — it is not a source of truth.
APPROVAL_REQUIRED_FIELD = "custom_items_require_approval"
# Display-only HTML pill on the parent, derived from the child rows on every save.
APPROVAL_SUMMARY_FIELD = "custom_item_approval_summary"

SALES_ORDER_ITEM = "Sales Order Item"

WORKFLOW_STATE_FIELD = "workflow_state"
WORKFLOW_NAME = "Sales Order Item Approval"
REQUESTER_ROLE = "Sales User"

STATE_DRAFT = "Draft"
STATE_PENDING = "Pending Item Approval"
STATE_APPROVED = "Approved"
STATE_REJECTED = "Rejected"
STATE_CANCELLED = "Cancelled"

# Legacy states from the pre-existing "Sales Approval" workflow that this one
# supersedes. Existing documents may still sit in these states, so the merged
# workflow keeps accepting them and the data is migrated to the canonical
# states below.
LEGACY_STATE_PENDING = "Pending"
LEGACY_STATE_CANCEL = "Cancle"
LEGACY_STATE_MIGRATION = {
	LEGACY_STATE_PENDING: STATE_PENDING,
	LEGACY_STATE_CANCEL: STATE_CANCELLED,
}

ACTION_SUBMIT = "Submit"
ACTION_SEND_FOR_APPROVAL = "Send for Approval"
ACTION_APPROVE = "Approve"
ACTION_REJECT = "Reject"
ACTION_CANCEL = "Cancel"


def is_enabled() -> bool:
	return bool(cint(frappe.db.get_single_value("SRV Settings", ENABLE_SETTING)))


def get_lookback_months() -> int:
	value = frappe.db.get_single_value("SRV Settings", LOOKBACK_MONTHS_SETTING)
	return DEFAULT_LOOKBACK_MONTHS if value in (None, "") else cint(value)


def allow_first_order_without_history() -> bool:
	return bool(cint(frappe.db.get_single_value("SRV Settings", ALLOW_FIRST_ORDER_SETTING)))


def is_self_approval_allowed() -> bool:
	"""Whether a requester may approve their own Sales Order."""
	return bool(
		cint(frappe.db.get_single_value("SRV Settings", ALLOW_SELF_APPROVAL_SETTING))
	)


def can_user_approve_own_order(doc, user: str | None = None) -> bool:
	"""Whether `user` may approve the given Sales Order (maker-checker aware)."""
	user = user or frappe.session.user
	if user == "Administrator" or is_self_approval_allowed():
		return True
	return user != doc.get("owner")


def add_sales_order_item_approval_to_boot(bootinfo):
	bootinfo.srv_erp_sales_order_item_approval = {
		"enabled": is_enabled(),
		"allow_self_approval": is_self_approval_allowed(),
		"approver_role": get_approver_role(),
	}


def get_approver_role() -> str:
	return frappe.db.get_single_value("SRV Settings", APPROVER_ROLE_SETTING) or DEFAULT_APPROVER_ROLE


def customer_has_order_history(customer: str) -> bool:
	if not customer:
		return False
	return bool(
		frappe.db.exists(
			"Sales Order",
			{"customer": customer, "docstatus": 1},
		)
	)


def get_customer_item_history(customer: str, lookback_months: int | None = None) -> set[str]:
	"""Item codes the customer bought in submitted Sales Orders within the lookback window."""
	if not customer:
		return set()

	if lookback_months is None:
		lookback_months = get_lookback_months()

	params: dict = {"customer": customer}
	date_condition = ""
	if lookback_months and cint(lookback_months) > 0:
		params["cutoff"] = add_months(nowdate(), -cint(lookback_months))
		date_condition = "AND so.transaction_date >= %(cutoff)s"

	rows = frappe.db.sql(
		f"""
		SELECT DISTINCT soi.item_code
		FROM `tabSales Order Item` soi
		INNER JOIN `tabSales Order` so ON so.name = soi.parent
		WHERE so.docstatus = 1
			AND so.customer = %(customer)s
			{date_condition}
		""",
		params,
	)

	return {row[0] for row in rows}


def get_items_requiring_approval(doc) -> list[str]:
	"""Item codes on the Sales Order that are not in the customer's order history.

	Kept for callers that only need the codes. Prefer `mark_items_requiring_approval`
	when the document rows are available so the per-row flag is set too.
	"""
	if not requires_item_approval(doc):
		return []

	history = get_customer_item_history(doc.get("customer"))
	return _collect_required_items(doc, history)


def requires_item_approval(doc) -> bool:
	"""Whether the customer-history gate applies to this document at all."""
	if not is_enabled():
		return False

	if cint(doc.get("docstatus")) == 2:
		return False

	customer = doc.get("customer")
	if not customer:
		return False

	if allow_first_order_without_history() and not customer_has_order_history(customer):
		return False

	return True


def _collect_required_items(doc, history: set[str]) -> list[str]:
	required: list[str] = []
	for row in doc.get("items") or []:
		item_code = row.get("item_code")
		if item_code and item_code not in history and item_code not in required:
			required.append(item_code)
	return required


def _set_row_field(row, fieldname, value):
	if hasattr(row, "set"):
		row.set(fieldname, value)
	else:
		row[fieldname] = value


def mark_items_requiring_approval(doc) -> list[str]:
	"""Set the per-row approval flag and return the item codes that need approval.

	The per-row `custom_item_requires_approval` flag is the source of truth; the
	workflow condition and the parent summary are derived from it.
	"""
	if not requires_item_approval(doc):
		for row in doc.get("items") or []:
			_set_row_field(row, ITEM_APPROVAL_FIELD, 0)
		return []

	history = get_customer_item_history(doc.get("customer"))

	required: list[str] = []
	for row in doc.get("items") or []:
		item_code = row.get("item_code")
		needs_approval = bool(item_code) and item_code not in history
		_set_row_field(row, ITEM_APPROVAL_FIELD, 1 if needs_approval else 0)
		if needs_approval and item_code not in required:
			required.append(item_code)

	return required


def doc_has_items_requiring_approval(doc) -> bool:
	"""Aggregate helper used by the workflow condition string."""
	for row in doc.get("items") or []:
		if cint(row.get(ITEM_APPROVAL_FIELD)):
			return True
	return False

def get_active_workflow_state_names() -> set[str]:
	"""Valid workflow states of the currently active Sales Order workflow."""
	name = frappe.db.get_value(
		"Workflow", {"document_type": SALES_ORDER, "is_active": 1}, "name"
	)
	if not name:
		return set()
	return {
		row.state
		for row in frappe.get_doc("Workflow", name).states
	}


def normalize_sales_order_workflow_state(doc, method=None):
	"""Keep `workflow_state` valid for the active workflow.

	A stale client (an open tab from before the workflow was swapped) can send a
	state that belonged to the superseded "Sales Approval" workflow, e.g. a new
	order arriving with `workflow_state = "Pending"`. The active workflow has no
	transition from its first state to that one, so the save fails with
	"Workflow State transition not allowed from Draft to Pending". Map any
	unknown state onto its canonical equivalent (or the workflow's first state)
	before Frappe validates the transition.

	Runs on `before_validate` so it executes before `_validate`/`validate_workflow`.
	"""
	state = doc.get(WORKFLOW_STATE_FIELD)
	valid_states = get_active_workflow_state_names()
	if not valid_states:
		return

	if state in valid_states:
		return

	if doc.is_new():
		# A brand-new doc must start at the workflow's first state; the
		# legacy-state mapping below is only meaningful for existing docs.
		normalized = get_default_workflow_state(doc)
	else:
		normalized = LEGACY_STATE_MIGRATION.get(state, get_default_workflow_state(doc))

	doc.set(WORKFLOW_STATE_FIELD, normalized)

	# `validate_workflow` compares against the state loaded from the DB. Mirror
	# the correction there too, otherwise it sees a transition between two
	# different states and raises WorkflowTransitionError.
	previous = doc.get_doc_before_save()
	if previous is not None:
		previous.set(WORKFLOW_STATE_FIELD, normalized)


def get_default_workflow_state(doc) -> str:
	"""First workflow state matching the document's current docstatus."""
	docstatus = cstr(doc.get("docstatus") or 0)
	name = frappe.db.get_value(
		"Workflow", {"document_type": SALES_ORDER, "is_active": 1}, "name"
	)
	if not name:
		return STATE_DRAFT

	for row in frappe.get_doc("Workflow", name).states:
		if cstr(row.doc_status) == docstatus:
			return row.state

	return STATE_DRAFT


def validate_sales_order_item_history(doc, method=None):
	"""Mark the per-row approval flag and refresh the derived parent state.

	Saving is always allowed; submission is gated in
	`validate_sales_order_item_approval_submission`.
	"""
	if doc.is_new():
		doc.set(APPROVED_FIELD, 0)

	required = mark_items_requiring_approval(doc)
	# Derived scalar for the workflow condition; source of truth is the child rows.
	doc.set(APPROVAL_REQUIRED_FIELD, 1 if required else 0)
	doc.set(APPROVAL_SUMMARY_FIELD, build_approval_summary(required))


def build_approval_summary(required_items: list[str]) -> str:
	"""Display-only HTML pill shown on the parent. Not a stored data field."""
	if not required_items:
		return ""

	items = ", ".join(frappe.bold(item) for item in required_items)
	return frappe.as_unicode(
		f'<div class="indicator-pill orange" style="display:inline-block">'
		f"{_('New items need approval')}: {items}"
		f"</div>"
	)


def validate_sales_order_item_approval_submission(doc, method=None):
	"""Block submission of Sales Orders that still contain unapproved items."""
	required = get_items_requiring_approval(doc)
	if not required:
		return

	if cint(doc.get(APPROVED_FIELD)):
		return

	frappe.throw(
		_(
			"This Sales Order contains item(s) that are not in the customer's order "
			"history: {0}. Send it for approval before submitting."
		).format(", ".join(frappe.bold(item) for item in required)),
		title=_("Item Approval Required"),
	)
