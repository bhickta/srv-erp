# SRV ERP development bench

The development bench is an independent copy of production under
`/home/bhickta/development/dev-frappe-bench`, with site
`deverp.srvelectricals.in`. Its custom app tracks the GitHub `dev` branch.
Production remains under `/home/frappe/prod-frappe-bench` and is read only.

## Replica provenance

- Database: `20261007_173003-proderp-database.sql.gz`, created on October 7,
  2026 at 12:01 UTC (17:31 IST).
- Backup SHA-256: `a3dbe371b1a63b0218292e6a066060a2a9e4eaadd1767e29b625fe8bcb9aca05`.
- Uploaded public/private files were copied independently from production at
  setup time. No file archive accompanied the scheduled database backup, so
  files and database are not a single point-in-time snapshot.
- Python 3.14.5 and the installed production Python dependencies were copied
  into an independent environment. Editable import paths and asset symlinks
  were changed to the development bench. No app, environment, upload or Redis
  storage points back to production.
- Frappe 15.111.1: `8831f757fcd7367bb2345823d7f4f71459742a82`.
- ERPNext 15.111.0: `48f6a9779767aaa890a60085a438459cfd851ed0`.
- India Compliance 15.14.4: `57ac27ba6345fdd29909cdd66efdff9bfd2f4eda`.
- SRV ERP: `a41f98875c8f874819051eed6b01980fe114a1b8`, starting point of `dev`.
- MariaDB 11.8.8, matching the production database version. Official ARM64
  Ubuntu 24.04 packages were downloaded and extracted under the bench, with
  checksums verified against package metadata. No system MariaDB installation
  or production RDS database was changed. Package binaries use bench-local
  libraries and configuration.

The exact manifest is `config/replica-manifest.json` in the bench. Existing
uncommitted production changes in the framework apps were copied too; those
apps are pinned to production's deployed source rather than updated upstream.

## Isolation

| Component | Development | Production |
| --- | --- | --- |
| Database | `127.0.0.1:3310`, `dev_srv_erp` | AWS RDS, production database |
| Redis cache | `127.0.0.1:13010` | `127.0.0.1:13000` |
| Redis queue | `127.0.0.1:11010` | `127.0.0.1:11000` |
| Application | `127.0.0.1:8010` | `127.0.0.1:8000` |
| Realtime | bench-local Unix socket | port `9000` |
| Static/private file proxy | `127.0.0.1:8081` | production Nginx configuration |
| Process manager | bench-local supervisor socket | system production Supervisor |

The local database account has permissions only for `dev_srv_erp`.
Development has no production RDS connection configuration. Scheduled jobs,
incoming/outgoing email accounts, webhooks, notifications, auto-repeat,
server scripts, OAuth/social login and GST/cloud backup integrations are
disabled. Reusable encrypted integration secrets, API keys, tokens and
production sessions are removed. Password hashes and business records are
preserved; existing username/password logins work. The development encryption
key is rotated after production secrets are erased. Two-factor authentication
is disabled in development because copied OTP secrets were removed.

The scheduler process is deliberately absent. A worker remains available for
development background tasks. `start-app.sh` checks database isolation before
every web, worker and realtime startup. It also removes only a stale realtime
Unix socket after a restart. `sanitize.py` refuses nonlocal database or shared
Redis endpoints; without `--apply` it performs read-only verification.

Development mode and tests are enabled. The app title identifies DEVELOPMENT;
Nginx adds a development response header and asks search engines not to index
the site. Private file authorization is enforced by Frappe before an internal
Nginx file redirect.

The two benches share this server's CPU, memory and disk. Once activated under
systemd, development has a one-CPU quota, 1.5 GiB memory pressure threshold,
2 GiB memory limit, lower CPU/IO priority, and a 128-task limit. This provides
service/data separation; a separate server would provide hardware isolation.
Do not run unrestricted bulk tests on the shared host.

## Public HTTPS activation

Until activation, the tested bench runs locally using its own Supervisor
daemon. It is not yet publicly accessible and does not yet start after a
server reboot.

1. Create a DNS **A** record: **deverp → 13.205.90.92**. The working record for
   `proderp` is a separate hostname. Remove any conflicting AAAA record unless
   IPv6 points to this server too.
2. Review `activate.sh` and the Nginx/systemd templates in this directory.
3. From a sudo-capable shell, run:

   ```bash
   sudo bash /home/bhickta/development/srv-erp/ops/development/activate.sh
   ```

The script validates development isolation and local application health,
switches only the development Supervisor into its dedicated systemd service,
adds `/etc/nginx/conf.d/dev-frappe-bench.conf`, validates Nginx and reloads it
gracefully. It never edits a production bench file, restarts production app
processes, or runs a production database command. The existing Nginx service
must reload to pick up the additional development hostname.

If DNS is pending, the service and HTTP hostname are installed; rerun the
script when DNS resolves. Certbot uses a separate configuration/work/log
directory under the development bench and a webroot challenge, without
rewriting production Nginx or using its certificate. A separate renewal timer
renews only the development certificate and gracefully reloads Nginx.

Successful activation prints a public HTTPS `pong`. Check:

```bash
curl --fail https://deverp.srvelectricals.in/api/method/ping
sudo systemctl status dev-frappe-bench.service
sudo systemctl status dev-frappe-cert-renew.timer
curl --fail -o /dev/null https://proderp.srvelectricals.in/login
```

## Developing the custom app

Use the bench app checkout for running changes:

```bash
cd /home/bhickta/development/dev-frappe-bench/apps/srv_erp
git fetch origin
git pull --ff-only origin dev
git switch -c feat/my-change
```

Make focused commits on a feature/fix branch. Test on the development site,
push the feature branch and open a PR into `dev`. Do not merge your own PR.
After review, update `dev` in the bench, build/migrate and restart only dev:

```bash
cd /home/bhickta/development/dev-frappe-bench
bench build --app srv_erp
bench --site deverp.srvelectricals.in migrate
env/bin/python config/sanitize.py --apply
bench --site deverp.srvelectricals.in clear-cache
/usr/bin/supervisorctl -c config/supervisord.conf restart dev-web dev-worker dev-socketio
```

Migration may recreate scheduled-job records, so rerun sanitization before
restarting. Framework schema annotations may change files in this development
checkout during migration; inspect the diff and keep app changes focused.
Promote reviewed work from `dev` to `version-15` through a separate production
PR. The development setup does not deploy to production.

## Verification and process control

```bash
cd /home/bhickta/development/dev-frappe-bench
env/bin/python config/sanitize.py
env/bin/python /home/bhickta/development/srv-erp/ops/development/smoke.py
/usr/bin/supervisorctl -c config/supervisord.conf status
```

The smoke script verifies guest login, assets, realtime, authenticated Desk
and ERP reads, a ToDo create/delete, private-file access controls and an actual
background job. It uses temporary development Administrator API credentials
and removes those credentials/documents in `finally`. Do not run it during
another API-key test involving Administrator.

Always pass the bench-local Supervisor configuration. Never run a blanket
`supervisorctl restart all`, a production `bench` command, or `bench setup
production` on this server. Logs are under the development bench's `logs/`.

## Refreshing production data

Use only an existing scheduled production backup; generating a new backup
inside `/home/frappe` is prohibited by the machine's read-only rule. Stop the
development web/worker/realtime/file-proxy processes before restoring. Keep
an independent development backup if the current test data matters.

Copy the selected production SQL/config backup and uploaded files into this
development bench with restricted backup/config permissions. Restore only
`dev_srv_erp` on `127.0.0.1:3310`, retain the local database credentials and
isolation settings, and copy only the backup's `encryption_key` from its site
configuration. Never copy the production DB host/user/password/domain settings.
Clear only development Redis stores, apply `sanitize.py --apply` before
migration, migrate, sanitize again, then restart only development processes
and rerun the smoke checks. Production credentials remain in the protected
source backup; do not commit backups, site configurations or uploads to Git.
