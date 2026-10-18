"""Idempotent conversion of the original one-item production documents."""

import frappe

from srv_erp.production.service import ASSIGNMENT, ENTRY, SCHEDULE, refresh_schedule_progress


def execute():
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
	frappe.db.sql("""UPDATE `tabSRV Production Assignment`
		SET percent_completed=CASE WHEN target_qty>0 THEN ROUND(completed_qty / target_qty * 100, 2) ELSE 0 END""")
	for name in frappe.get_all(SCHEDULE, pluck="name"):
		doc = frappe.get_doc(SCHEDULE, name)
		if doc.docstatus == 0:
			from srv_erp.production.service import schedule_dates

			count = len(schedule_dates(doc))
			for row in doc.items:
				planned = row.qty_per_occurrence * count
				frappe.db.set_value(
					row.doctype,
					row.name,
					{
						"planned_qty": planned,
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
