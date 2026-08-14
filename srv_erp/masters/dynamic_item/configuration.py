from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

REQUESTER_ROLE = "Masters Item Requester"
APPROVER_ROLE = "Masters Item Approver"
PENDING = "Pending Approval"
APPROVED = "Approved"
REJECTED = "Rejected"
CANCELLED = "Cancelled"
CREATE_VARIANT = "Create Variant"
ADD_PACKAGING = "Add Packaging"


def get_settings():
	return frappe.get_cached_doc("Masters Settings")


def masters_settings_available() -> bool:
	"""Return whether the settings DocType is usable in the current migration phase."""
	# Single DocTypes store values in tabSingles and intentionally have no own table.
	return bool(frappe.db.exists("DocType", "Masters Settings"))


def clear_settings_cache():
	frappe.clear_document_cache("Masters Settings", "Masters Settings")


def is_dynamic_item_enabled() -> bool:
	if not masters_settings_available():
		return False
	return bool(cint(get_settings().enable_dynamic_item_requests))


def is_approval_enforced() -> bool:
	if not masters_settings_available():
		return False
	return bool(cint(get_settings().enforce_variant_approval))


def is_bulk_variant_creation_enabled() -> bool:
	if not masters_settings_available():
		return False
	return bool(cint(get_settings().allow_bulk_variant_creation))


def get_requester_roles() -> set[str]:
	return {row.role for row in get_settings().get("requester_roles") or [] if row.role}


def get_approver_role() -> str:
	return get_settings().approver_role or APPROVER_ROLE


def get_approver_users(exclude_user: str | None = None, role: str | None = None) -> list[str]:
	users = frappe.get_all(
		"Has Role",
		filters={"role": role or get_approver_role(), "parenttype": "User"},
		pluck="parent",
	)
	if exclude_user:
		users = [user for user in users if user != exclude_user]
	if not users:
		return []
	return frappe.get_all(
		"User",
		filters={
			"name": ["in", users],
			"enabled": 1,
			"user_type": "System User",
		},
		pluck="name",
		order_by="name",
	)


def user_has_requester_role(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(get_requester_roles().intersection(frappe.get_roles(user)))


def user_has_approver_role(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return get_approver_role() in frappe.get_roles(user)


def require_requester(user: str | None = None):
	user = user or frappe.session.user
	if not is_dynamic_item_enabled():
		frappe.throw(_("Dynamic Item Requests are disabled in Masters Settings."))
	if not user_has_requester_role(user):
		frappe.throw(_("User {0} is not permitted to request dynamic Items.").format(frappe.bold(user)))


def require_approver(user: str | None = None):
	user = user or frappe.session.user
	if not user_has_approver_role(user):
		frappe.throw(
			_("User {0} does not have the configured Masters approver role.").format(frappe.bold(user)),
			frappe.PermissionError,
		)


def is_grid_enabled(document_type: str, table_field: str) -> bool:
	if not is_dynamic_item_enabled():
		return False
	return any(
		cint(row.enabled) and row.document_type == document_type and row.table_field == table_field
		for row in get_settings().get("item_grids") or []
	)
