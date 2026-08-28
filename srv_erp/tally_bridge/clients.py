import http.client
import json
import urllib.error
import urllib.parse
import urllib.request

from .json_gateway import parse_import_response as parse_json_import_response
from .xml_gateway import parse_current_company, parse_logical_result


class BridgeRequestError(RuntimeError):
	pass


class FrappeClient:
	def __init__(self, base_url, api_key, api_secret, timeout=30):
		self.base_url = base_url.rstrip("/")
		self.timeout = timeout
		self.headers = {
			"Authorization": f"token {api_key}:{api_secret}",
			"Accept": "application/json",
			"User-Agent": "SRV-Tally-Bridge/1.0",
		}

	def request(self, method, path, data=None):
		"""Call any Frappe REST/API method path with the bridge credentials."""
		base_origin = urllib.parse.urlsplit(self.base_url)
		requested = urllib.parse.urlsplit(path)
		if requested.scheme and (requested.scheme, requested.netloc) != (
			base_origin.scheme,
			base_origin.netloc,
		):
			raise BridgeRequestError("API paths must use the configured Frappe server")
		url = path if requested.scheme else f"{self.base_url}/{path.lstrip('/')}"
		headers = dict(self.headers)
		body = None
		if method.upper() == "GET" and data:
			url = f"{url}?{urllib.parse.urlencode(data)}"
		elif data is not None:
			body = json.dumps(data, ensure_ascii=False).encode("utf-8")
			headers["Content-Type"] = "application/json"
		request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
		try:
			with urllib.request.urlopen(request, timeout=self.timeout) as response:
				payload = json.loads(response.read().decode("utf-8"))
		except urllib.error.HTTPError as exc:
			detail = exc.read().decode("utf-8", errors="replace")
			raise BridgeRequestError(f"Frappe returned HTTP {exc.code}: {detail[:1000]}") from exc
		except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError) as exc:
			raise BridgeRequestError(f"Cannot reach Frappe: {exc}") from exc
		return payload.get("message", payload)

	def get_unsynced_documents(self, config, limit=None):
		params = {
			"company": config.erpnext_company,
			"target_id": config.target_id,
			"tally_company": config.tally_company,
			"limit": limit or config.batch_size,
		}
		if config.from_date:
			params["from_date"] = config.from_date
		return self.request(
			"GET",
			"/api/method/srv_erp.integrations.tally_sync_api.get_unsynced_sales_documents",
			params,
		)

	def acknowledge(self, config, results):
		return self.request(
			"POST",
			"/api/method/srv_erp.integrations.tally_sync_api.acknowledge_sales_documents",
			{
				"target_id": config.target_id,
				"tally_company": config.tally_company,
				"results": results,
			},
		)


class TallyClient:
	def __init__(self, url="http://127.0.0.1:9000", timeout=30):
		self.url = url.rstrip("/") + "/"
		self.timeout = timeout

	def post_xml(self, xml):
		request = urllib.request.Request(
			self.url,
			data=xml.encode("utf-8"),
			headers={"Content-Type": "text/xml; charset=UTF-8", "User-Agent": "SRV-Tally-Bridge/1.0"},
			method="POST",
		)
		try:
			with urllib.request.urlopen(request, timeout=self.timeout) as response:
				return response.read().decode("utf-8", errors="replace")
		except urllib.error.HTTPError as exc:
			detail = exc.read().decode("utf-8", errors="replace")
			raise BridgeRequestError(f"Tally returned HTTP {exc.code}: {detail[:1000]}") from exc
		except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError) as exc:
			raise BridgeRequestError(f"Cannot reach Tally at {self.url}: {exc}") from exc

	def post_json(self, payload, report_id):
		request = urllib.request.Request(
			self.url,
			data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
			headers={
				"Content-Type": "application/json",
				"version": "1",
				"tallyrequest": "Import",
				"type": "Data",
				"id": report_id,
				"detailed-response": "Yes",
				"User-Agent": "SRV-Tally-Bridge/1.0",
			},
			method="POST",
		)
		try:
			with urllib.request.urlopen(request, timeout=self.timeout) as response:
				raw_response = response.read().decode("utf-8", errors="replace")
				# Tally 7.1 may emit its reserved-name marker (U+0004) without
				# JSON escaping it. strict=False accepts that otherwise valid response.
				try:
					return json.loads(raw_response, strict=False)
				except json.JSONDecodeError as exc:
					raise BridgeRequestError(
						f"Tally returned invalid JSON: {raw_response[:1000]}"
					) from exc
		except urllib.error.HTTPError as exc:
			detail = exc.read().decode("utf-8", errors="replace")
			raise BridgeRequestError(f"Tally returned HTTP {exc.code}: {detail[:1000]}") from exc
		except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError) as exc:
			raise BridgeRequestError(f"Cannot reach Tally at {self.url}: {exc}") from exc

	def get_current_company(self, request_xml):
		return parse_current_company(self.post_xml(request_xml))

	def get_logical_function(self, request_xml):
		return parse_logical_result(self.post_xml(request_xml))

	def import_xml(self, xml, require_change=False, allow_ignored=False):
		from .xml_gateway import parse_import_response

		return parse_import_response(
			self.post_xml(xml),
			require_change=require_change,
			allow_ignored=allow_ignored,
		)

	def import_json(self, payload, report_id, require_change=False, allow_ignored=False):
		return parse_json_import_response(
			self.post_json(payload, report_id),
			require_change=require_change,
			allow_ignored=allow_ignored,
		)
