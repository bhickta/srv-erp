import frappe
from frappe import _
from frappe.model.document import Document

from srv_erp.production.service import (
	ASSIGNMENT,
	item_context,
	item_dates,
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
			"assignment_count": sum(row.occurrence_count for row in self.items)
			* max(len(self.get("responsibilities") or []), 1),
			"responsibilities": [
				{"supervisor": role.supervisor, "work_area": role.work_area}
				for role in self.get("responsibilities") or []
			],
			"items": [
				{
					"row": row.idx,
					"dates": item_dates(self, row),
					**{
						key: row.get(key)
						for key in (
							"template",
							"item_code",
							"item_name",
							"from_date",
							"to_date",
							"frequency",
							"occurrence_count",
							"supervisor",
							"uom",
							"qty_per_occurrence",
							"planned_qty",
						)
					},
				}
				for row in self.items
			],
		}

	def on_submit(self):
		for row in self.items:
			roles = self.get("responsibilities") or [
				frappe._dict(name=None, supervisor=row.supervisor, work_area="Production")
			]
			for date in item_dates(self, row):
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
				frappe.throw(
					_(
						"Submitted schedule: {0} cannot be changed; amend the schedule to change its defaults."
					).format(self.meta.get_label(key))
				)
		source_keys = (
			"name",
			"template",
			"item_code",
			"schedule_date",
			"from_date",
			"to_date",
			"frequency",
			"interval",
			"recurrence_unit",
			"weekdays",
			"custom_dates",
			"qty_per_occurrence",
			"uom",
			"supervisor",
		)
		if len(self.items) != len(previous.items):
			frappe.throw(
				_("Submitted Items & Date Ranges: rows cannot be added or removed; amend the schedule.")
			)
		for row, old in zip(self.items, previous.items, strict=True):
			changed = [key for key in source_keys if row.get(key) != old.get(key)]
			if changed:
				labels = ", ".join(row.meta.get_label(key) or key for key in changed)
				frappe.throw(
					_(
						"{0}: submitted fields {1} cannot be changed. Amend the schedule or adjust a dated assignment."
					).format(item_context(row), labels)
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
			for key in (
				"planned_qty",
				"completed_qty",
				"remaining_qty",
				"percent_completed",
				"item_name",
				"occurrence_count",
			):
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
