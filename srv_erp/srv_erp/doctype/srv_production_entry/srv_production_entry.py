from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import escape_html, flt, getdate

from srv_erp.production.permissions import assignment_permission, entry_permission, is_planner
from srv_erp.production.service import (
	ASSIGNMENT,
	ENTRY,
	lock_assignment,
	lock_schedule,
	positive_qty,
	prevent_cancel_edits,
	refresh_schedule_progress,
	submitted_qty,
	update_progress,
	validate_production_date,
)


class SRVProductionEntry(Document):
	def _save(self, *args, **kwargs):
		if not self.is_new():
			schedule = frappe.db.get_value(ENTRY, self.name, "schedule")
			if schedule:
				lock_schedule(schedule)
			original = frappe.get_doc(ENTRY, self.name, for_update=True)
			if not entry_permission(original, "write"):
				frappe.throw(_("Not permitted for this production entry."), frappe.PermissionError)
			if self.schedule != original.schedule or self.assignment != original.assignment:
				frappe.throw(_("The source of an existing production entry cannot be changed."))
		return super()._save(*args, **kwargs)

	def validate(self):
		if not self.get("items") and self.assignment:
			self.append(
				"items", {"assignment": self.assignment, "item_code": self.item_code, "qty": self.qty}
			)
		if not self.get("items"):
			frappe.throw(_("Create a production entry from the schedule's pending items."))
		assignments = self.lock_sources()
		supervisors = {doc.supervisor for doc in assignments.values()}
		if len(supervisors) != 1:
			frappe.throw(_("Create a separate production entry for each supervisor."))
		if len({source.work_area or "Production" for source in assignments.values()}) != 1:
			frappe.throw(_("Create a separate production entry for each work area."))
		for row in self.items:
			source = assignments[row.assignment]
			context = _("Entry row {0} ({1}, scheduled {2}, {3})").format(
				row.idx,
				escape_html(row.item_code or source.template),
				source.planned_date,
				escape_html(source.work_area or "Production"),
			)
			if not row.item_code:
				frappe.throw(context + ": " + _("Select a produced variant."))
			item = frappe.get_doc("Item", row.item_code)
			item.check_permission("read")
			if item.disabled or item.has_variants or item.variant_of != source.template:
				frappe.throw(
					context
					+ ": "
					+ _("Select an enabled variant of template {0}.").format(escape_html(source.template))
				)
			if source.item_code and item.name != source.item_code:
				frappe.throw(
					context
					+ ": "
					+ _("Production must use planned variant {0}.").format(escape_html(source.item_code))
				)
			if item.stock_uom != source.uom:
				frappe.throw(
					context
					+ ": "
					+ _("Produced variants must use planned UOM {0}.").format(escape_html(source.uom))
				)
			row.qty = positive_qty(row.qty, context + _(" — Produced Qty"))
			row.item_name = item.item_name
			row.work_area = source.work_area or "Production"
			row.template, row.planned_item = source.template, source.item_code
			row.supervisor, row.uom, row.planned_date = source.supervisor, source.uom, source.planned_date
			row.planned_qty = source.target_qty
			row.previously_produced_qty = submitted_qty(source.name, exclude=self.name)
			row.remaining_qty = flt(max(source.target_qty - row.previously_produced_qty, 0), 6)
		first = next(iter(assignments.values()))
		self.company, self.supervisor = first.company, first.supervisor
		self.work_area = first.work_area or "Production"
		self.schedule_date = min(getdate(row.planned_date) for row in self.items)
		self.item_count = len(self.items)
		self.status = "Draft"
		# Legacy snapshots remain available to integrations, hidden from the form.
		self.assignment, self.template, self.item_code, self.uom = (
			self.items[0].assignment,
			self.items[0].template,
			self.items[0].item_code,
			self.items[0].uom,
		)
		self.qty = self.items[0].qty
		validate_production_date(self.production_date)

	def lock_sources(self):
		names = sorted({row.assignment for row in self.items if row.assignment})
		if not names or any(not row.assignment for row in self.items):
			frappe.throw(_("Every output row must reference a dated production assignment."))
		schedule = frappe.db.get_value(ASSIGNMENT, names[0], "schedule")
		if not schedule or (self.schedule and self.schedule != schedule):
			frappe.throw(_("The production entry source schedule does not match its items."))
		self.schedule = schedule
		if lock_schedule(schedule) != 1:
			frappe.throw(_("Production can only be recorded against a submitted schedule."))
		sources = {}
		for name in names:
			# Check parent identity before locking another schedule: one lock order.
			if frappe.db.get_value(ASSIGNMENT, name, "schedule") != schedule:
				frappe.throw(_("All production entry rows must belong to the same schedule."))
			doc, _status = lock_assignment(name)
			if not assignment_permission(doc, "read"):
				frappe.throw(_("Not permitted for one or more planned items."), frappe.PermissionError)
			if doc.status == "Cancelled":
				frappe.throw(_("Cancelled production assignments cannot be fulfilled."))
			sources[name] = doc
		return sources

	def before_submit(self):
		sources = self.lock_sources()
		totals = defaultdict(float)
		for row in self.items:
			totals[row.assignment] += row.qty
		for name, qty in totals.items():
			if flt(submitted_qty(name, exclude=self.name) + qty, 6) > flt(sources[name].target_qty, 6):
				rows = ", ".join(str(row.idx) for row in self.items if row.assignment == name)
				pending = max(sources[name].target_qty - submitted_qty(name, exclude=self.name), 0)
				frappe.throw(
					_(
						"Entry row(s) {0}: item {1}, scheduled {2}, operation {3} has {4} {5} pending; this entry records {6}. Reduce Produced Qty or refresh the entry."
					).format(
						rows,
						escape_html(sources[name].item_code or sources[name].template),
						sources[name].planned_date,
						escape_html(sources[name].work_area or "Production"),
						pending,
						escape_html(sources[name].uom),
						qty,
					)
				)
		self.status = "Submitted"

	def on_submit(self):
		self.update_source_progress()

	def before_cancel(self):
		prevent_cancel_edits(self)
		if not is_planner() or not entry_permission(self, "cancel"):
			frappe.throw(
				_("Only a production planner can cancel production entries."), frappe.PermissionError
			)
		self.lock_sources()
		self.status = "Cancelled"

	def on_cancel(self):
		self.update_source_progress()

	def update_source_progress(self):
		for name in sorted({row.assignment for row in self.items}):
			update_progress(lock_assignment(name)[0], refresh_schedule=False)
		refresh_schedule_progress(self.schedule)
