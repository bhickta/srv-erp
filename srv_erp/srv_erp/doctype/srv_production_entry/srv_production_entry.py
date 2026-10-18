import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from srv_erp.production.permissions import assignment_permission, entry_permission, is_planner
from srv_erp.production.service import (
	lock_assignment,
	positive_qty,
	prevent_cancel_edits,
	submitted_qty,
	update_progress,
	validate_production_date,
)


class SRVProductionEntry(Document):
	def _save(self, *args, **kwargs):
		if not self.is_new():
			# Serialize before Frappe locks the entry row in check_if_latest.
			assignment = frappe.db.get_value(self.doctype, self.name, "assignment")
			if assignment:
				if self.assignment != assignment:
					frappe.throw(_("The assignment of an existing production entry cannot be changed."))
				locked, _schedule_status = lock_assignment(assignment)
				if not assignment_permission(locked, "read"):
					frappe.throw(_("Not permitted for this production assignment."), frappe.PermissionError)
		return super()._save(*args, **kwargs)

	def validate(self):
		previous = self.get_doc_before_save()
		if previous and self.assignment != previous.assignment:
			frappe.throw(_("The assignment of an existing production entry cannot be changed."))
		assignment, docstatus = lock_assignment(self.assignment)
		if not assignment_permission(assignment, "read"):
			frappe.throw(_("Not permitted to record production for this assignment."), frappe.PermissionError)
		if docstatus != 1 or assignment.status == "Cancelled":
			frappe.throw(_("Production can only be recorded against an active schedule."))
		item = frappe.get_doc("Item", self.item_code)
		item.check_permission("read")
		if item.disabled or item.has_variants or item.variant_of != assignment.template:
			frappe.throw(_("Select an enabled variant of the assigned template."))
		if item.stock_uom != assignment.uom:
			frappe.throw(_("The variant stock UOM must match the planned UOM."))
		for key in ("company", "template", "supervisor", "uom"):
			self.set(key, assignment.get(key))
		self.qty = positive_qty(self.qty)
		validate_production_date(self.production_date)

	def before_submit(self):
		assignment, docstatus = lock_assignment(self.assignment)
		if not assignment_permission(assignment, "read") or docstatus != 1:
			frappe.throw(_("Not permitted to submit production for this assignment."), frappe.PermissionError)
		if flt(submitted_qty(self.assignment, exclude=self.name) + self.qty, 6) > flt(
			assignment.target_qty, 6
		):
			frappe.throw(_("Production exceeds the remaining target. Ask a planner to increase the target."))

	def on_submit(self):
		update_progress(lock_assignment(self.assignment)[0])

	def before_cancel(self):
		prevent_cancel_edits(self)
		if not is_planner() or not entry_permission(self, "cancel"):
			frappe.throw(
				_("Only a production planner can cancel production entries."), frappe.PermissionError
			)
		lock_assignment(self.assignment)

	def on_cancel(self):
		update_progress(lock_assignment(self.assignment)[0])
