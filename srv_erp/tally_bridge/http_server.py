import json
import logging
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


LOGGER = logging.getLogger("srv_tally_bridge")


class BridgeHTTPServer(ThreadingHTTPServer):
	def __init__(self, address, service):
		self.service = service
		super().__init__(address, BridgeRequestHandler)


class BridgeRequestHandler(BaseHTTPRequestHandler):
	server_version = "SRVTallyBridge/1.0"

	def _json(self, status, payload):
		content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
		self.send_response(status)
		self.send_header("Content-Type", "application/json; charset=utf-8")
		self.send_header("Content-Length", str(len(content)))
		self.end_headers()
		self.wfile.write(content)

	def do_GET(self):
		path = urllib.parse.urlparse(self.path)
		if path.path == "/health":
			try:
				self._json(200, self.server.service.health())
			except Exception as exc:
				self._json(503, {"ok": False, "error": str(exc)})
			return
		if path.path == "/sync":
			query = urllib.parse.parse_qs(path.query)
			limit = int(query.get("limit", [0])[0]) or None
			summary = self.server.service.sync_once(limit=limit)
			self._json(200 if not summary.error else 409, summary.to_dict())
			return
		self._json(404, {"error": "Not found"})

	def log_message(self, fmt, *args):
		LOGGER.info("%s - %s", self.address_string(), fmt % args)


def start_polling(service, interval_seconds):
	def poll():
		while True:
			summary = service.sync_once()
			LOGGER.info("Scheduled sync: %s", summary.to_dict())
			time.sleep(max(int(interval_seconds), 10))

	thread = threading.Thread(target=poll, name="tally-sync-poller", daemon=True)
	thread.start()
	return thread
