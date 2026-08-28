import argparse
import json
import logging
import sys

from .clients import BridgeRequestError, FrappeClient, TallyClient
from .config import BridgeConfig
from .http_server import BridgeHTTPServer, start_polling
from .service import SyncService


def _parser():
	parser = argparse.ArgumentParser(description="Sync ERPNext Sales Orders and Delivery Notes to TallyPrime")
	parser.add_argument("--config", default="tally-bridge.json", help="Path to bridge JSON configuration")
	parser.add_argument("--verbose", action="store_true")
	subparsers = parser.add_subparsers(dest="command", required=True)
	sync = subparsers.add_parser("sync", help="Run one synchronization batch")
	sync.add_argument("--limit", type=int)
	subparsers.add_parser("status", help="Check Tally connectivity and loaded company")
	serve = subparsers.add_parser("serve", help="Run the local trigger API and scheduled polling")
	serve.add_argument("--no-poll", action="store_true", help="Only serve the local trigger API")
	api = subparsers.add_parser("api", help="Call any Frappe REST or whitelisted API path")
	api.add_argument("method", choices=("GET", "POST", "PUT", "DELETE"))
	api.add_argument("path")
	api.add_argument("--data", default="{}", help="JSON request object")
	return parser


def main(argv=None):
	args = _parser().parse_args(argv)
	logging.basicConfig(
		level=logging.DEBUG if args.verbose else logging.INFO,
		format="%(asctime)s %(levelname)s %(message)s",
	)
	try:
		config = BridgeConfig.load(args.config)
		frappe = FrappeClient(
			config.frappe_url,
			config.api_key,
			config.api_secret,
			config.request_timeout_seconds,
		)
		tally = TallyClient(config.tally_url, config.request_timeout_seconds)
		service = SyncService(config, frappe, tally)
		if args.command == "sync":
			result = service.sync_once(limit=args.limit).to_dict()
			print(json.dumps(result, indent=2))
			return 1 if result["error"] or result["failed"] else 0
		if args.command == "status":
			print(json.dumps(service.health(), indent=2))
			return 0
		if args.command == "api":
			print(json.dumps(frappe.request(args.method, args.path, json.loads(args.data)), indent=2))
			return 0
		if not args.no_poll:
			start_polling(service, config.poll_interval_seconds)
		server = BridgeHTTPServer((config.listen_host, config.listen_port), service)
		logging.info("Bridge listening on http://%s:%s", config.listen_host, config.listen_port)
		server.serve_forever()
		return 0
	except (BridgeRequestError, OSError, ValueError, json.JSONDecodeError) as exc:
		print(f"error: {exc}", file=sys.stderr)
		return 2


if __name__ == "__main__":
	raise SystemExit(main())
