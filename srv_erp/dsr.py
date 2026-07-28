from __future__ import annotations

from datetime import datetime, time, timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime, getdate, now_datetime

PRIVILEGED_ROLES = {"Administrator", "System Manager"}


def validate_dsr_submission_deadline(doc) -> None:
	"""Apply the configured DSR backdate rule, if one exists."""
	if PRIVILEGED_ROLES.intersection(frappe.get_roles()):
		return

	report_date = getdate(doc.date)
	today = getdate(now_datetime())
	if report_date > today:
		frappe.throw(_("A DSR cannot be submitted for a future date."))

	rule = get_dsr_submission_rule()
	if not rule:
		return

	tolerance = max(float(rule.tolerance or 0), 0)
	if rule.unit == "Hours":
		deadline = get_datetime(datetime.combine(report_date, time.min)) + timedelta(hours=tolerance)
	else:
		deadline_date = add_working_days(report_date, int(tolerance))
		deadline = get_datetime(datetime.combine(deadline_date, time.max))

	if now_datetime() > deadline:
		frappe.throw(
			_("The submission deadline for this DSR was {0}.").format(
				frappe.format(deadline, {"fieldtype": "Datetime"})
			)
		)


def get_dsr_submission_rule():
	meta = frappe.get_meta("SRV Settings")
	if not meta.has_field("dsr_submission_rules"):
		return None

	settings = frappe.get_single("SRV Settings")
	for rule in settings.get("dsr_submission_rules") or []:
		if rule.document_type == "DSR":
			return rule
	return None


def add_working_days(start_date, working_days: int):
	current_date = getdate(start_date)
	holidays = get_company_holidays()
	days_added = 0

	while days_added < working_days:
		current_date += timedelta(days=1)
		if current_date.weekday() == 6 or current_date in holidays:
			continue
		days_added += 1

	return current_date


def get_company_holidays() -> set:
	company = frappe.defaults.get_user_default("company") or frappe.get_cached_value(
		"Global Defaults", None, "default_company"
	)
	if not company:
		return set()

	holiday_list = frappe.get_cached_value("Company", company, "default_holiday_list")
	if not holiday_list:
		return set()

	return {
		getdate(row.holiday_date)
		for row in frappe.get_all("Holiday", filters={"parent": holiday_list}, fields=["holiday_date"])
	}
