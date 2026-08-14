import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from srv_erp.masters.dynamic_item.configuration import clear_settings_cache, get_approver_users


class MastersSettings(Document):
	def validate(self):
		roles = [row.role for row in self.get("requester_roles") or [] if row.role]
		if len(roles) != len(set(roles)):
			frappe.throw(_("Requester Roles cannot contain duplicates."))
		if cint(self.enable_dynamic_item_requests) and not roles:
			frappe.throw(_("Add at least one Requester Role before enabling Dynamic Item Requests."))
		if cint(self.enable_dynamic_item_requests) and not self.approver_role:
			frappe.throw(_("Approver Role is required before enabling Dynamic Item Requests."))
		if (
			cint(self.enable_dynamic_item_requests)
			and self.approver_role
			and not get_approver_users(role=self.approver_role)
		):
			frappe.throw(
				_("Assign approver role {0} to at least one enabled System User first.").format(
					frappe.bold(self.approver_role)
				)
			)
		if cint(self.enforce_variant_approval) and cint(self.allow_bulk_variant_creation):
			frappe.throw(_("Bulk Variant Creation cannot be enabled while variant approval is enforced."))

		grids = [
			(row.document_type, row.table_field)
			for row in self.get("item_grids") or []
			if row.document_type and row.table_field
		]
		if len(grids) != len(set(grids)):
			frappe.throw(_("Each Document Type and Table Field may appear only once."))
		self.validate_item_grids()

	def validate_item_grids(self):
		for row in self.get("item_grids") or []:
			if not row.document_type or not row.table_field:
				frappe.throw(_("Document Type and Table Field are required on every Item Grid row."))
			if not frappe.db.exists("DocType", row.document_type):
				frappe.throw(_("DocType {0} does not exist.").format(frappe.bold(row.document_type)))
			table_field = frappe.get_meta(row.document_type).get_field(row.table_field)
			if not table_field or table_field.fieldtype != "Table" or not table_field.options:
				frappe.throw(
					_("{0}.{1} must be a Table field.").format(
						frappe.bold(row.document_type), frappe.bold(row.table_field)
					)
				)
			if row.child_doctype != table_field.options:
				frappe.throw(
					_("Child DocType for {0}.{1} must be {2}.").format(
						frappe.bold(row.document_type),
						frappe.bold(row.table_field),
						frappe.bold(table_field.options),
					)
				)
			item_field = frappe.get_meta(table_field.options).get_field("item_code")
			if not item_field or item_field.fieldtype != "Link" or item_field.options != "Item":
				frappe.throw(
					_('{0}.{1} must contain an "item_code" Link to Item.').format(
						frappe.bold(row.document_type), frappe.bold(row.table_field)
					)
				)

	def on_update(self):
		clear_settings_cache()
