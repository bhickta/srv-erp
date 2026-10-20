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

	def second_variant(self):
		code = self.template + "-SECOND"
		if not frappe.db.exists("Item", code):
			attribute = frappe.get_doc("Item Attribute", "_Test Production Size")
			if not any(row.attribute_value == "Two" for row in attribute.item_attribute_values):
				attribute.append("item_attribute_values", {"attribute_value": "Two", "abbr": "TWO"})
				attribute.save()
			with patch("srv_erp.masters.dynamic_item.guard.validate_dynamic_item_insert"):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": code,
						"item_name": code,
						"item_group": frappe.db.get_value("Item", self.template, "item_group"),
						"stock_uom": "Nos",
						"variant_of": self.template,
						"attributes": [{"attribute": "_Test Production Size", "attribute_value": "Two"}],
					}
				).insert()
		return code

	def multi_schedule(self, rows=None, **kwargs):
		rows = rows or [
			{"template": self.template, "item_code": self.variant, "qty_per_occurrence": 10},
			{"template": self.template, "item_code": self.second_variant(), "qty_per_occurrence": 20},
		]
		return (
			frappe.get_doc(
				{
					"doctype": SCHEDULE,
					"title": "Multi-item production",
					"company": self.company,
					"start_date": "2026-10-01",
					"end_date": "2026-10-01",
					"frequency": "Once",
					"items": rows,
					**kwargs,
				}
			)
			.insert()
			.submit()
		)

	def test_multi_item_variant_plan_mapping_and_progress(self):
		from srv_erp.production.service import make_production_entry

		schedule = self.multi_schedule()
		self.assertEqual(schedule.status, "To Produce")
		self.assertEqual(schedule.remaining_items, 2)
		entry = make_production_entry(schedule.name, supervisor=self.supervisors[0])
		self.assertEqual(len(entry.items), 2)
		self.assertEqual({row.item_code for row in entry.items}, {self.variant, self.second_variant()})
		self.assertEqual({row.qty for row in entry.items}, {10, 20})
		entry.items[0].qty = entry.items[0].remaining_qty / 2
		entry.items[1].qty = entry.items[1].remaining_qty / 2
		entry.insert().submit()
		schedule.reload()
		self.assertEqual(schedule.status, "Partly Produced")
		self.assertEqual(schedule.percent_completed, 50)
		self.assertTrue(all(row.percent_completed == 50 for row in schedule.items))
		remaining = make_production_entry(schedule.name, supervisor=self.supervisors[0])
		self.assertEqual({row.qty for row in remaining.items}, {5, 10})
		remaining.insert().submit()
		schedule.reload()
		self.assertEqual(
			(schedule.status, schedule.percent_completed, schedule.remaining_items), ("Completed", 100, 0)
		)
		with self.assertRaises(frappe.ValidationError):
			make_production_entry(schedule.name)
		remaining.cancel()
		schedule.reload()
		self.assertEqual((schedule.status, schedule.percent_completed), ("Partly Produced", 50))

	def test_multi_item_specific_variant_cannot_be_substituted(self):
		from srv_erp.production.service import make_production_entry

		schedule = self.multi_schedule()
		entry = make_production_entry(schedule.name)
		entry.items[0].item_code = (
			self.second_variant() if entry.items[0].item_code == self.variant else self.variant
		)
		with self.assertRaises(frappe.ValidationError):
			entry.insert()

	def test_multi_item_template_output_can_split_across_variants(self):
		from srv_erp.production.service import make_production_entry

		schedule = self.multi_schedule(rows=[{"template": self.template, "qty_per_occurrence": 10}])
		entry = make_production_entry(schedule.name)
		row = entry.items[0]
		row.item_code, row.qty = self.variant, 4
		entry.append("items", {"assignment": row.assignment, "item_code": self.second_variant(), "qty": 6})
		entry.insert().submit()
		self.assertEqual(schedule.reload().percent_completed, 100)
		self.assertEqual(submitted_qty(row.assignment), 10)

	def test_multi_item_duplicate_rows_cannot_exceed_one_source_target(self):
		from srv_erp.production.service import make_production_entry

		schedule = self.multi_schedule(rows=[{"template": self.template, "qty_per_occurrence": 10}])
		entry = make_production_entry(schedule.name)
		entry.items[0].item_code, entry.items[0].qty = self.variant, 6
		entry.append(
			"items", {"assignment": entry.items[0].assignment, "item_code": self.second_variant(), "qty": 6}
		)
		entry.insert()
		with self.assertRaises(frappe.ValidationError):
			entry.submit()
		self.assertEqual(submitted_qty(entry.items[0].assignment), 0)

	def test_multi_item_schedule_rejects_invalid_variant_and_duplicates(self):
		with self.assertRaises(frappe.ValidationError):
			self.multi_schedule(
				rows=[{"template": self.template, "item_code": self.template, "qty_per_occurrence": 1}]
			)
		with self.assertRaises(frappe.ValidationError):
			self.multi_schedule(
				rows=[{"template": self.template, "item_code": self.variant, "qty_per_occurrence": 1}] * 2
			)

	def test_multi_item_forged_cross_schedule_entry_rejected(self):
		from srv_erp.production.service import make_production_entry

		first, second = self.multi_schedule(), self.multi_schedule()
		entry = make_production_entry(first.name)
		foreign = frappe.get_all(ASSIGNMENT, filters={"schedule": second.name}, pluck="name")[0]
		entry.items[0].assignment = foreign
		with self.assertRaises(frappe.ValidationError):
			entry.insert()

	def test_multi_item_supervisor_mapping_and_entry_privacy(self):
		from srv_erp.production.service import make_production_entry

		schedule = self.multi_schedule()
		names = frappe.get_all(ASSIGNMENT, filters={"schedule": schedule.name}, pluck="name")
		frappe.db.set_value(ASSIGNMENT, names[0], "supervisor", self.supervisors[1])
		frappe.set_user(self.supervisors[0])
		entry = make_production_entry(schedule.name)
		self.assertEqual(len(entry.items), 1)
		self.assertNotEqual(entry.items[0].assignment, names[0])
		entry.insert().submit()
		own_entry = entry.name
		frappe.set_user(self.supervisors[1])
		visible = frappe.get_list(ENTRY, pluck="name", limit_page_length=0)
		self.assertNotIn(own_entry, visible)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(ENTRY, own_entry).check_permission("read")
		other = make_production_entry(schedule.name)
		self.assertEqual(other.items[0].assignment, names[0])

	def test_multi_item_submitted_source_rows_are_immutable(self):
		schedule = self.multi_schedule()
		schedule.items[0].qty_per_occurrence = 999
		with self.assertRaises(frappe.ValidationError):
			schedule.save()

	def test_multi_item_migration_is_idempotent_and_preserves_totals(self):
		from srv_erp.production.migrate import execute

		_, names = self.schedule()
		entry = self.entry(names[0]).submit()
		before = submitted_qty(names[0])
		# Emulate the previous release's persisted single-item documents.
		frappe.db.delete("SRV Production Entry Item", {"parent": entry.name})
		schedule = frappe.db.get_value(ASSIGNMENT, names[0], "schedule")
		frappe.db.delete("SRV Production Schedule Item", {"parent": schedule})
		frappe.db.sql(
			"UPDATE `tabSRV Production Assignment` SET schedule_item=NULL WHERE schedule=%s", schedule
		)
		execute()
		execute()
		self.assertEqual(submitted_qty(names[0]), before)
		self.assertEqual(frappe.db.count("SRV Production Entry Item", {"parent": entry.name}), 1)
		self.assertEqual(frappe.db.count("SRV Production Schedule Item", {"parent": schedule}), 1)
		self.assertEqual(frappe.get_doc(SCHEDULE, schedule).status, "Partly Produced")

	def test_multi_item_reassignment_does_not_expose_other_rows(self):
		from srv_erp.production.service import make_production_entry

		schedule = self.multi_schedule()
		entry = make_production_entry(schedule.name).insert().submit()
		assignment = frappe.get_doc(ASSIGNMENT, entry.items[0].assignment)
		assignment.supervisor = self.supervisors[1]
		assignment.change_reason = "Move this item to another supervisor"
		assignment.save()
		for user in self.supervisors:
			frappe.set_user(user)
			self.assertFalse(frappe.has_permission(ENTRY, "read", doc=frappe.get_doc(ENTRY, entry.name)))
			self.assertNotIn(entry.name, frappe.get_list(ENTRY, pluck="name", limit_page_length=0))
		frappe.set_user(self.supervisors[0])
		forged = frappe.get_doc(ENTRY, entry.name)
		forged.items = [row for row in forged.items if row.assignment != assignment.name]
		with self.assertRaises(frappe.PermissionError):
			forged.save()

	def test_multi_item_cancelled_child_quantities_cannot_be_changed(self):
		from srv_erp.production.service import make_production_entry

		entry = make_production_entry(self.multi_schedule().name).insert().submit()
		entry.items[0].qty = 1
		with self.assertRaises(frappe.ValidationError):
			entry.cancel()

	def test_multi_item_mapper_respects_selected_schedule_rows(self):
		from srv_erp.production.service import make_production_entry

		schedule = self.multi_schedule()
		previous = frappe.flags.selected_children
		try:
			frappe.flags.selected_children = {"items": [schedule.items[1].name]}
			entry = make_production_entry(schedule.name)
			self.assertEqual(len(entry.items), 1)
			self.assertEqual(entry.items[0].item_code, schedule.items[1].item_code)
		finally:
			frappe.flags.selected_children = previous

	def test_multi_item_child_table_apis_cannot_bypass_entry_permissions(self):
		from frappe.client import get, get_list, get_value

		from srv_erp.production.service import make_production_entry

		own = make_production_entry(self.multi_schedule().name).insert().submit()
		foreign_schedule = self.multi_schedule()
		for name in frappe.get_all(ASSIGNMENT, filters={"schedule": foreign_schedule.name}, pluck="name"):
			frappe.db.set_value(ASSIGNMENT, name, "supervisor", self.supervisors[1])
		foreign = make_production_entry(foreign_schedule.name).insert().submit()
		frappe.set_user(self.supervisors[0])
		rows = get_list(
			"SRV Production Entry Item", fields=["parent", "name"], parent=ENTRY, limit_page_length=0
		)
		self.assertIn(own.name, {row.parent for row in rows})
		self.assertNotIn(foreign.name, {row.parent for row in rows})
		with self.assertRaises(frappe.PermissionError):
			get("SRV Production Entry Item", name=foreign.items[0].name, parent=ENTRY)
		self.assertFalse(
			get_value("SRV Production Entry Item", "qty", {"name": foreign.items[0].name}, parent=ENTRY)
		)
		with self.assertRaises(frappe.PermissionError):
			get_list("SRV Production Schedule Item", parent=SCHEDULE)

	def test_multi_item_child_rows_cannot_be_shared(self):
		schedule = self.multi_schedule()
		with self.assertRaises(frappe.PermissionError):
			frappe.share.add_docshare(
				"SRV Production Schedule Item",
				schedule.items[0].name,
				user=self.supervisors[0],
				flags={"ignore_share_permission": True},
			)

	def role_schedule(self, **kwargs):
		return self.multi_schedule(
			responsibilities=[
				{"supervisor": self.supervisors[0], "work_area": "Fabrication"},
				{"supervisor": self.supervisors[1], "work_area": "Bending"},
			],
			**kwargs,
		)

	def test_responsibility_stages_have_independent_balances_and_privacy(self):
		from srv_erp.production.service import make_production_entry

		schedule = self.role_schedule()
		self.assertEqual(frappe.db.count(ASSIGNMENT, {"schedule": schedule.name}), 4)
		frappe.set_user(self.supervisors[0])
		entry = make_production_entry(schedule.name).insert().submit()
		self.assertEqual(entry.work_area, "Fabrication")
		self.assertEqual(len(entry.items), 2)
		self.assertEqual({row.work_area for row in entry.items}, {"Fabrication"})
		visible = frappe.get_list(ASSIGNMENT, filters={"schedule": schedule.name}, pluck="supervisor")
		self.assertEqual(set(visible), {self.supervisors[0]})
		frappe.set_user("Administrator")
		schedule.reload()
		self.assertEqual(
			(schedule.percent_completed, schedule.status, schedule.remaining_items),
			(50, "Partly Produced", 2),
		)
		self.assertEqual({row.completed_qty for row in schedule.items}, {0})
		self.assertEqual({row.planned_qty for row in schedule.items}, {10, 20})
		self.assertEqual(schedule.responsibilities[0].status, "Completed")
		self.assertEqual(schedule.responsibilities[1].percent_completed, 0)
		frappe.set_user(self.supervisors[1])
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(ENTRY, entry.name).check_permission("read")
		bending = make_production_entry(schedule.name).insert().submit()
		self.assertEqual({row.qty for row in bending.items}, {10, 20})
		frappe.set_user("Administrator")
		schedule.reload()
		self.assertEqual(
			(schedule.percent_completed, schedule.status, schedule.remaining_items), (100, "Completed", 0)
		)
		bending.cancel()
		schedule.reload()
		self.assertEqual(schedule.percent_completed, 50)
		self.assertTrue(all(row.completed_qty == 0 for row in schedule.items))
		self.assertTrue(
			all(frappe.get_doc(ASSIGNMENT, row.assignment).remaining_qty == 0 for row in entry.items)
		)

	def test_item_dates_and_names_follow_sources_and_cannot_be_forged(self):
		from srv_erp.production.service import make_production_entry

		frappe.db.set_value("Item", self.variant, "item_name", "Fabricated panel")
		second = self.second_variant()
		schedule = self.multi_schedule(
			rows=[
				{"template": self.template, "item_code": self.variant, "qty_per_occurrence": 10},
				{
					"template": self.template,
					"item_code": second,
					"qty_per_occurrence": 20,
					"schedule_date": "2026-10-03",
				},
			],
			end_date="2026-10-03",
			schedule_date="2026-10-02",
		)
		self.assertEqual(str(schedule.items[0].schedule_date), "2026-10-02")
		entry = make_production_entry(schedule.name)
		self.assertEqual(str(entry.schedule_date), "2026-10-02")
		self.assertEqual({str(row.planned_date) for row in entry.items}, {"2026-10-02", "2026-10-03"})
		for row in entry.items:
			row.planned_date = "2020-01-01"
			row.item_name = "Forged name"
			row.work_area = "Forged area"
		entry.schedule_date = "2020-01-01"
		entry.insert().submit()
		self.assertEqual(str(entry.schedule_date), "2026-10-02")
		self.assertEqual({str(row.planned_date) for row in entry.items}, {"2026-10-02", "2026-10-03"})
		self.assertEqual(
			next(row.item_name for row in entry.items if row.item_code == self.variant), "Fabricated panel"
		)
		self.assertEqual({row.work_area for row in entry.items}, {"Production"})

	def test_item_recurrence_starts_at_its_own_schedule_date(self):
		schedule = self.multi_schedule(
			rows=[
				{
					"template": self.template,
					"item_code": self.variant,
					"qty_per_occurrence": 10,
					"schedule_date": "2026-10-02",
				}
			],
			end_date="2026-10-03",
			frequency="Daily",
		)
		self.assertEqual(schedule.items[0].planned_qty, 20)
		self.assertEqual(frappe.db.count(ASSIGNMENT, {"schedule": schedule.name}), 2)
		with self.assertRaises(frappe.ValidationError):
			self.multi_schedule(schedule_date="2026-09-30")
		with self.assertRaises(frappe.ValidationError):
			self.multi_schedule(
				rows=[{"template": self.template, "qty_per_occurrence": 1, "schedule_date": "2026-10-02"}]
			)

	def test_same_user_multiple_areas_require_separate_entries(self):
		from srv_erp.production.service import make_production_entry

		schedule = self.multi_schedule(
			responsibilities=[
				{"supervisor": self.supervisors[0], "work_area": "Fabrication"},
				{"supervisor": self.supervisors[0], "work_area": "Bending"},
			]
		)
		with self.assertRaises(frappe.ValidationError):
			make_production_entry(schedule.name)
		entry = make_production_entry(schedule.name, work_area="Fabrication")
		foreign = frappe.get_all(
			ASSIGNMENT, filters={"schedule": schedule.name, "work_area": "Bending"}, pluck="name"
		)[0]
		entry.items[0].assignment = foreign
		with self.assertRaises(frappe.ValidationError):
			entry.insert()
		make_production_entry(schedule.name, work_area="Fabrication").insert().submit()
		self.assertEqual(len(make_production_entry(schedule.name, work_area="Bending").items), 2)

	def test_responsibility_validation_and_submitted_sources_are_immutable(self):
		with self.assertRaises(frappe.ValidationError):
			self.multi_schedule(
				responsibilities=[
					{"supervisor": self.supervisors[0], "work_area": "Bending"},
					{"supervisor": self.supervisors[0], "work_area": " bending "},
				]
			)
		with self.assertRaises(frappe.ValidationError):
			self.multi_schedule(responsibilities=[{"supervisor": self.supervisors[0], "work_area": " "}])
		schedule = self.role_schedule()
		schedule.responsibilities[0].work_area = "Packing"
		with self.assertRaises(frappe.ValidationError):
			schedule.save()
		schedule.reload()
		schedule.items[0].schedule_date = "2026-10-02"
		with self.assertRaises(frappe.ValidationError):
			schedule.save()

	def test_explicit_responsibilities_do_not_require_template_default(self):
		frappe.db.set_value("Item", self.template, "custom_production_supervisor", None)
		schedule = self.role_schedule()
		self.assertEqual(frappe.db.count(ASSIGNMENT, {"schedule": schedule.name}), 4)

	def test_role_migration_is_idempotent_and_keeps_original_sources(self):
		from srv_erp.production.migrate import execute
		from srv_erp.production.service import make_production_entry

		schedule = self.multi_schedule()
		entry = make_production_entry(schedule.name).insert().submit()
		sources = {row.assignment for row in entry.items}
		frappe.db.set_value(SCHEDULE, schedule.name, "schedule_date", None)
		for row in schedule.items:
			frappe.db.set_value(row.doctype, row.name, {"schedule_date": None, "item_name": None})
		for row in entry.items:
			frappe.db.set_value(row.doctype, row.name, {"item_name": None, "work_area": None})
			frappe.db.set_value(ASSIGNMENT, row.assignment, "work_area", None)
		frappe.db.set_value(ENTRY, entry.name, {"schedule_date": None, "work_area": None})
		execute()
		execute()
		schedule.reload()
		entry.reload()
		self.assertEqual({row.assignment for row in entry.items}, sources)
		self.assertEqual(frappe.db.count(ASSIGNMENT, {"schedule": schedule.name}), 2)
		self.assertEqual(schedule.responsibilities, [])
		self.assertEqual(schedule.status, "Completed")
		self.assertEqual(str(entry.schedule_date), "2026-10-01")
		self.assertEqual(entry.work_area, "Production")
		self.assertTrue(all(row.item_name and row.schedule_date for row in schedule.items))
		self.assertTrue(all(row.item_name and row.work_area == "Production" for row in entry.items))

	def test_rescheduling_one_operation_does_not_double_physical_quantity(self):
		from srv_erp.production.service import make_production_entry

		schedule = self.role_schedule(end_date="2026-10-03")
		name = frappe.get_all(
			ASSIGNMENT, filters={"schedule": schedule.name, "work_area": "Bending"}, pluck="name"
		)[0]
		assignment = frappe.get_doc(ASSIGNMENT, name)
		assignment.planned_date = "2026-10-03"
		assignment.change_reason = "Bending is scheduled after fabrication"
		assignment.save()
		schedule.reload()
		self.assertEqual({row.planned_qty for row in schedule.items}, {10, 20})
		make_production_entry(schedule.name, work_area="Fabrication").insert().submit()
		schedule.reload()
		self.assertEqual({row.completed_qty for row in schedule.items}, {0})
		bending = make_production_entry(schedule.name, work_area="Bending")
		self.assertIn("2026-10-03", {str(row.planned_date) for row in bending.items})
		bending.insert().submit()
		schedule.reload()
		self.assertEqual((schedule.status, schedule.percent_completed), ("Completed", 100))
		self.assertEqual({row.completed_qty for row in schedule.items}, {10, 20})

	def test_responsibility_child_access_and_shares_cannot_leak_other_users(self):
		from frappe.client import get, get_list

		schedule = self.role_schedule()
		row = schedule.responsibilities[1]
		frappe.set_user(self.supervisors[0])
		with self.assertRaises(frappe.PermissionError):
			get_list(row.doctype, parent=SCHEDULE)
		with self.assertRaises(frappe.PermissionError):
			get(row.doctype, name=row.name, parent=SCHEDULE)
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.PermissionError):
			frappe.share.add_docshare(
				row.doctype, row.name, user=self.supervisors[0], flags={"ignore_share_permission": True}
			)
