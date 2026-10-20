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


def schedule_dates(doc, start_date=None):
	try:
		weekdays = [
			WEEKDAYS.index(value.strip()) for value in (doc.weekdays or "").split(",") if value.strip()
		]
		explicit_dates = (doc.custom_dates or "").split()
		if start_date:
			explicit_dates = [value for value in explicit_dates if getdate(value) >= getdate(start_date)]
		return production_dates(
			start_date or doc.start_date,
			doc.end_date,
			doc.frequency,
			doc.interval or 0,
			doc.recurrence_unit,
			weekdays,
			explicit_dates,
		)
	except (ValueError, TypeError, OverflowError) as exc:
		frappe.throw(_("Invalid production recurrence: {0}").format(str(exc)))


def validate_schedule(doc):
	require_planner(doc.company)
	if not doc.get("items") and doc.get("template"):
		doc.append("items", {"template": doc.template, "qty_per_occurrence": doc.qty_per_occurrence})
	if not doc.get("items"):
		frappe.throw(_("Add at least one item to produce."))
	schedule_dates(doc)
	doc.schedule_date = getdate(doc.get("schedule_date") or doc.start_date)
	if not getdate(doc.start_date) <= doc.schedule_date <= getdate(doc.end_date):
		frappe.throw(_("Schedule Date must be within the schedule date range."))
	seen_responsibilities = set()
	for role in doc.get("responsibilities") or []:
		validate_supervisor(role.supervisor)
		if not company_allowed(doc.company, role.supervisor):
			frappe.throw(_("The assigned user must have access to the schedule company."))
		role.work_area = (role.work_area or "").strip()
		if not role.work_area:
			frappe.throw(_("Select an Operation for each responsibility."))
		if not frappe.db.exists("Operation", role.work_area):
			frappe.throw(_("Select an existing Operation for each responsibility."))
		key = (role.supervisor, role.work_area.casefold())
		if key in seen_responsibilities:
			frappe.throw(_("The same user/work area may only be assigned once."))
		seen_responsibilities.add(key)
		role.status, role.percent_completed = "Planned", 0
	seen = set()
	all_dates = set()
	assignment_count = 0
	for row in doc.items:
		if not row.template:
			frappe.throw(_("Choose a template before selecting a variant."))
		template = frappe.get_doc("Item", row.template)
		template.check_permission("read")
		if template.disabled or not template.has_variants:
			frappe.throw(_("Select an enabled Item template on each row."))
		if row.item_code:
			variant = frappe.get_doc("Item", row.item_code)
			variant.check_permission("read")
			if variant.disabled or variant.has_variants or variant.variant_of != row.template:
				frappe.throw(_("The planned variant must belong to the selected template."))
			if variant.stock_uom != template.stock_uom:
				frappe.throw(_("The planned variant and template must use the same stock UOM."))
		row.supervisor = template.get("custom_production_supervisor")
		if not doc.get("responsibilities"):
			validate_supervisor(row.supervisor)
		row.schedule_date = getdate(row.get("schedule_date") or doc.schedule_date)
		if not getdate(doc.start_date) <= row.schedule_date <= getdate(doc.end_date):
			frappe.throw(_("Each item Schedule Date must be within the schedule date range."))
		key = (row.template, row.item_code or "", row.schedule_date)
		if key in seen:
			frappe.throw(
				_(
					"The same item may only appear once per Schedule Date. Use another date or combine the quantity."
				)
			)
		seen.add(key)
		row_dates = schedule_dates(doc, row.schedule_date)
		all_dates.update(row_dates)
		assignment_count += len(row_dates) * max(len(doc.get("responsibilities") or []), 1)
		row.item_name = variant.item_name if row.item_code else template.item_name
		row.uom = template.stock_uom
		row.qty_per_occurrence = positive_qty(row.qty_per_occurrence)
		row.planned_qty = flt(row.qty_per_occurrence * len(row_dates), 6)
		row.completed_qty = row.percent_completed = 0
		row.remaining_qty = row.planned_qty
	doc.title = doc.get("title") or doc.items[0].template
	doc.total_items = doc.remaining_items = len(doc.items)
	if assignment_count > 1000:
		frappe.throw(
			_("A schedule may contain at most 1,000 dated item assignments, including responsibilities.")
		)
	doc.occurrence_count = len(all_dates)
	doc.percent_completed = 0
	doc.status = "Draft"
	# Retain legacy values for older API clients; all calculations use child rows.
	doc.template, doc.supervisor, doc.uom = (
		doc.items[0].get(key) for key in ("template", "supervisor", "uom")
	)
	doc.qty_per_occurrence = doc.items[0].qty_per_occurrence
	if doc.get("responsibilities"):
		doc.supervisor = doc.responsibilities[0].supervisor
	return sorted(all_dates)


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
		"""SELECT i.qty FROM `tabSRV Production Entry Item` i
		INNER JOIN `tabSRV Production Entry` e ON e.name=i.parent
		WHERE i.assignment=%s AND e.docstatus=1 AND e.name != %s FOR UPDATE""",
		(assignment, exclude or ""),
	)
	# Supports the interval between schema synchronization and legacy backfill.
	legacy = frappe.db.sql(
		"""SELECT e.qty FROM `tabSRV Production Entry` e
		WHERE e.assignment=%s AND e.docstatus=1 AND e.name != %s
		AND NOT EXISTS (SELECT 1 FROM `tabSRV Production Entry Item` i WHERE i.parent=e.name)
		FOR UPDATE""",
		(assignment, exclude or ""),
	)
	return flt(sum(row[0] for row in [*rows, *legacy]), 6)


def refresh_schedule_progress(schedule):
	rows = frappe.db.sql(
		"""SELECT schedule_item, responsibility, occurrence_key, target_qty, completed_qty, status, planned_date
		FROM `tabSRV Production Assignment` WHERE schedule=%s FOR UPDATE""",
		schedule,
		as_dict=True,
	)
	grouped = {}
	for row in rows:
		grouped.setdefault(row.schedule_item, []).append(row)
	remaining_items = 0
	for name, item_rows in grouped.items():
		by_date = {}
		for row in item_rows:
			# The generated occurrence stays stable when a planner moves one
			# operation to another date; it is still the same physical output.
			prefix = f"{schedule}:{row.schedule_item}:"
			occurrence = (
				row.occurrence_key.removeprefix(prefix).split(":")[0]
				if row.occurrence_key and row.occurrence_key.startswith(prefix)
				else row.planned_date
			)
			by_date.setdefault(occurrence, []).append(row)
		# Each stage works on the same planned units; do not multiply the item
		# quantity by the number of users/operations. Finished quantity requires
		# work from every responsibility for that dated item.
		planned = sum(min(row.target_qty for row in group) for group in by_date.values())
		completed = sum(
			min(min(row.completed_qty, row.target_qty) for row in group) for group in by_date.values()
		)
		values = {
			"planned_qty": flt(planned, 6),
			"completed_qty": flt(completed, 6),
			"remaining_qty": flt(max(planned - completed, 0), 6),
			"percent_completed": completion_percent(item_rows),
		}
		remaining_items += any(row.completed_qty < row.target_qty for row in item_rows)
		if name:
			frappe.db.set_value("SRV Production Schedule Item", name, values, update_modified=False)
	docstatus = frappe.db.get_value(SCHEDULE, schedule, "docstatus")
	for role in frappe.get_all(
		"SRV Production Schedule Responsibility", filters={"parent": schedule}, pluck="name"
	):
		role_rows = [row for row in rows if row.responsibility == role]
		status = (
			"Cancelled"
			if docstatus == 2
			else (
				"Completed"
				if role_rows and all(row.completed_qty >= row.target_qty for row in role_rows)
				else "In Progress"
				if any(row.completed_qty > 0 for row in role_rows)
				else "Planned"
			)
		)
		frappe.db.set_value(
			"SRV Production Schedule Responsibility",
			role,
			{"status": status, "percent_completed": completion_percent(role_rows)},
			update_modified=False,
		)
	status = (
		"Cancelled"
		if docstatus == 2
		else "Draft"
		if docstatus == 0
		else (
			"Completed"
			if rows and all(row.completed_qty >= row.target_qty for row in rows)
			else "Partly Produced"
			if any(row.completed_qty > 0 for row in rows)
			else "To Produce"
		)
	)
	frappe.db.set_value(
		SCHEDULE,
		schedule,
		{
			"status": status,
			"percent_completed": completion_percent(rows),
			"remaining_items": remaining_items,
			"total_items": len(grouped),
			"occurrence_count": len({row.planned_date for row in rows}),
		},
	)


def completion_percent(rows):
	return (
		flt(sum(min(row.completed_qty / row.target_qty, 1) for row in rows) * 100 / len(rows), 2)
		if rows
		else 0
	)


def update_progress(assignment, cancelled=False, refresh_schedule=True):
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
			"percent_completed": flt(100 * completed / assignment.target_qty, 2),
			"status": status,
		},
	)
	if refresh_schedule:
		refresh_schedule_progress(assignment.schedule)


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
			"item_code",
			"planned_date",
			"supervisor",
			"work_area",
			"target_qty",
			"completed_qty",
			"uom",
			"status",
		],
		limit_page_length=0,
		order_by="planned_date asc",
	)
	for row in events:
		row.calendar_title = f"{row.item_code or row.template} · {row.work_area or 'Production'}: {row.completed_qty:g}/{row.target_qty:g} {row.uom}"
		row.calendar_editable = False
		row.convert_to_user_tz = 0
	return events


@frappe.whitelist()
def get_assignment_details(assignment):
	doc = frappe.get_doc(ASSIGNMENT, assignment)
	doc.check_permission("read")
	return {
		key: doc.get(key)
		for key in (
			"company",
			"template",
			"item_code",
			"supervisor",
			"work_area",
			"item_name",
			"uom",
			"remaining_qty",
			"target_qty",
			"completed_qty",
			"planned_date",
			"schedule",
		)
	}


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
		if field.fieldtype == "Table":
			previous = doc.get_doc_before_save()

			def values(rows):
				return [
					{
						key: value
						for key, value in row.as_dict(
							convert_dates_to_str=True, no_private_properties=True
						).items()
						if key not in ("docstatus", "creation", "modified", "modified_by")
					}
					for row in rows
				]

			changed = values(doc.get(field.fieldname)) != values(previous.get(field.fieldname))
		else:
			changed = field.fieldtype not in (
				"HTML",
				"Section Break",
				"Column Break",
			) and doc.has_value_changed(field.fieldname)
		if changed:
			frappe.throw(
				_("Submitted production field {0} cannot be changed during cancellation.").format(
					field.fieldname
				)
			)


@frappe.whitelist()
def get_pending_options(schedule):
	frappe.has_permission(ENTRY, "create", throw=True)
	rows = frappe.get_list(
		ASSIGNMENT,
		filters={"schedule": schedule, "remaining_qty": [">", 0], "status": ["!=", "Cancelled"]},
		fields=["name", "supervisor", "work_area", "planned_date"],
		limit_page_length=0,
		order_by="planned_date",
	)
	if not rows:
		frappe.throw(_("There are no pending items available to you in this schedule."))
	return {
		"supervisors": sorted({row.supervisor for row in rows}),
		"dates": sorted({str(row.planned_date) for row in rows}),
		"responsibilities": [
			dict(supervisor=user, work_area=area or "Production")
			for user, area in sorted({(row.supervisor, row.work_area or "Production") for row in rows})
		],
	}


@frappe.whitelist()
def make_production_entry(source_name, supervisor=None, planned_date=None, assignment=None, work_area=None):
	frappe.has_permission(ENTRY, "create", throw=True)
	args = frappe.flags.args or {}
	supervisor = supervisor or args.get("supervisor")
	planned_date = planned_date or args.get("planned_date")
	assignment = assignment or args.get("assignment")
	work_area = work_area or args.get("work_area")
	filters = {"schedule": source_name, "remaining_qty": [">", 0], "status": ["!=", "Cancelled"]}
	selected = (frappe.flags.selected_children or {}).get("items")
	if selected:
		filters["schedule_item"] = ["in", selected]
	if supervisor:
		filters["supervisor"] = supervisor
	if work_area:
		filters["work_area"] = work_area
	if planned_date:
		filters["planned_date"] = getdate(planned_date)
	if assignment:
		filters["name"] = assignment
	if lock_schedule(source_name) != 1:
		frappe.throw(_("Only submitted schedules can create production entries."))
	rows = frappe.get_list(
		ASSIGNMENT,
		filters=filters,
		fields=["name", "supervisor", "work_area", "planned_date"],
		limit_page_length=0,
		order_by="planned_date, creation",
	)
	if not rows:
		frappe.throw(_("No pending production items match this selection."))
	if len({row.supervisor for row in rows}) != 1:
		frappe.throw(_("Select one supervisor when creating the production entry."))
	if len({row.work_area or "Production" for row in rows}) != 1:
		frappe.throw(_("Select one work area when creating the production entry."))
	doc = frappe.new_doc(ENTRY)
	doc.schedule = source_name
	doc.production_date = nowdate()
	for row in rows:
		source, _status = lock_assignment(row.name)
		source.check_permission("read")
		remaining = flt(max(source.target_qty - submitted_qty(source.name), 0), 6)
		if remaining <= 0:
			continue
		doc.company, doc.supervisor, doc.work_area = (
			source.company,
			source.supervisor,
			source.work_area or "Production",
		)
		doc.append(
			"items",
			{
				"assignment": source.name,
				"template": source.template,
				"item_code": source.item_code,
				"item_name": frappe.db.get_value("Item", source.item_code or source.template, "item_name"),
				"work_area": source.work_area or "Production",
				"planned_item": source.item_code,
				"supervisor": source.supervisor,
				"planned_date": source.planned_date,
				"planned_qty": source.target_qty,
				"previously_produced_qty": flt(source.target_qty - remaining, 6),
				"remaining_qty": remaining,
				"qty": remaining,
				"uom": source.uom,
			},
		)
	if not doc.items:
		frappe.throw(_("All selected production items have already been completed."))
	doc.item_count = len(doc.items)
	doc.schedule_date = min(getdate(row.planned_date) for row in doc.items)
	return doc
