import frappe
from frappe import _
from frappe.model.document import Document


class DynamicItemRequest(Document):
	def before_insert(self):
		if not getattr(frappe.flags, "dynamic_item_service", False):
			frappe.throw(_("Dynamic Item Requests must be created through the request API."))

	def validate(self):
		if self.is_new() or getattr(frappe.flags, "dynamic_item_service", False):
			return
		previous = self.get_doc_before_save()
		if not previous:
			return
		protected_fields = (
			"request_type",
			"status",
			"template_item",
			"staged_item_code",
			"resolved_item",
			"signature",
			"active_signature",
			"source_doctype",
			"source_field",
			"source_name",
			"requested_by",
			"requested_on",
			"approved_by",
			"approved_on",
			"rejected_by",
			"rejected_on",
			"rejection_reason",
			"amended_from_request",
		)
		if any(previous.get(fieldname) != self.get(fieldname) for fieldname in protected_fields):
			frappe.throw(_("Dynamic Item Request state can only be changed through approval actions."))
		if not self.is_child_table_same("attributes") or not self.is_child_table_same("uoms"):
			frappe.throw(_("Pending request parameters cannot be edited. Reject and create a new request."))


def on_doctype_update():
	frappe.db.add_index(
		"Dynamic Item Request",
		["status", "request_type", "resolved_item"],
		"dynamic_item_resolution_idx",
	)
	frappe.db.add_index(
		"Dynamic Item Request",
		["requested_by", "status"],
		"dynamic_item_requester_idx",
	)
