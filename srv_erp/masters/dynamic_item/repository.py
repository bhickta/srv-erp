from __future__ import annotations

import frappe
from erpnext.controllers.item_variant import get_variant

from srv_erp.masters.dynamic_item.configuration import PENDING
from srv_erp.masters.dynamic_item.context import dynamic_item_service_context


def get_item_state(item_code: str) -> frappe._dict:
	return frappe.db.get_value(
		"Item",
		item_code,
		["name", "disabled", "dynamic_item_approval_status", "dynamic_item_request"],
		as_dict=True,
	)


def get_variant_if_present(template_item: str, attributes: dict[str, str]) -> str | None:
	return get_variant(template_item, attributes)


def get_pending_request(active_signature: str):
	return frappe.db.get_value(
		"Dynamic Item Request",
		{"active_signature": active_signature, "status": PENDING},
		["name", "request_type", "status", "staged_item_code", "resolved_item"],
		as_dict=True,
	)


def insert_request(values: dict):
	active_signature = values["active_signature"]
	existing = get_pending_request(active_signature)
	if existing:
		return frappe.get_doc("Dynamic Item Request", existing.name), False

	savepoint = "dynamic_item_request_reservation"
	frappe.db.savepoint(savepoint)
	try:
		with dynamic_item_service_context():
			request = frappe.get_doc({"doctype": "Dynamic Item Request", **values})
			request.insert(ignore_permissions=True)
		return request, True
	except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
		frappe.db.rollback(save_point=savepoint)
		existing = get_pending_request(active_signature)
		if not existing:
			raise
		return frappe.get_doc("Dynamic Item Request", existing.name), False


def lock_template(template_item: str):
	frappe.db.sql("select name from `tabItem` where name = %s for update", template_item)


def lock_request(name: str):
	frappe.db.sql("select name from `tabDynamic Item Request` where name = %s for update", name)
