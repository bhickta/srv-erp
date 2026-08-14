import frappe
from frappe import _

from erpnext.controllers.item_variant import (
	create_variant_doc_for_quick_entry as erpnext_create_variant_doc_for_quick_entry,
)
from erpnext.controllers.item_variant import (
	enqueue_multiple_variant_creation as erpnext_enqueue_multiple_variant_creation,
)

from srv_erp.masters.dynamic_item.configuration import (
	is_approval_enforced,
	is_bulk_variant_creation_enabled,
)


def require_bulk_variant_creation():
	if not is_bulk_variant_creation_enabled():
		frappe.throw(_("Bulk variant creation is disabled in Masters Settings."))
	if is_approval_enforced():
		frappe.throw(_("Bulk variant creation is unavailable while variant approval is enforced."))


@frappe.whitelist()
def enqueue_multiple_variant_creation(item, args, use_template_image=False):
	require_bulk_variant_creation()
	return erpnext_enqueue_multiple_variant_creation(item, args, use_template_image)


@frappe.whitelist()
def create_variant_doc_for_quick_entry(template, args):
	if is_approval_enforced():
		frappe.throw(_("Use Resolve / Request Item so the new variant follows Masters approval."))
	return erpnext_create_variant_doc_for_quick_entry(template, args)
