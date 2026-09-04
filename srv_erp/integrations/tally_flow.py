"""SRV policy for the reusable ERPNext-to-Tally sales-document flow."""

from express_tally.integrations.sales_voucher_flow import SalesDocumentsToTallyFlow


class SRVSalesDocumentsToTally(SalesDocumentsToTallyFlow):
	key = "srv.sales_documents_to_tally"
	title = "SRV Sales Orders and Delivery Notes to Tally"
	allowed_roles = frozenset({"Tally Sync User", "Accounts Manager", "System Manager"})
	include_unscoped_legacy = True
