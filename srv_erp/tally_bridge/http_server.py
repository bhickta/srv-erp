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
		self._sync_state_lock = threading.Lock()
		self._sync_thread = None
		self._last_sync = None
		super().__init__(address, BridgeRequestHandler)

	def trigger_sync(self, limit=None):
		"""Start a batch without holding Tally's UI HTTP request open."""
		with self._sync_state_lock:
			if self._sync_thread and self._sync_thread.is_alive():
				return False
			self._sync_thread = threading.Thread(
				target=self._run_sync,
				args=(limit,),
				name="tally-click-sync",
				daemon=True,
			)
			self._sync_thread.start()
			return True

	def _run_sync(self, limit):
		try:
			summary = self.service.sync_once(limit=limit)
			self._last_sync = summary.to_dict()
			LOGGER.info("Manual sync: %s", self._last_sync)
		except Exception as exc:
			self._last_sync = {"error": str(exc)}
			LOGGER.exception("Manual sync failed")

	def sync_status(self):
		with self._sync_state_lock:
			running = bool(self._sync_thread and self._sync_thread.is_alive())
		return {"status": 1, "running": running, "last_sync": self._last_sync}


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
			try:
				limit = int(query.get("limit", [0])[0]) or None
			except ValueError:
				self._json(400, {"status": 0, "message": "limit must be a number"})
				return
			started = self.server.trigger_sync(limit=limit)
			message = "Sync started in background" if started else "A sync is already running"
			self._json(202, {"status": 1, "started": started, "message": message})
			return
		if path.path == "/sync-status":
			self._json(200, self.server.sync_status())
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
