#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if ! command -v python3 >/dev/null 2>&1; then
	echo "Python 3.10 or newer is required on the Linux host."
	exit 2
fi

if [ ! -f "$SCRIPT_DIR/tally-bridge.json" ]; then
	echo "Copy tally-bridge.example.json to tally-bridge.json and fill in the connection details first."
	exit 2
fi

if [ -d "$SCRIPT_DIR/srv_erp/tally_bridge" ]; then
	BRIDGE_ROOT=$SCRIPT_DIR
elif [ -d "$SCRIPT_DIR/../srv_erp/tally_bridge" ]; then
	BRIDGE_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
else
	echo "The Python bridge package srv_erp/tally_bridge is missing."
	echo "Extract the complete SRV-Tally-Bridge ZIP; do not copy only tally_plugin files."
	exit 2
fi

cd "$BRIDGE_ROOT"
exec python3 -m srv_erp.tally_bridge --config "$SCRIPT_DIR/tally-bridge.json" serve --no-poll
