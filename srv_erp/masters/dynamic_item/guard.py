from __future__ import annotations

import frappe
from frappe import _

from srv_erp.masters.dynamic_item.configuration import APPROVED, PENDING, is_approval_enforced


def validate_dynamic_item_insert(doc, method=None):
	if not doc.variant_of or not is_approval_enforced():
		return
	if getattr(frappe.flags, "dynamic_item_service", False):
		return
	frappe.throw(
		_("New Item variants must be created through a Dynamic Item Request in the Masters module."),
		frappe.PermissionError,
	)


def protect_dynamic_item_state(doc, method=None):
	if not doc.get("dynamic_item_request"):
		return
	if getattr(frappe.flags, "dynamic_item_service", False):
		return
	previous = doc.get_doc_before_save()
	if not previous:
		return
	protected_fields = (
		"dynamic_item_approval_status",
		"dynamic_item_request",
		"dynamic_variant_signature",
		"dynamic_item_requested_by",
		"dynamic_item_approved_by",
		"dynamic_item_approved_on",
	)
	approval_changed = any(previous.get(fieldname) != doc.get(fieldname) for fieldname in protected_fields)
	pending_activation_changed = previous.get("dynamic_item_approval_status") == PENDING and previous.get(
		"disabled"
	) != doc.get("disabled")
	if approval_changed or pending_activation_changed:
		frappe.throw(_("Dynamic Item approval fields can only be changed through the Masters approval flow."))


def validate_no_unapproved_items(doc, method=None):
	if not is_approval_enforced() or getattr(frappe.flags, "dynamic_item_service", False):
		return
	if doc.doctype in ("Item", "Dynamic Item Request"):
		return
	item_codes = collect_item_links(doc)
	if not item_codes:
		return
	pending_items = frappe.get_all(
		"Item",
		filters={
			"name": ["in", list(item_codes)],
			"dynamic_item_approval_status": ["!=", APPROVED],
			"dynamic_item_request": ["is", "set"],
		},
		pluck="name",
	)
	if pending_items:
		frappe.throw(
			_("Pending Dynamic Items cannot be used: {0}.").format(
				", ".join(frappe.bold(item) for item in sorted(pending_items))
			)
		)


def collect_item_links(doc) -> set[str]:
	item_codes = set()
	meta = frappe.get_meta(doc.doctype)
	for field in meta.fields:
		if field.fieldtype == "Link" and field.options == "Item" and doc.get(field.fieldname):
			item_codes.add(doc.get(field.fieldname))
		elif field.fieldtype == "Table" and field.options:
			child_meta = frappe.get_meta(field.options)
			item_fields = [
				df.fieldname for df in child_meta.fields if df.fieldtype == "Link" and df.options == "Item"
			]
			for row in doc.get(field.fieldname) or []:
				for fieldname in item_fields:
					if row.get(fieldname):
						item_codes.add(row.get(fieldname))
	return item_codes
