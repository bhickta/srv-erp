from __future__ import annotations

import frappe


def get_dsr_documents(filters=None, fields=None):
	filters = frappe._dict(filters or {})
	query_filters = {"docstatus": 1}

	if filters.get("sales_person"):
		query_filters["sales_person"] = filters.sales_person
	if filters.get("from_date"):
		query_filters["date"] = (">=", filters.from_date)
	if filters.get("to_date"):
		query_filters.setdefault("date", ("<=", filters.to_date))
		if filters.get("from_date"):
			query_filters["date"] = ("between", [filters.from_date, filters.to_date])

	audit_status = filters.get("audit_status")
	if audit_status == "Paid":
		query_filters["payment_audited"] = 1
	elif audit_status == "Rejected":
		query_filters["payment_rejected"] = 1
	elif audit_status == "Partially Paid":
		query_filters["partially_paid"] = 1
	elif audit_status == "Pending":
		query_filters.update(
			{
				"payment_audited": 0,
				"payment_rejected": 0,
				"partially_paid": 0,
			}
		)

	return frappe.get_list(
		"DSR",
		filters=query_filters,
		fields=fields or ["name", "date", "sales_person"],
		limit_page_length=0,
		order_by="date desc, creation desc",
	)


def get_audit_status(dsr) -> str:
	if dsr.payment_rejected:
		return "Rejected"
	if dsr.partially_paid:
		return "Partially Paid"
	if dsr.payment_audited:
		return "Paid"
	return "Pending"
