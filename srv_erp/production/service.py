import math

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from srv_erp.production.permissions import company_allowed, is_planner
from srv_erp.production.recurrence import production_dates
from srv_erp.production.setup import validate_supervisor

SCHEDULE = "SRV Production Schedule"
ASSIGNMENT = "SRV Production Assignment"
ENTRY = "SRV Production Entry"
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def positive_qty(value):
	try:
		number = float(value)
	except TypeError, ValueError:
		number = 0
	if not math.isfinite(number) or flt(number, 6) <= 0:
		frappe.throw(_("Quantity must be a positive finite number (minimum 0.000001)."))
	return flt(number, 6)


def require_planner(company):
	if not is_planner() or not company_allowed(company):
		frappe.throw(
			_("Only a production planner for this company can perform this action."), frappe.PermissionError
		)


def schedule_dates(doc):
	try:
		weekdays = [
			WEEKDAYS.index(value.strip()) for value in (doc.weekdays or "").split(",") if value.strip()
		]
		return production_dates(
			doc.start_date,
			doc.end_date,
			doc.frequency,
			doc.interval or 0,
			doc.recurrence_unit,
			weekdays,
			(doc.custom_dates or "").split(),
		)
	except (ValueError, TypeError, OverflowError) as exc:
		frappe.throw(_("Invalid production recurrence: {0}").format(str(exc)))


def validate_schedule(doc):
	require_planner(doc.company)
	item = frappe.get_doc("Item", doc.template)
	item.check_permission("read")
	if not item.has_variants or item.disabled:
		frappe.throw(_("Select an enabled Item template."))
	doc.supervisor = item.get("custom_production_supervisor")
	validate_supervisor(doc.supervisor)
	doc.uom = item.stock_uom
	doc.qty_per_occurrence = positive_qty(doc.qty_per_occurrence)
	return schedule_dates(doc)


def lock_schedule(name):
	rows = frappe.db.sql("SELECT docstatus FROM `tabSRV Production Schedule` WHERE name=%s FOR UPDATE", name)
	if not rows:
		frappe.throw(_("Production schedule not found."))
	return rows[0][0]


def lock_assignment(name):
	# Always lock the parent first, including cancellation and reassignment paths.
	schedule = frappe.db.get_value(ASSIGNMENT, name, "schedule")
	if not schedule:
		frappe.throw(_("Production assignment not found."))
	docstatus = lock_schedule(schedule)
	frappe.db.sql("SELECT name FROM `tabSRV Production Assignment` WHERE name=%s FOR UPDATE", name)
	return frappe.get_doc(ASSIGNMENT, name, for_update=True), docstatus


def submitted_qty(assignment, exclude=None):
	rows = frappe.db.sql(
		"""SELECT qty FROM `tabSRV Production Entry`
		WHERE assignment=%s AND docstatus=1 AND name != %s FOR UPDATE""",
		(assignment, exclude or ""),
	)
	return flt(sum(row[0] for row in rows), 6)


def update_progress(assignment, cancelled=False):
	completed = submitted_qty(assignment.name)
	status = (
		"Cancelled"
		if cancelled
		else (
			"Completed" if completed >= assignment.target_qty else "In Progress" if completed else "Planned"
		)
	)
	frappe.db.set_value(
		ASSIGNMENT,
		assignment.name,
		{
			"completed_qty": completed,
			"remaining_qty": flt(max(assignment.target_qty - completed, 0), 6),
			"status": status,
		},
	)


@frappe.whitelist()
def get_events(start, end, filters=None, **kwargs):
	# get_list applies both query hooks and normal Frappe user permissions.
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters
	if filters is None:
		filters = []
	if isinstance(filters, dict):
		filters = [[key, "=", value] for key, value in filters.items()]
	filters = [*filters, ["planned_date", ">=", getdate(start)], ["planned_date", "<", getdate(end)]]
	events = frappe.get_list(
		ASSIGNMENT,
		filters=filters,
		fields=[
			"name",
			"template",
			"planned_date",
			"supervisor",
			"target_qty",
			"completed_qty",
			"uom",
			"status",
		],
		limit_page_length=0,
		order_by="planned_date asc",
	)
	for row in events:
		row.calendar_title = f"{row.template}: {row.completed_qty:g}/{row.target_qty:g} {row.uom}"
		row.calendar_editable = False
		row.convert_to_user_tz = 0
	return events


@frappe.whitelist()
def get_assignment_details(assignment):
	doc = frappe.get_doc(ASSIGNMENT, assignment)
	doc.check_permission("read")
	return {key: doc.get(key) for key in ("company", "template", "supervisor", "uom", "remaining_qty")}


def validate_production_date(value):
	if getdate(value) > getdate(nowdate()):
		frappe.throw(_("Production cannot be recorded for a future date."))


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def supervisor_query(doctype, txt, searchfield, start, page_len, filters):
	if not is_planner() and not frappe.has_permission("Item", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return frappe.db.sql(
		"""SELECT DISTINCT u.name, u.full_name FROM `tabUser` u
		INNER JOIN `tabHas Role` r ON r.parent=u.name AND r.parenttype='User'
		WHERE u.enabled=1 AND u.user_type='System User' AND r.role=%s
		AND (u.name LIKE %s OR u.full_name LIKE %s)
		ORDER BY u.name LIMIT %s OFFSET %s""",
		("SRV Production Supervisor", f"%{txt}%", f"%{txt}%", page_len, start),
	)


def prevent_cancel_edits(doc):
	# Frappe intentionally skips validate() on cancellation. Keep submitted
	# production and source fields immutable on that path as well.
	for field in doc.meta.fields:
		if field.fieldtype not in ("HTML", "Section Break", "Column Break") and doc.has_value_changed(
			field.fieldname
		):
			frappe.throw(_("Submitted production fields cannot be changed during cancellation."))
