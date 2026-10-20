"""Idempotent conversion of the original one-item production documents."""

import frappe

from srv_erp.production.service import ASSIGNMENT, ENTRY, SCHEDULE, item_dates, refresh_schedule_progress


def execute():
	backfill_operation_links()
	for name in frappe.get_all(SCHEDULE, pluck="name"):
		doc = frappe.get_doc(SCHEDULE, name)
		if not doc.get("items") and doc.template:
			row = doc.append(
				"items",
				{
					"template": doc.template,
					"qty_per_occurrence": doc.qty_per_occurrence,
					"supervisor": doc.supervisor,
					"uom": doc.uom,
				},
			)
			row.set_new_name()
			row.parent, row.parenttype, row.parentfield = doc.name, SCHEDULE, "items"
			row.docstatus = doc.docstatus
			row.db_insert()
			frappe.db.set_value(SCHEDULE, name, "title", doc.template, update_modified=False)
		if len(doc.items) == 1:
			frappe.db.sql(
				"UPDATE `tabSRV Production Assignment` SET schedule_item=%s WHERE schedule=%s AND COALESCE(schedule_item, '')=''",
				(doc.items[0].name, name),
			)
	for name in frappe.get_all(ENTRY, pluck="name"):
		doc = frappe.get_doc(ENTRY, name)
		if not doc.items and doc.assignment:
			source = frappe.get_doc(ASSIGNMENT, doc.assignment)
			previously_produced = max(source.completed_qty - (doc.qty if doc.docstatus == 1 else 0), 0)
			row = doc.append(
				"items",
				{
					"assignment": doc.assignment,
					"template": doc.template,
					"item_code": doc.item_code,
					"qty": doc.qty,
					"uom": doc.uom,
					"supervisor": doc.supervisor,
					"planned_date": source.planned_date,
					"planned_item": source.item_code,
					"planned_qty": source.target_qty,
					"previously_produced_qty": previously_produced,
					"remaining_qty": max(source.target_qty - previously_produced, 0),
				},
			)
			row.set_new_name()
			row.parent, row.parenttype, row.parentfield = doc.name, ENTRY, "items"
			row.docstatus = doc.docstatus
			row.db_insert()
			frappe.db.set_value(
				ENTRY,
				name,
				{
					"schedule": source.schedule,
					"item_count": 1,
					"status": {0: "Draft", 1: "Submitted", 2: "Cancelled"}[doc.docstatus],
				},
				update_modified=False,
			)
	backfill_dates_and_names()
	backfill_item_ranges()
	frappe.db.sql("""UPDATE `tabSRV Production Assignment`
		SET percent_completed=CASE WHEN target_qty>0 THEN ROUND(completed_qty / target_qty * 100, 2) ELSE 0 END""")
	for name in frappe.get_all(SCHEDULE, pluck="name"):
		doc = frappe.get_doc(SCHEDULE, name)
		if doc.docstatus == 0:
			count = len({date for row in doc.items for date in item_dates(doc, row)})
			for row in doc.items:
				planned = row.qty_per_occurrence * len(item_dates(doc, row))
				frappe.db.set_value(
					row.doctype,
					row.name,
					{
						"planned_qty": planned,
						"occurrence_count": row.occurrence_count,
						"remaining_qty": planned,
						"completed_qty": 0,
						"percent_completed": 0,
					},
					update_modified=False,
				)
			frappe.db.set_value(
				SCHEDULE,
				name,
				{
					"title": doc.title or doc.template,
					"total_items": len(doc.items),
					"remaining_items": len(doc.items),
					"occurrence_count": count,
					"percent_completed": 0,
					"status": "Draft",
				},
				update_modified=False,
			)
		else:
			refresh_schedule_progress(name)


def backfill_dates_and_names():
	# Empty responsibility tables preserve historical template ownership. Never
	# regenerate assignments: old entries must retain their original sources.
	frappe.db.sql("""UPDATE `tabSRV Production Schedule`
		SET schedule_date=start_date WHERE schedule_date IS NULL""")
	frappe.db.sql("""UPDATE `tabSRV Production Schedule Item` i
		INNER JOIN `tabSRV Production Schedule` s ON s.name=i.parent
		LEFT JOIN `tabItem` m ON m.name=COALESCE(NULLIF(i.item_code, ''), i.template)
		SET i.schedule_date=COALESCE(i.schedule_date, s.schedule_date),
		i.item_name=COALESCE(NULLIF(i.item_name, ''), m.item_name)""")
	frappe.db.sql("""UPDATE `tabSRV Production Assignment` a
		LEFT JOIN `tabItem` m ON m.name=COALESCE(NULLIF(a.item_code, ''), a.template)
		SET a.work_area=COALESCE(NULLIF(a.work_area, ''), 'Production'),
		a.item_name=COALESCE(NULLIF(a.item_name, ''), m.item_name)""")
	frappe.db.sql("""UPDATE `tabSRV Production Entry Item` i
		INNER JOIN `tabSRV Production Assignment` a ON a.name=i.assignment
		LEFT JOIN `tabItem` m ON m.name=i.item_code
		SET i.work_area=COALESCE(NULLIF(i.work_area, ''), a.work_area),
		i.planned_date=COALESCE(i.planned_date, a.planned_date),
		i.item_name=COALESCE(NULLIF(i.item_name, ''), m.item_name)""")
	frappe.db.sql("""UPDATE `tabSRV Production Entry` e
		INNER JOIN (SELECT parent, MIN(planned_date) schedule_date, MIN(work_area) work_area
		FROM `tabSRV Production Entry Item` GROUP BY parent) i ON i.parent=e.name
		SET e.schedule_date=COALESCE(e.schedule_date, i.schedule_date),
		e.work_area=COALESCE(NULLIF(e.work_area, ''), i.work_area)""")


def backfill_operation_links():
	from srv_erp.production.setup import ensure_operation

	ensure_operation("Production")
	# Preserve submitted source names and history; only create the missing
	# master records. Normal new schedules must select an existing Operation.
	for doctype in (
		"SRV Production Schedule Responsibility",
		ASSIGNMENT,
		ENTRY,
		"SRV Production Entry Item",
	):
		for name in frappe.get_all(doctype, pluck="work_area", distinct=True):
			if name:
				ensure_operation(name)


def backfill_item_ranges():
	# Preserve the historical recurrence for each row. Do not validate overlaps
	# or regenerate assignments for submitted schedules created by older code.
	frappe.db.sql("""UPDATE `tabSRV Production Schedule Item` i
		INNER JOIN `tabSRV Production Schedule` s ON s.name=i.parent
		SET i.from_date=COALESCE(i.from_date, i.schedule_date, s.schedule_date, s.start_date),
		i.to_date=COALESCE(i.to_date, CASE WHEN COALESCE(NULLIF(i.frequency, ''), s.frequency)='Once'
		THEN COALESCE(i.from_date, i.schedule_date, s.schedule_date, s.start_date) ELSE s.end_date END),
		i.frequency=COALESCE(NULLIF(i.frequency, ''), s.frequency),
		i.`interval`=CASE WHEN COALESCE(i.recurrence_unit, '')='' THEN s.`interval` ELSE i.`interval` END,
		i.recurrence_unit=COALESCE(NULLIF(i.recurrence_unit, ''), s.recurrence_unit),
		i.weekdays=COALESCE(i.weekdays, s.weekdays),
		i.custom_dates=COALESCE(i.custom_dates, s.custom_dates)""")
