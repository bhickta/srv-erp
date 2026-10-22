"""Five-day delivery reminders in the Desk notification bell."""

import hashlib

import frappe
from frappe import _
from frappe.desk.doctype.notification_settings.notification_settings import is_notifications_enabled
from frappe.utils import date_diff, escape_html, flt, getdate, nowdate

INTERVAL_DAYS = 5
INACTIVE_STATUSES = {"Closed", "On Hold", "Cancelled"}


def overdue_milestone(doc, today):
	if doc.docstatus != 1 or doc.status in INACTIVE_STATUSES:
		return None
	# Header percentages can be rounded to 100 while a row still has a balance.
	pending = [row for row in doc.get("items") or [] if flt(row.delivered_qty, 6) < flt(row.qty, 6)]
	if not pending or doc.get("skip_delivery_note"):
		return None
	dates = [
		getdate(row.delivery_date or doc.delivery_date)
		for row in pending
		if row.delivery_date or doc.delivery_date
	]
	if not dates:
		return None
	due_date = min(dates)
	days = date_diff(today, due_date)
	if days < INTERVAL_DAYS:
		return None
	return due_date, days, days // INTERVAL_DAYS * INTERVAL_DAYS


def recipients(doc):
	users = {doc.owner}
	users.update(
		frappe.get_all(
			"ToDo",
			filters={"reference_type": "Sales Order", "reference_name": doc.name, "status": "Open"},
			pluck="allocated_to",
		)
	)
	return [
		user
		for user in sorted(users - {None, "Guest"})
		if frappe.db.exists("User", {"name": user, "enabled": 1, "user_type": "System User"})
		and frappe.has_permission("Sales Order", "read", doc=doc, user=user)
		and is_notifications_enabled(user)
	]


def send_overdue_reminders():
	"""A delayed run sends the latest milestone once, rather than an old-reminder burst."""
	today = nowdate()
	count = 0
	for name in frappe.get_all(
		"Sales Order", filters={"docstatus": 1, "status": ["not in", list(INACTIVE_STATUSES)]}, pluck="name"
	):
		# Serialize against concurrent runs and recalculate balances after locking.
		doc = frappe.get_doc("Sales Order", name, for_update=True)
		milestone = overdue_milestone(doc, today)
		if not milestone:
			continue
		due_date, days, interval = milestone
		for user in recipients(doc):
			key = hashlib.sha256(f"srv-so-overdue:{name}:{due_date}:{interval}:{user}".encode()).hexdigest()
			if frappe.db.exists("Notification Log", key):
				continue
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"type": "Alert",
					"subject": _("Sales Order {0} is {1} days overdue ({2}-day reminder)").format(
						escape_html(name), days, interval
					),
					"for_user": user,
					"from_user": "Administrator",
					"document_type": "Sales Order",
					"document_name": name,
					"email_content": _(
						"Customer: {0}. Undelivered items were due on {1}. Open the Sales Order to review the remaining quantities."
					).format(escape_html(doc.customer_name or doc.customer), due_date),
				}
			).insert(ignore_permissions=True, set_name=key)
			count += 1
	return count
