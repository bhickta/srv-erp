import logging
import threading
import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass

from .clients import BridgeRequestError
from .json_gateway import build_master_imports
from .xml_gateway import (
	build_voucher_import,
	current_company_request,
	function_request,
)


LOGGER = logging.getLogger("srv_tally_bridge")


@dataclass
class SyncSummary:
	fetched: int = 0
	succeeded: int = 0
	failed: int = 0
	skipped: int = 0
	error: str = ""

	def to_dict(self):
		return asdict(self)


class SyncService:
	def __init__(self, config, frappe_client, tally_client):
		self.config = config
		self.frappe = frappe_client
		self.tally = tally_client
		self._lock = threading.Lock()

	def health(self):
		loaded_company = self.tally.get_current_company(current_company_request())
		inventory_enabled = self.tally.get_logical_function(function_request("$$IsInventoryOn"))
		return {
			"ok": bool(loaded_company) and inventory_enabled,
			"loaded_tally_company": loaded_company,
			"configured_tally_company": self.config.tally_company,
			"company_matches": loaded_company == self.config.tally_company,
			"inventory_enabled": inventory_enabled,
		}

	def sync_once(self, limit=None):
		if not self._lock.acquire(blocking=False):
			return SyncSummary(skipped=1, error="A sync is already running")
		try:
			return self._sync_once(limit)
		finally:
			self._lock.release()

	def _sync_once(self, limit=None):
		summary = SyncSummary()
		try:
			health = self.health()
			if not health["company_matches"]:
				summary.error = (
					f"Tally company mismatch: loaded '{health['loaded_tally_company']}', "
					f"configured '{health['configured_tally_company']}'"
				)
				return summary
			if not health["inventory_enabled"]:
				summary.error = "Tally Maintain Inventory is disabled for the loaded company"
				return summary
			batch = self.frappe.get_unsynced_documents(self.config, limit=limit)
		except (BridgeRequestError, ValueError) as exc:
			summary.error = str(exc)
			return summary

		if batch.get("schema_version") != 1:
			summary.error = f"Unsupported Frappe sync schema: {batch.get('schema_version')}"
			return summary

		documents = batch.get("documents") or batch.get("orders") or []
		summary.fetched = len(documents)
		for document in documents:
			result = self._sync_document(document)
			try:
				self.frappe.acknowledge(self.config, [result])
			except BridgeRequestError as exc:
				# The deterministic Tally GUID and voucher number make the next retry
				# identifiable even when the acknowledgement response was lost.
				LOGGER.error("Could not acknowledge %s: %s", document["name"], exc)
				summary.failed += 1
				summary.error = str(exc)
				continue
			if result["status"] == "Success":
				summary.succeeded += 1
			else:
				summary.failed += 1
		return summary

	def _sync_document(self, order):
		request_id = str(uuid.uuid4())
		result = {
			"request_id": request_id,
			"source_name": order["name"],
			"source_doctype": order.get("source_doctype", "Sales Order"),
			"source_modified": order["modified"],
			"source_hash": order["source_hash"],
			"operation": order["operation"],
			"status": "Failed",
			"tally_voucher_id": "",
			"error": "",
		}
		try:
			document = deepcopy(order)
			if self.config.voucher_date_override:
				original_date = document["transaction_date"]
				document["transaction_date"] = self.config.voucher_date_override
				source_doctype = document.get("source_doctype", "Sales Order")
				date_note = (
					f"ERPNext {source_doctype} {document['name']}; original date {original_date}"
				)
				document["narration"] = "\n".join(
					part for part in (document.get("narration"), date_note) if part
				)
			for master_payload in build_master_imports(document, self.config.tally_company):
				master_result = self.tally.import_json(
					master_payload,
					"All Masters",
					require_change=False,
				)
				if not master_result.success:
					raise BridgeRequestError(master_result.message or "Tally master import failed")
			voucher_result = self.tally.import_xml(
				build_voucher_import(document, self.config.tally_company, self.config.target_id),
				require_change=True,
				allow_ignored=True,
			)
			if not voucher_result.success:
				raise BridgeRequestError(voucher_result.message or "Tally voucher import failed")
			result["status"] = "Success"
			result["tally_voucher_id"] = voucher_result.last_voucher_id
		except (BridgeRequestError, ValueError, KeyError) as exc:
			result["error"] = str(exc)[:4000]
			LOGGER.error("Sync failed for %s: %s", order.get("name"), exc)
		return result
