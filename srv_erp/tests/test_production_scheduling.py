from datetime import date
from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from srv_erp.production import permissions
from srv_erp.production.recurrence import production_dates
from srv_erp.production.service import ASSIGNMENT, ENTRY, SCHEDULE, get_events, submitted_qty
from srv_erp.production.setup import setup_production


class TestProductionRecurrence(TestCase):
	def dates(self, start, end, frequency, **kwargs):
		return [str(value) for value in production_dates(start, end, frequency, **kwargs)]

	def test_inclusive_dates_and_weekdays(self):
		self.assertEqual(self.dates("2026-10-16", "2026-10-19", "Weekdays"), ["2026-10-16", "2026-10-19"])
		self.assertEqual(len(self.dates("2026-10-16", "2026-10-19", "Daily")), 4)
		self.assertEqual(self.dates("2026-10-16", "2026-10-19", "Once"), ["2026-10-16"])

	def test_monthly_preserves_anchor_and_leap_year(self):
		self.assertEqual(
			self.dates("2028-01-31", "2028-04-30", "Monthly"),
			[
				"2028-01-31",
				"2028-02-29",
				"2028-03-31",
				"2028-04-30",
			],
		)

	def test_custom_intervals_and_selected_weekdays(self):
		self.assertEqual(
			self.dates("2026-10-05", "2026-10-23", "Custom", interval=2, unit="Weeks", weekdays=[0, 4]),
			[
				"2026-10-05",
				"2026-10-09",
				"2026-10-19",
				"2026-10-23",
			],
		)
		self.assertEqual(
			self.dates("2026-10-01", "2026-10-07", "Custom", interval=3),
			["2026-10-01", "2026-10-04", "2026-10-07"],
		)
		self.assertEqual(
			self.dates("2026-01-31", "2026-05-31", "Custom", interval=2, unit="Months"),
			["2026-01-31", "2026-03-31", "2026-05-31"],
		)

	def test_explicit_dates_are_sorted_and_deduplicated(self):
		self.assertEqual(
			self.dates(
				"2026-10-01",
				"2026-10-31",
				"Custom",
				unit="Dates",
				custom_dates=["2026-10-09", "2026-10-02", "2026-10-09"],
			),
			["2026-10-02", "2026-10-09"],
		)

	def test_invalid_and_unbounded_rules_are_rejected(self):
		cases = [
			("2026-10-02", "2026-10-01", "Daily", {}),
			("2026-10-01", "2026-10-02", "Unknown", {}),
			("2026-10-01", "2026-10-02", "Custom", {"interval": 0}),
			("2026-10-01", "2026-10-02", "Custom", {"interval": 1.5}),
			("2026-10-01", "2026-10-02", "Custom", {"unit": "Dates", "custom_dates": ["2026-11-01"]}),
			("2026-01-01", "2030-01-01", "Daily", {}),
			("2026-10-17", "2026-10-18", "Weekdays", {}),
		]
		for start, end, frequency, kwargs in cases:
			with self.subTest(frequency=frequency, kwargs=kwargs), self.assertRaises(ValueError):
				production_dates(start, end, frequency, **kwargs)


class TestProductionPermissions(TestCase):
	def test_company_restriction_applies_to_planners_and_supervisors(self):
		with patch.object(
			permissions, "get_user_permissions", return_value={"Company": [frappe._dict(doc="A")]}
		):
			self.assertTrue(permissions.company_allowed("A", "planner"))
			self.assertFalse(permissions.company_allowed("B", "planner"))

	def test_other_roles_and_shares_cannot_widen_supervisor_access(self):
		doc = frappe._dict(company="A", supervisor="alice")
		with (
			patch.object(permissions, "company_allowed", return_value=True),
			patch.object(permissions, "is_planner", return_value=False),
			patch.object(
				permissions.frappe, "get_roles", return_value=[permissions.SUPERVISOR, "Stock Manager"]
			),
		):
			self.assertTrue(permissions.assignment_permission(doc, "read", "alice"))
			self.assertFalse(permissions.assignment_permission(doc, "write", "alice"))
			self.assertFalse(permissions.assignment_permission(doc, "read", "bob"))


class TestProductionScheduling(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		setup_production()
		cls.company = frappe.get_all("Company", pluck="name", limit=1)[0]
		cls.supervisors = ["production-a@example.test", "production-b@example.test"]
		for user in cls.supervisors:
			if not frappe.db.exists("User", user):
				frappe.get_doc(
					{
						"doctype": "User",
						"email": user,
						"first_name": user,
						"send_welcome_email": 0,
						"user_type": "System User",
						"roles": [{"role": permissions.SUPERVISOR}],
					}
				).insert()
		cls.template = "_Test Production Template"
		if not frappe.db.exists("Item Attribute", "_Test Production Size"):
			frappe.get_doc(
				{
					"doctype": "Item Attribute",
					"attribute_name": "_Test Production Size",
					"item_attribute_values": [{"attribute_value": "One", "abbr": "ONE"}],
				}
			).insert()
		# Item creation is unrelated to this feature's Dynamic Item approval workflow.
		# Isolate that guard while still executing production supervisor validation.
		with patch("srv_erp.masters.dynamic_item.guard.validate_dynamic_item_insert"):
			if not frappe.db.exists("Item", cls.template):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": cls.template,
						"item_name": cls.template,
						"item_group": frappe.get_all(
							"Item Group", filters={"is_group": 0}, pluck="name", limit=1
						)[0],
						"stock_uom": "Nos",
						"has_variants": 1,
						"variant_based_on": "Item Attribute",
						"attributes": [{"attribute": "_Test Production Size"}],
						"custom_production_supervisor": cls.supervisors[0],
					}
				).insert()
			cls.variant = cls.template + "-V"
			if not frappe.db.exists("Item", cls.variant):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": cls.variant,
						"item_name": cls.variant,
						"item_group": frappe.db.get_value("Item", cls.template, "item_group"),
						"stock_uom": "Nos",
						"variant_of": cls.template,
						"attributes": [{"attribute": "_Test Production Size", "attribute_value": "One"}],
					}
				).insert()
		frappe.db.commit()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.set_value("Item", self.template, "custom_production_supervisor", self.supervisors[0])

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def schedule(self, **kwargs):
		doc = frappe.get_doc(
			{
				"doctype": SCHEDULE,
				"company": self.company,
				"template": self.template,
				"start_date": "2026-10-01",
				"end_date": "2026-10-03",
				"frequency": "Daily",
				"qty_per_occurrence": 10,
				**kwargs,
			}
		).insert()
		doc.submit()
		return doc, frappe.get_all(
			ASSIGNMENT, filters={"schedule": doc.name}, pluck="name", order_by="planned_date"
		)

	def entry(self, assignment, qty=4):
		return frappe.get_doc(
			{
				"doctype": ENTRY,
				"assignment": assignment,
				"item_code": self.variant,
				"qty": qty,
				"production_date": "2026-10-01",
			}
		).insert()

	def test_schedule_generation_and_unique_occurrences(self):
		schedule, names = self.schedule()
		self.assertEqual(len(names), 3)
		self.assertEqual(frappe.get_doc(ASSIGNMENT, names[0]).supervisor, self.supervisors[0])
		schedule.submit()  # Repeating the action is a no-op, not another set of assignments.
		self.assertEqual(frappe.db.count(ASSIGNMENT, {"schedule": schedule.name}), 3)

	def test_partial_submission_cancellation_and_overproduction(self):
		_, names = self.schedule()
		draft = self.entry(names[0])
		self.assertEqual(submitted_qty(names[0]), 0)
		draft.submit()
		self.assertEqual(frappe.get_doc(ASSIGNMENT, names[0]).remaining_qty, 6)
		second = self.entry(names[0], 6).submit()
		self.assertEqual(frappe.get_doc(ASSIGNMENT, names[0]).status, "Completed")
		with self.assertRaises(frappe.ValidationError):
			self.entry(names[0], 1).submit()
		second.cancel()
		self.assertEqual(frappe.get_doc(ASSIGNMENT, names[0]).completed_qty, 4)
		self.assertEqual(frappe.get_doc(ASSIGNMENT, names[0]).status, "In Progress")

	def test_supervisor_lists_calendar_direct_and_write_access(self):
		_, own = self.schedule()
		frappe.db.set_value("Item", self.template, "custom_production_supervisor", self.supervisors[1])
		_, others = self.schedule()
		other_entry = self.entry(others[0])
		frappe.set_user(self.supervisors[0])
		visible = frappe.get_list(ASSIGNMENT, pluck="name", limit_page_length=0)
		self.assertTrue(set(own).issubset(visible))
		self.assertTrue(set(others).isdisjoint(visible))
		self.assertTrue(set(others).isdisjoint(row.name for row in get_events("2026-10-01", "2026-10-04")))
		self.assertFalse(frappe.has_permission(ASSIGNMENT, "read", doc=frappe.get_doc(ASSIGNMENT, others[0])))
		self.assertFalse(frappe.has_permission(ENTRY, "read", doc=other_entry))
		self.assertFalse(frappe.has_permission(SCHEDULE, "read"))
		self.assertFalse(frappe.has_permission(ASSIGNMENT, "write", doc=frappe.get_doc(ASSIGNMENT, own[0])))
		with self.assertRaises(frappe.PermissionError):
			self.entry(others[0])
		self.entry(own[0]).submit()
		self.assertEqual(submitted_qty(own[0]), 4)

	def test_cancel_schedule_requires_reversing_production(self):
		schedule, names = self.schedule()
		entry = self.entry(names[0]).submit()
		with self.assertRaises(frappe.ValidationError):
			schedule.cancel()
		entry.cancel()
		schedule.reload().cancel()
		self.assertEqual(frappe.get_doc(ASSIGNMENT, names[0]).status, "Cancelled")
		with self.assertRaises(frappe.ValidationError):
			self.entry(names[0])

	def test_reassignment_and_source_tampering(self):
		_, names = self.schedule()
		entry = self.entry(names[0]).submit()
		assignment = frappe.get_doc(ASSIGNMENT, names[0])
		assignment.supervisor = self.supervisors[1]
		with self.assertRaises(frappe.ValidationError):
			assignment.save()
		assignment.reload()
		assignment.supervisor = self.supervisors[1]
		assignment.change_reason = "Supervisor handover"
		assignment.save()
		self.assertFalse(frappe.has_permission(ENTRY, "read", doc=entry, user=self.supervisors[0]))
		self.assertTrue(frappe.has_permission(ENTRY, "read", doc=entry, user=self.supervisors[1]))
		assignment.template = self.variant
		with self.assertRaises(frappe.ValidationError):
			assignment.save()

	def test_future_date_nonpositive_qty_and_unrelated_variant(self):
		_, names = self.schedule()
		for qty in (0, -1):
			with self.subTest(qty=qty), self.assertRaises(frappe.ValidationError):
				self.entry(names[0], qty)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": ENTRY,
					"assignment": names[0],
					"item_code": self.variant,
					"qty": 1,
					"production_date": "2099-01-01",
				}
			).insert()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": ENTRY,
					"assignment": names[0],
					"item_code": self.template,
					"qty": 1,
					"production_date": "2026-10-01",
				}
			).insert()

	def test_shares_cannot_bypass_supervisor_permissions(self):
		_, names = self.schedule()
		with self.assertRaises(frappe.PermissionError):
			frappe.share.add_docshare(
				ASSIGNMENT, names[0], user=self.supervisors[1], flags={"ignore_share_permission": True}
			)

	def test_planner_role_can_create_plans_without_stock_permissions(self):
		user = "production-planner@example.test"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": user,
					"first_name": "Production Planner",
					"send_welcome_email": 0,
					"user_type": "System User",
					"roles": [{"role": permissions.PLANNER}],
				}
			).insert()
		frappe.set_user(user)
		schedule, names = self.schedule()
		self.assertEqual(len(names), 3)
		self.assertTrue(frappe.has_permission(SCHEDULE, "read", doc=schedule))
		self.assertFalse(frappe.has_permission("Stock Entry", "create"))

	def test_cancellation_cannot_change_submitted_source_or_quantity(self):
		schedule, names = self.schedule()
		entry = self.entry(names[0]).submit()
		entry.assignment = names[1]
		with self.assertRaises(frappe.ValidationError):
			entry.cancel()
		entry.reload()
		entry.qty = 1
		with self.assertRaises(frappe.ValidationError):
			entry.cancel()
		entry.reload().cancel()
		schedule.qty_per_occurrence = 1
		with self.assertRaises(frappe.ValidationError):
			schedule.cancel()
