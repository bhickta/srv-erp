import frappe
from frappe.desk import reportview
from frappe.model.db_query import DatabaseQuery
from frappe.utils import cint, sbool


LIVE_GROUP_OPERATOR = "descendants of (inclusive)"


class LiveCustomerGroupSalesOrderQuery(DatabaseQuery):
	def __init__(self, group_bounds=None):
		super().__init__("Sales Order")
		self.group_bounds = group_bounds or []

	def build_conditions(self):
		super().build_conditions()
		for index, bounds in enumerate(self.group_bounds):
			if not bounds:
				self.conditions.append("1 = 0")
				continue

			lft, rgt = (cint(value) for value in bounds)
			customer_alias = f"live_customer_{index}"
			group_alias = f"live_customer_group_{index}"
			self.conditions.append(
				f"""EXISTS (
					SELECT 1
					FROM `tabCustomer` {customer_alias}
					INNER JOIN `tabCustomer Group` {group_alias}
						ON {group_alias}.name = {customer_alias}.customer_group
					WHERE {customer_alias}.name = `tabSales Order`.customer
						AND {group_alias}.lft >= {lft}
						AND {group_alias}.rgt <= {rgt}
				)"""
			)


@frappe.whitelist()
@frappe.read_only()
def get():
	args = _get_query_args()
	query = LiveCustomerGroupSalesOrderQuery(_extract_live_group_bounds(args))
	data = query.execute(**_without_doctype(args))
	return reportview.compress(data, args=args)


@frappe.whitelist()
@frappe.read_only()
def get_count():
	args = _get_query_args()
	query = LiveCustomerGroupSalesOrderQuery(_extract_live_group_bounds(args))

	args.distinct = sbool(args.distinct)
	distinct = "distinct " if args.distinct else ""
	args.limit = cint(args.limit)
	args.order_by = None
	args.fields = [f"{distinct}`tabSales Order`.name"]

	partial_query = query.execute(**_without_doctype(args), run=False)
	return frappe.db.sql(f"SELECT COUNT(*) FROM ({partial_query}) live_sales_orders")[0][0]


def _get_query_args():
	args = reportview.get_form_params()
	if args.doctype != "Sales Order":
		frappe.throw("This endpoint only supports Sales Order")
	return args


def _without_doctype(args):
	query_args = frappe._dict(args.copy())
	query_args.pop("doctype", None)
	return query_args


def _extract_live_group_bounds(args):
	group_bounds = []
	remaining_filters = []

	for condition in args.filters or []:
		doctype, fieldname, operator, value = _normalise_filter(condition)
		if (
			doctype == "Sales Order"
			and fieldname == "customer_group"
			and operator.lower() == LIVE_GROUP_OPERATOR
		):
			group_bounds.append(frappe.db.get_value("Customer Group", value, ["lft", "rgt"]))
		else:
			remaining_filters.append(condition)

	args.filters = remaining_filters
	return group_bounds


def _normalise_filter(condition):
	if len(condition) == 3:
		return "Sales Order", condition[0], condition[1], condition[2]
	return condition[0], condition[1], condition[2], condition[3]
