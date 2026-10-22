"""Planner corrections to generated work without rewriting submitted production."""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime

from srv_erp.production.permissions import company_allowed
from srv_erp.production.service import (
	ASSIGNMENT,
	SCHEDULE,
	lock_schedule,
	planning_date,
	positive_qty,
	refresh_schedule_progress,
	require_planner,
	submitted_qty,
)
from srv_erp.production.setup import validate_supervisor


def active_schedule(name):
	doc = frappe.get_doc(SCHEDULE, name)
	require_planner(doc.company)
	doc.check_permission("write")
	if lock_schedule(name) != 1:
		frappe.throw(_("Schedule {0} must be submitted and active before updating its plan.").format(name))
	return doc


@frappe.whitelist()
def get_plan(schedule):
	active_schedule(schedule)
	rows = frappe.get_all(
		ASSIGNMENT,
		filters={"schedule": schedule, "status": ["!=", "Cancelled"]},
		fields=[
			"name",
			"modified",
			"schedule_item",
			"template",
			"item_code",
			"item_name",
			"work_area",
			"planned_date",
			"supervisor",
			"target_qty",
			"completed_qty",
			"remaining_qty",
			"status",
			"uom",
		],
		order_by="planned_date, template, item_code, work_area, supervisor, name",
		limit_page_length=0,
	)
	for index, row in enumerate(rows, 1):
		row.row_number = index
	return rows


def row_context(index, doc):
	return _("Update row {0}: {1}, {2}, {3} ({4})").format(
		index, doc.item_code or doc.template, doc.work_area, doc.planned_date, doc.name
	)


@frappe.whitelist(methods=["POST"])
def update_plan(schedule, rows, reason):
	doc = active_schedule(schedule)
	rows = frappe.parse_json(rows)
	if not isinstance(rows, list) or not rows or len(rows) > 1000:
		frappe.throw(_("Select between 1 and 1,000 dated plan rows to update."))
	if not isinstance(reason, str) or not reason.strip():
		frappe.throw(_("Enter a reason for updating this plan."))
	# The parent lock is shared by entries, cancellation and individual corrections.
	# Check every row before saving any, then roll back all saves if a hook fails.
	pending, seen = [], set()
	for index, row in enumerate(rows, 1):
		if (
			not isinstance(row, dict)
			or not isinstance(row.get("name"), str)
			or not row["name"]
			or row["name"] in seen
		):
			frappe.throw(_("Update row {0}: missing or repeated assignment reference.").format(index))
		seen.add(row["name"])
		try:
			index = int(row.get("row_number", index))
		except TypeError, ValueError:
			frappe.throw(_("Invalid dated plan row number."))
		if frappe.db.get_value(ASSIGNMENT, row["name"], "schedule") != schedule:
			frappe.throw(
				_(
					"Update row {0}: assignment {1} does not belong to this schedule or no longer exists."
				).format(index, frappe.utils.escape_html(row["name"]))
			)
		try:
			assignment = frappe.get_doc(ASSIGNMENT, row["name"])
		except frappe.DoesNotExistError:
			frappe.throw(
				_("Update row {0}: assignment {1} no longer exists. Reopen Update Plan.").format(
					index, frappe.utils.escape_html(str(row["name"]))
				)
			)
		context = row_context(index, assignment)
		if assignment.schedule != schedule or assignment.status == "Cancelled":
			frappe.throw(_("{0}: this assignment does not belong to the active schedule.").format(context))
		assignment.check_permission("write")
		try:
			fresh = get_datetime(row.get("modified")) == get_datetime(assignment.modified)
		except TypeError, ValueError:
			fresh = False
		completed = submitted_qty(assignment.name)
		if not row.get("modified") or not fresh or flt(row.get("completed_qty"), 6) != completed:
			frappe.throw(
				_("{0}: the plan or recorded production changed. Reopen Update Plan and try again.").format(
					context
				)
			)
		date = planning_date(row.get("planned_date"), _("Schedule Date"), context)
		qty = positive_qty(row.get("target_qty"), context)
		if qty < completed:
			frappe.throw(
				_("{0}: target {1} cannot be below submitted production {2} {3}.").format(
					context, qty, completed, assignment.uom
				)
			)
		validate_supervisor(row.get("supervisor"), context)
		if not company_allowed(doc.company, row["supervisor"]):
			frappe.throw(
				_("{0}: supervisor {1} cannot access company {2}.").format(
					context, row["supervisor"], doc.company
				)
			)
		values = {"planned_date": str(date), "target_qty": qty, "supervisor": row["supervisor"]}
		if any(str(assignment.get(key)) != str(value) for key, value in values.items()):
			pending.append((index, assignment, values))
	if not pending:
		frappe.throw(_("No dates, supervisors or target quantities were changed."))
	check_collisions(schedule, pending)
	frappe.db.savepoint("production_plan_update")
	try:
		for _index, assignment, values in pending:
			assignment.update(values)
			# Each action records a distinct reason even when planners reuse the same explanation.
			assignment.change_reason = f"{reason.strip()}\n[{frappe.utils.now()} · {frappe.session.user}]"
			assignment.flags.defer_schedule_progress = True
			assignment.save(ignore_version=False)
		refresh_schedule_progress(schedule)
		doc.add_comment(
			"Comment",
			_("Plan updated: {0} dated assignment(s). Reason: {1}").format(
				len(pending), frappe.utils.escape_html(reason.strip())
			),
		)
	except Exception:
		frappe.db.rollback(save_point="production_plan_update")
		raise
	return {"updated": len(pending)}


def check_collisions(schedule, pending):
	"""Reject newly introduced collisions; retain existing historical overlaps."""
	all_rows = frappe.get_all(
		ASSIGNMENT,
		filters={"schedule": schedule, "status": ["!=", "Cancelled"]},
		fields=["name", "template", "item_code", "work_area", "supervisor", "planned_date"],
	)
	changes = {assignment.name: (index, values) for index, assignment, values in pending}
	original, final = {}, {}
	for row in all_rows:
		original[row.name] = tuple(
			str(row.get(key) or "")
			for key in ("template", "item_code", "work_area", "supervisor", "planned_date")
		)
		if row.name in changes:
			row.update(changes[row.name][1])
		key = tuple(
			str(row.get(field) or "")
			for field in ("template", "item_code", "work_area", "supervisor", "planned_date")
		)
		for other in final.get(key, []):
			if (row.name in changes or other in changes) and original[row.name] != original[other]:
				frappe.throw(
					_(
						"Date collision: {0} and {1}, item {2}, operation {3}, supervisor {4}, date {5}. Choose separate dates or supervisors."
					).format(
						_("Update row {0} (assignment {1})").format(changes[row.name][0], row.name)
						if row.name in changes
						else _("Existing assignment {0}").format(row.name),
						_("Update row {0} (assignment {1})").format(changes[other][0], other)
						if other in changes
						else _("Existing assignment {0}").format(other),
						row.item_code or row.template,
						row.work_area,
						row.supervisor,
						row.planned_date,
					)
				)
		final.setdefault(key, []).append(row.name)
