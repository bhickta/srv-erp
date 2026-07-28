from __future__ import annotations

import frappe
from frappe import _

from srv_erp.srv_erp.report.dsr_common import get_dsr_documents


def execute(filters=None):
	dsr_documents = get_dsr_documents(filters, fields=["name", "date", "sales_person"])
	if not dsr_documents:
		return get_columns(), []

	parent_details = {dsr.name: dsr for dsr in dsr_documents}
	data = []
	for lead in frappe.get_all(
		"DSR Lead",
		filters={
			"parent": ("in", list(parent_details)),
			"parentfield": "lead",
		},
		fields=["parent", "party_name", "town", "contact_number", "remarks", "idx"],
		order_by="parent, idx",
	):
		dsr = parent_details[lead.parent]
		data.append(
			{
				"dsr": dsr.name,
				"sales_person": dsr.sales_person,
				"date": dsr.date,
				"party_name": lead.party_name,
				"town": lead.town,
				"contact_number": lead.contact_number,
				"remarks": lead.remarks,
				"visit_count": 1,
			}
		)

	return get_columns(), data


def get_columns():
	return [
		{
			"label": _("DSR"),
			"fieldname": "dsr",
			"fieldtype": "Link",
			"options": "DSR",
			"width": 180,
		},
		{
			"label": _("Sales Person"),
			"fieldname": "sales_person",
			"fieldtype": "Link",
			"options": "Sales Person",
			"width": 180,
		},
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 110},
		{"label": _("Party Name"), "fieldname": "party_name", "fieldtype": "Data", "width": 180},
		{
			"label": _("Town"),
			"fieldname": "town",
			"fieldtype": "Link",
			"options": "DSR Town",
			"width": 150,
		},
		{"label": _("Contact Number"), "fieldname": "contact_number", "fieldtype": "Data", "width": 130},
		{"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 220},
		{"label": _("Visits"), "fieldname": "visit_count", "fieldtype": "Int", "width": 80},
	]
