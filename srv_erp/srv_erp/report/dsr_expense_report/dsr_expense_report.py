from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from srv_erp.srv_erp.report.dsr_common import get_audit_status, get_dsr_documents


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	total = sum(flt(row.amount) for row in data)
	report_summary = [
		{
			"label": _("Expense Rows"),
			"value": len(data),
			"datatype": "Int",
		},
		{
			"label": _("Total Amount"),
			"value": total,
			"datatype": "Currency",
		},
	]
	return get_columns(), data, None, None, report_summary


def get_columns():
	return [
		{
			"label": _("DSR"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "DSR",
			"width": 180,
		},
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 110},
		{
			"label": _("Sales Person"),
			"fieldname": "sales_person",
			"fieldtype": "Link",
			"options": "Sales Person",
			"width": 180,
		},
		{"label": _("Start Reading"), "fieldname": "start_reading", "fieldtype": "Int", "width": 110},
		{"label": _("End Reading"), "fieldname": "end_reading", "fieldtype": "Int", "width": 110},
		{"label": _("KM Travelled"), "fieldname": "km_travelled", "fieldtype": "Int", "width": 110},
		{"label": _("Expense Type"), "fieldname": "type", "fieldtype": "Data", "width": 160},
		{"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 220},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Audit Status"), "fieldname": "audit_status", "fieldtype": "Data", "width": 120},
	]


def get_data(filters):
	dsr_documents = get_dsr_documents(
		filters,
		fields=[
			"name",
			"date",
			"sales_person",
			"start_reading",
			"end_reading",
			"km_travelled",
			"amount_for_travel",
			"fuel_added",
			"amount_paid",
			"payment_audited",
			"payment_rejected",
			"partially_paid",
		],
	)
	if not dsr_documents:
		return []

	expenses_by_parentfield = defaultdict(list)
	for expense in frappe.get_all(
		"DSR Expense",
		filters={
			"parent": ("in", [dsr.name for dsr in dsr_documents]),
			"parentfield": "daily_sales_expenses_by_admin",
		},
		fields=["parent", "parentfield", "type", "amount", "description", "idx"],
		order_by="parent, parentfield, idx",
	):
		expenses_by_parentfield[(expense.parent, expense.parentfield)].append(expense)

	for expense in frappe.get_all(
		"DSR Approved Expense",
		filters={
			"parent": ("in", [dsr.name for dsr in dsr_documents]),
			"parentfield": "daily_sales_expense_by_admin_approved_amount",
		},
		fields=["parent", "parentfield", "type", "amount", "description", "idx"],
		order_by="parent, parentfield, idx",
	):
		expenses_by_parentfield[(expense.parent, expense.parentfield)].append(expense)

	data = []
	for dsr in dsr_documents:
		common = {
			"name": dsr.name,
			"date": dsr.date,
			"sales_person": dsr.sales_person,
			"start_reading": dsr.start_reading,
			"end_reading": dsr.end_reading,
			"km_travelled": dsr.km_travelled,
			"audit_status": get_audit_status(dsr),
		}
		data.append({**common, "type": _("Travel"), "amount": dsr.amount_for_travel})

		if dsr.fuel_added:
			data.append({**common, "type": _("Fuel"), "amount": dsr.amount_paid})

		parentfield = (
			"daily_sales_expense_by_admin_approved_amount"
			if dsr.partially_paid
			else "daily_sales_expenses_by_admin"
		)
		expense_rows = expenses_by_parentfield[(dsr.name, parentfield)]
		if filters.get("group_by_expense_type"):
			grouped = defaultdict(float)
			for expense in expense_rows:
				grouped[expense.type] += flt(expense.amount)
			data.extend(
				{**common, "type": expense_type, "amount": amount} for expense_type, amount in grouped.items()
			)
		else:
			data.extend(
				{
					**common,
					"type": expense.type,
					"description": expense.description,
					"amount": expense.amount,
				}
				for expense in expense_rows
			)

	return data
