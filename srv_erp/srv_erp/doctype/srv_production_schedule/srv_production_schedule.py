import frappe
from frappe import _
from frappe.model.document import Document

from srv_erp.production.service import (
	ASSIGNMENT,
	lock_schedule,
	prevent_cancel_edits,
	refresh_schedule_progress,
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
			"dates": dates,
			"assignment_count": len(dates) * len(self.items),
			"items": [
				{
					key: row.get(key)
					for key in (
						"template",
						"item_code",
						"supervisor",
						"uom",
						"qty_per_occurrence",
						"planned_qty",
					)
				}
				for row in self.items
			],
		}

	def on_submit(self):
		from srv_erp.production.service import schedule_dates

		for row in self.items:
			for date in schedule_dates(self):
				doc = frappe.get_doc(
					{
						"doctype": ASSIGNMENT,
						"schedule": self.name,
						"schedule_item": row.name,
						"occurrence_key": f"{self.name}:{row.name}:{date.isoformat()}",
						"company": self.company,
						"template": row.template,
						"item_code": row.item_code,
						"supervisor": row.supervisor,
						"planned_date": date,
						"target_qty": row.qty_per_occurrence,
						"remaining_qty": row.qty_per_occurrence,
						"uom": row.uom,
					}
				)
				doc.flags.from_production_schedule = True
				doc.insert(ignore_permissions=True)
		refresh_schedule_progress(self.name)
		self.reload()

	def before_update_after_submit(self):
		require_planner(self.company)
		previous = self.get_doc_before_save()
		for key in (
			"company",
			"start_date",
			"end_date",
			"frequency",
			"interval",
			"recurrence_unit",
			"weekdays",
			"custom_dates",
			"template",
			"supervisor",
			"uom",
			"qty_per_occurrence",
		):
			if self.has_value_changed(key):
				frappe.throw(_("Submitted schedule source fields cannot be changed."))
		source_keys = ("name", "template", "item_code", "qty_per_occurrence", "uom", "supervisor")
		if [[row.get(key) for key in source_keys] for row in self.items] != [
			[row.get(key) for key in source_keys] for row in previous.items
		]:
			frappe.throw(
				_(
					"Submitted schedule items cannot be changed. Amend the schedule or adjust a dated assignment."
				)
			)
		for key in ("status", "percent_completed", "total_items", "remaining_items", "occurrence_count"):
			self.set(key, previous.get(key))
		for row, old in zip(self.items, previous.items, strict=True):
			for key in ("planned_qty", "completed_qty", "remaining_qty", "percent_completed"):
				row.set(key, old.get(key))

	def before_cancel(self):
		prevent_cancel_edits(self)
		require_planner(self.company)
		lock_schedule(self.name)
		for name in frappe.get_all(ASSIGNMENT, filters={"schedule": self.name}, pluck="name"):
			if submitted_qty(name):
				frappe.throw(_("Cancel the submitted production entries before cancelling this schedule."))

	def on_cancel(self):
		for name in frappe.get_all(ASSIGNMENT, filters={"schedule": self.name}, pluck="name"):
			update_progress(
				frappe.get_doc(ASSIGNMENT, name, for_update=True), cancelled=True, refresh_schedule=False
			)
		refresh_schedule_progress(self.name)
		self.reload()

	def on_trash(self):
		if frappe.db.exists(ASSIGNMENT, {"schedule": self.name}):
			frappe.throw(_("Schedules with generated assignments must be retained for audit history."))
