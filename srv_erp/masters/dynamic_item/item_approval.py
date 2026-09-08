import frappe
from erpnext.controllers.item_variant import get_variant
from frappe import _
from frappe.utils import cint, now_datetime

from srv_erp.masters.dynamic_item.cleanup import delete_staged_item
from srv_erp.masters.dynamic_item.configuration import APPROVED, PENDING
from srv_erp.masters.dynamic_item.context import dynamic_item_service_context
from srv_erp.masters.dynamic_item.exceptions import DynamicItemConflict
from srv_erp.masters.dynamic_item.packaging import add_packaging_rows, get_missing_packaging
from srv_erp.masters.dynamic_item.repository import get_item_state, lock_template


def get_request_attributes(request) -> dict[str, str]:
	return {row.item_attribute: row.attribute_value for row in request.attributes}


def approve_staged_variant(request) -> str:
	if not request.staged_item_code or not frappe.db.exists("Item", request.staged_item_code):
		frappe.throw(_("The staged Item no longer exists."))
	lock_template(request.template_item)
	attributes = get_request_attributes(request)
	other_variant = get_variant(request.template_item, attributes, variant=request.staged_item_code)
	if other_variant:
		state = get_item_state(other_variant)
		if cint(state.disabled):
			frappe.throw(
				_("Matching Item {0} exists but is disabled.").format(frappe.bold(other_variant)),
				DynamicItemConflict,
			)
		delete_staged_item(request)
		return other_variant

	item = frappe.get_doc("Item", request.staged_item_code)
	if item.dynamic_item_approval_status != PENDING or item.dynamic_item_request != request.name:
		frappe.throw(_("Staged Item approval metadata does not match this request."))
	if not cint(item.disabled):
		frappe.throw(_("Staged Item must remain disabled until approval."))
	missing_packaging = get_missing_packaging(item, [row.as_dict() for row in request.uoms])
	if missing_packaging:
		frappe.throw(_("Staged Item packaging no longer matches the approved request parameters."))
	item.dynamic_item_approval_status = APPROVED
	item.dynamic_item_approved_by = frappe.session.user
	item.dynamic_item_approved_on = now_datetime()
	item.disabled = 0
	with dynamic_item_service_context():
		item.save(ignore_permissions=True)
	return item.name


def approve_packaging_request(request) -> str:
	if not request.resolved_item or not frappe.db.exists("Item", request.resolved_item):
		frappe.throw(_("The Item for this packaging request no longer exists."))
	frappe.db.sql("select name from `tabItem` where name = %s for update", request.resolved_item)
	item = frappe.get_doc("Item", request.resolved_item)
	if cint(item.disabled):
		frappe.throw(_("Item {0} is disabled.").format(frappe.bold(item.name)))
	add_packaging_rows(item, [row.as_dict() for row in request.uoms])
	with dynamic_item_service_context():
		item.save(ignore_permissions=True)
	return item.name
