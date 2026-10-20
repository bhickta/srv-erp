import frappe
from frappe import _
from frappe.model.document import Document

from srv_erp.production.service import (
	ASSIGNMENT,
	lock_schedule,
	prevent_cancel_edits,
	refresh_schedule_progress,
	require_planner,
	schedule_dates,
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
			"assignment_count": sum(len(schedule_dates(self, row.schedule_date)) for row in self.items)
			* max(len(self.get("responsibilities") or []), 1),
			"responsibilities": [
				{"supervisor": role.supervisor, "work_area": role.work_area}
				for role in self.get("responsibilities") or []
			],
			"items": [
				{
					key: row.get(key)
					for key in (
						"template",
						"item_code",
						"item_name",
						"schedule_date",
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
		for row in self.items:
			roles = self.get("responsibilities") or [
				frappe._dict(name=None, supervisor=row.supervisor, work_area="Production")
			]
			for date in schedule_dates(self, row.schedule_date):
				for role in roles:
					doc = frappe.get_doc(
						{
							"doctype": ASSIGNMENT,
							"schedule": self.name,
							"schedule_item": row.name,
							"responsibility": role.name,
							"occurrence_key": f"{self.name}:{row.name}:{date.isoformat()}:{role.name or 'default'}",
							"company": self.company,
							"template": row.template,
							"item_code": row.item_code,
							"item_name": row.item_name,
							"supervisor": role.supervisor,
							"work_area": role.work_area,
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
			"schedule_date",
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
		source_keys = (
			"name",
			"template",
			"item_code",
			"schedule_date",
			"qty_per_occurrence",
			"uom",
			"supervisor",
		)
		if [[row.get(key) for key in source_keys] for row in self.items] != [
			[row.get(key) for key in source_keys] for row in previous.items
		]:
			frappe.throw(
				_(
					"Submitted schedule items cannot be changed. Amend the schedule or adjust a dated assignment."
				)
			)
		role_keys = ("name", "supervisor", "work_area")
		if [[row.get(key) for key in role_keys] for row in self.get("responsibilities") or []] != [
			[row.get(key) for key in role_keys] for row in previous.get("responsibilities") or []
		]:
			frappe.throw(
				_(
					"Submitted responsibilities cannot be changed. Amend the schedule to change the work areas."
				)
			)
		for role, old_role in zip(
			self.get("responsibilities") or [], previous.get("responsibilities") or [], strict=True
		):
			role.status, role.percent_completed = old_role.status, old_role.percent_completed
		for key in ("status", "percent_completed", "total_items", "remaining_items", "occurrence_count"):
			self.set(key, previous.get(key))
		for row, old in zip(self.items, previous.items, strict=True):
			for key in ("planned_qty", "completed_qty", "remaining_qty", "percent_completed", "item_name"):
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
