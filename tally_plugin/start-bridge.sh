#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
	echo "Python 3.10 or newer is required on the Linux host."
	exit 2
fi

if [ ! -f "tally-bridge.json" ]; then
	echo "Copy tally-bridge.example.json to tally-bridge.json and fill in the connection details first."
	exit 2
fi

exec python3 -m srv_erp.tally_bridge --config tally-bridge.json serve --no-poll
