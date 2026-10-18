import frappe
from frappe import _
from frappe.model.document import Document

from srv_erp.production.service import (
	ASSIGNMENT,
	lock_schedule,
	prevent_cancel_edits,
	require_planner,
	submitted_qty,
	update_progress,
	validate_schedule,
)


class SRVProductionSchedule(Document):
	def validate(self):
		validate_schedule(self)

	@frappe.whitelist()
	def preview(self):
		self.check_permission("read" if not self.is_new() else "create")
		dates = validate_schedule(self)
		return {
			"supervisor": self.supervisor,
			"uom": self.uom,
			"total_qty": self.qty_per_occurrence * len(dates),
			"dates": dates,
		}

	def on_submit(self):
		for date in validate_schedule(self):
			doc = frappe.get_doc(
				{
					"doctype": ASSIGNMENT,
					"schedule": self.name,
					"occurrence_key": f"{self.name}:{date.isoformat()}",
					"company": self.company,
					"template": self.template,
					"supervisor": self.supervisor,
					"planned_date": date,
					"target_qty": self.qty_per_occurrence,
					"remaining_qty": self.qty_per_occurrence,
					"uom": self.uom,
				}
			)
			doc.flags.from_production_schedule = True
			doc.insert(ignore_permissions=True)

	def before_cancel(self):
		prevent_cancel_edits(self)
		require_planner(self.company)
		lock_schedule(self.name)
		for name in frappe.get_all(ASSIGNMENT, filters={"schedule": self.name}, pluck="name"):
			if submitted_qty(name):
				frappe.throw(_("Cancel the submitted production entries before cancelling this schedule."))

	def on_cancel(self):
		for name in frappe.get_all(ASSIGNMENT, filters={"schedule": self.name}, pluck="name"):
			update_progress(frappe.get_doc(ASSIGNMENT, name), cancelled=True)

	def on_trash(self):
		if frappe.db.exists(ASSIGNMENT, {"schedule": self.name}):
			frappe.throw(_("Schedules with generated assignments must be retained for audit history."))
