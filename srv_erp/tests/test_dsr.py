from datetime import datetime
from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from srv_erp.selling.dsr import validate_dsr_submission_deadline


class TestDSR(ERPNextTestSuite):
	def make_dsr(self, **values):
		data = {
			"doctype": "DSR",
			"date": "2026-07-28",
			"sales_person": "_Test Sales Person",
			"start_reading": 100,
			"end_reading": 135,
			"fuel_added": 1,
			"rate_per_liter": 100,
			"amount_paid": 500,
			"daily_sales_expenses_by_admin": [
				{
					"type": "Meals",
					"amount": 75,
					"description": "Lunch",
				}
			],
		}
		data.update(values)
		return frappe.get_doc(data)

	@patch("srv_erp.srv_erp.doctype.dsr.dsr.frappe.get_roles", return_value=["Sales User"])
	@patch("srv_erp.srv_erp.doctype.dsr.dsr.frappe.get_all", return_value=[])
	@patch("srv_erp.srv_erp.doctype.dsr.dsr.frappe.get_cached_value", return_value=9)
	def test_calculates_travel_fuel_and_total(self, _get_cached_value, _get_all, _get_roles):
		dsr = self.make_dsr()

		dsr.validate()

		self.assertEqual(dsr.km_travelled, 35)
		self.assertEqual(dsr.amount_for_travel, 315)
		self.assertEqual(dsr.fuel_quantity, 5)
		self.assertEqual(dsr.total_amount, 890)
		self.assertEqual(dsr.custom_day, "Tuesday")

	@patch("srv_erp.srv_erp.doctype.dsr.dsr.frappe.get_roles", return_value=["Sales User"])
	def test_sales_user_cannot_set_audit_fields(self, _get_roles):
		dsr = self.make_dsr(payment_audited=1)

		with self.assertRaises(frappe.PermissionError):
			dsr.validate_audit_permissions()

	@patch("srv_erp.srv_erp.doctype.dsr.dsr.frappe.get_all")
	def test_participant_cannot_appear_in_another_dsr_for_same_date(self, get_all):
		get_all.side_effect = [
			[frappe._dict(name="Existing DSR", sales_person="_Test Other Sales Person")],
			["_Test Sales Person"],
		]
		dsr = self.make_dsr()

		with self.assertRaises(frappe.ValidationError):
			dsr.validate_participants()

	def test_partial_approval_cannot_exceed_claim(self):
		dsr = self.make_dsr(
			partially_paid=1,
			daily_sales_expense_by_admin_approved_amount=[
				{
					"type": "Meals",
					"amount": 100,
					"description": "Approved lunch",
				}
			],
		)

		with self.assertRaises(frappe.ValidationError):
			dsr.validate_audit_state()

	@patch("srv_erp.selling.dsr.now_datetime", return_value=datetime(2026, 7, 28, 12))
	@patch("srv_erp.selling.dsr.frappe.get_roles", return_value=["Sales User"])
	def test_future_dsr_cannot_be_submitted(self, _get_roles, _now_datetime):
		with self.assertRaises(frappe.ValidationError):
			validate_dsr_submission_deadline(frappe._dict(date="2026-07-29"))

	@patch(
		"srv_erp.selling.dsr.get_dsr_submission_rule",
		return_value=frappe._dict(unit="Days", tolerance=0),
	)
	@patch("srv_erp.selling.dsr.now_datetime", return_value=datetime(2026, 7, 28, 12))
	@patch("srv_erp.selling.dsr.frappe.get_roles", return_value=["Sales User"])
	def test_configured_backdate_deadline_is_enforced(
		self, _get_roles, _now_datetime, _get_dsr_submission_rule
	):
		with self.assertRaises(frappe.ValidationError):
			validate_dsr_submission_deadline(frappe._dict(date="2026-07-27"))
