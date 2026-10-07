"""Fail-closed entry point for an isolated synthetic OEM Bench.

Run from the Bench root: env/bin/python apps/srv_erp/ops/oem/guard.py
    --site oem-test.localhost migrate
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse

ROOT = Path('/home/bhickta/development')
BENCH = ROOT / 'oem-bench'
SITES = {'oem-dev.localhost': '_oem_dev', 'oem-test.localhost': '_oem_test'}
REDIS = {'redis_cache': 13011, 'redis_queue': 11011, 'redis_socketio': 11011}


def inspect(bench, site):
    bench = Path(bench).resolve()
    if bench != BENCH or site not in SITES:
        raise ValueError('Only the declared synthetic OEM Bench/sites are allowed')
    config = json.loads((bench / 'sites/common_site_config.json').read_text())
    config.update(json.loads((bench / 'sites' / site / 'site_config.json').read_text()))
    if config.get('db_name') != SITES[site] or config.get('db_host') != '127.0.0.1' or int(config.get('db_port', 0)) != 3311:
        raise ValueError('Database must be the dedicated OEM instance and database')
    if config.get('db_user', config['db_name']) != SITES[site]:
        raise ValueError('Unexpected database user')
    if config.get('db_socket') or config.get('db_ssl_ca') or config.get('db_ssl_cert'):
        raise ValueError('Unexpected external database configuration')
    for key, port in REDIS.items():
        endpoint = urlparse(config.get(key, ''))
        if endpoint.hostname != '127.0.0.1' or endpoint.port != port or endpoint.scheme != 'redis':
            raise ValueError('Redis must use the dedicated OEM ports')
    if not config.get('mute_emails') or not config.get('pause_scheduler'):
        raise ValueError('Outbound email/scheduler must be disabled')
    for app in (bench / 'apps').iterdir():
        if not app.resolve().is_relative_to(ROOT):
            raise ValueError('All app paths must be under development')
    return bench


def main():
    if len(sys.argv) < 4 or sys.argv[1] != '--site':
        raise SystemExit('Usage: guard.py --site oem-test.localhost <bench-command>')
    bench = inspect(Path.cwd(), sys.argv[2])
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    return subprocess.call([str(bench / 'env/bin/python'), '-m', 'frappe.utils.bench_helper', 'frappe', *sys.argv[1:]], cwd=bench)


if __name__ == '__main__':
    sys.exit(main())
