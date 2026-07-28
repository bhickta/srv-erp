from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from srv_erp.srv_erp.report.dsr_common import get_audit_status, get_dsr_documents


def execute(filters=None):
	dsr_documents = get_dsr_documents(
		filters,
		fields=[
			"name",
			"date",
			"sales_person",
			"km_travelled",
			"amount_for_travel",
			"fuel_added",
			"amount_paid",
			"total_amount",
			"payment_audited",
			"payment_rejected",
			"partially_paid",
		],
	)
	data = [
		{
			**dsr,
			"fuel_amount": dsr.amount_paid if dsr.fuel_added else 0,
			"audit_status": get_audit_status(dsr),
		}
		for dsr in dsr_documents
	]
	report_summary = [
		{"label": _("DSRs"), "value": len(data), "datatype": "Int"},
		{
			"label": _("Total Expense"),
			"value": sum(flt(row.total_amount) for row in dsr_documents),
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
		{"label": _("KM Travelled"), "fieldname": "km_travelled", "fieldtype": "Int", "width": 110},
		{
			"label": _("Travel Amount"),
			"fieldname": "amount_for_travel",
			"fieldtype": "Currency",
			"width": 130,
		},
		{"label": _("Fuel Amount"), "fieldname": "fuel_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Total Amount"), "fieldname": "total_amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Audit Status"), "fieldname": "audit_status", "fieldtype": "Data", "width": 120},
	]
