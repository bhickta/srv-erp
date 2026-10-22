from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from srv_erp.selling.overdue_reminders import overdue_milestone, recipients, send_overdue_reminders


def order(**values):
	return frappe._dict(
		{
			"doctype": "Sales Order",
			"name": "SO-REMINDER",
			"owner": "Administrator",
			"docstatus": 1,
			"status": "To Deliver and Bill",
			"delivery_date": "2026-10-01",
			"items": [frappe._dict(qty=10, delivered_qty=0, delivery_date="2026-10-01")],
			**values,
		}
	)


class TestOverdueMilestones(TestCase):
	def test_first_reminder_at_five_days_and_each_five_day_bucket(self):
		self.assertIsNone(overdue_milestone(order(), "2026-10-05"))
		for day, expected in ((6, 5), (10, 5), (11, 10), (16, 15)):
			self.assertEqual(overdue_milestone(order(), f"2026-10-{day:02}")[2], expected)

	def test_earliest_pending_item_date_and_header_fallback(self):
		doc = order(
			items=[
				frappe._dict(qty=10, delivered_qty=10, delivery_date="2026-09-01"),
				frappe._dict(qty=10, delivered_qty=4, delivery_date="2026-10-05"),
				frappe._dict(qty=10, delivered_qty=0, delivery_date="2026-10-09"),
			]
		)
		self.assertEqual(str(overdue_milestone(doc, "2026-10-10")[0]), "2026-10-05")
		doc["items"][1].delivery_date = None
		self.assertEqual(str(overdue_milestone(doc, "2026-10-10")[0]), "2026-10-01")

	def test_inactive_fully_delivered_and_non_delivery_orders_are_skipped(self):
		for values in (
			{"docstatus": 0},
			{"docstatus": 2},
			{"status": "Closed"},
			{"status": "On Hold"},
			{"skip_delivery_note": 1},
			{"items": [frappe._dict(qty=10, delivered_qty=10)]},
		):
			self.assertIsNone(overdue_milestone(order(**values), "2026-10-21"))

	@patch("srv_erp.selling.overdue_reminders.frappe")
	@patch("srv_erp.selling.overdue_reminders.is_notifications_enabled")
	def test_recipients_require_enabled_system_user_read_permission_and_preferences(self, enabled, mock):
		mock.get_all.return_value = ["allowed", "denied", "disabled", "opted-out", "allowed"]
		mock.db.exists.side_effect = lambda _dt, filters: filters["name"] != "disabled"
		mock.has_permission.side_effect = lambda *args, **kwargs: kwargs["user"] != "denied"
		enabled.side_effect = lambda user: user != "opted-out"
		self.assertEqual(recipients(order(owner="allowed")), ["allowed"])


class TestOverdueNotificationLog(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.doc = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"name": "_TEST-SRV-REMINDER-" + frappe.generate_hash(length=8),
				"customer": "_Test Reminder Customer",
				"customer_name": "Reminder Customer",
				"owner": "Administrator",
				"docstatus": 1,
				"status": "To Deliver and Bill",
				"delivery_date": "2026-10-01",
			}
		)
		# Persist only the fields used by the job, independent of site-specific SO workflows.
		self.doc.db_insert()
		row = self.doc.append("items", {"qty": 10, "delivered_qty": 4, "delivery_date": "2026-10-01"})
		row.db_insert()

	def run_job(self, today):
		# Restrict the job to this test order; other fixtures must not receive alerts.
		original = frappe.get_all

		def orders(doctype, *args, **kwargs):
			return [self.doc.name] if doctype == "Sales Order" else original(doctype, *args, **kwargs)

		with (
			patch("srv_erp.selling.overdue_reminders.nowdate", return_value=today),
			patch("srv_erp.selling.overdue_reminders.frappe.get_all", side_effect=orders),
			patch("srv_erp.selling.overdue_reminders.recipients", return_value=["Administrator"]),
			patch("frappe.sendmail") as sendmail,
		):
			count = send_overdue_reminders()
			sendmail.assert_not_called()
		return count

	def test_real_bell_logs_are_deduplicated_at_five_ten_and_fifteen_days(self):
		self.assertEqual(self.run_job("2026-10-05"), 0)
		self.assertEqual(self.run_job("2026-10-06"), 1)
		self.assertEqual(self.run_job("2026-10-06"), 0)
		self.assertEqual(self.run_job("2026-10-07"), 0)
		self.assertEqual(self.run_job("2026-10-11"), 1)
		self.assertEqual(self.run_job("2026-10-16"), 1)
		logs = frappe.get_all(
			"Notification Log",
			filters={"document_name": self.doc.name},
			fields=["type", "read", "document_type", "for_user", "subject"],
		)
		self.assertEqual(len(logs), 3)
		self.assertTrue(
			all(
				log.type == "Alert"
				and not log.read
				and log.for_user == "Administrator"
				and log.document_type == "Sales Order"
				for log in logs
			)
		)
		self.assertTrue(any("15 days overdue" in log.subject for log in logs))

	def test_downtime_sends_latest_milestone_once_and_delivery_stops_alerts(self):
		self.assertEqual(self.run_job("2026-10-13"), 1)
		self.assertEqual(self.run_job("2026-10-14"), 0)
		frappe.db.set_value("Sales Order Item", self.doc.items[0].name, "delivered_qty", 10)
		self.assertEqual(self.run_job("2026-10-16"), 0)
