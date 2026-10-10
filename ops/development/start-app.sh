#!/usr/bin/env bash
# Gate every web/worker startup on development database sanitization.
set -euo pipefail
DEV_BENCH=/home/bhickta/development/dev-frappe-bench
if [[ ${1:-} == --socketio ]]; then
    shift
    # Node leaves its Unix socket behind after shutdown. Remove only a dead socket.
    "$DEV_BENCH/env/bin/python" - <<'PY'
import errno
import socket
import stat
from pathlib import Path
path = Path('/home/bhickta/development/dev-frappe-bench/run/socketio.sock')
if path.exists():
    if not stat.S_ISSOCK(path.lstat().st_mode):
        raise SystemExit('Refusing to replace a non-socket realtime path')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(1)
        try:
            client.connect(str(path))
        except OSError as error:
            if error.errno == errno.ECONNREFUSED:
                path.unlink()
            else:
                raise
        else:
            raise SystemExit('A development realtime server is already listening')
PY
fi
for ((i=0; i<45; i++)); do
    if "$DEV_BENCH/env/bin/python" "$DEV_BENCH/config/sanitize.py"; then
        exec "$@"
    fi
    sleep 1
done
echo 'Development isolation check failed; application will remain stopped.' >&2
exit 1
