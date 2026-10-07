#!/usr/bin/env bash
# Run as root after reviewing. All production bench files remain read-only.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run this activation script with sudo.' >&2; exit 1; }
DEV_BENCH=/home/bhickta/development/dev-frappe-bench
DEV_OPS=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
DEV_DOMAIN=deverp.srvelectricals.in
DEV_PUBLIC_IP=13.205.90.92
DEV_VHOST=/etc/nginx/conf.d/dev-frappe-bench.conf
DEV_NGINX_CONFIG="$DEV_BENCH/config/nginx-public.conf"

runuser -u bhickta -- "$DEV_BENCH/env/bin/python" "$DEV_OPS/sanitize.py" --config-only
if [[ -e $DEV_VHOST || -L $DEV_VHOST ]]; then
    [[ $(readlink -f -- "$DEV_VHOST") == "$DEV_NGINX_CONFIG" ]] || {
        echo "Refusing to replace an unrelated Nginx configuration: $DEV_VHOST" >&2; exit 1;
    }
fi

install -o bhickta -g bhickta -m 0644 "$DEV_OPS/sanitize.py" "$DEV_BENCH/config/sanitize.py"
install -o bhickta -g bhickta -m 0644 "$DEV_OPS/start-app.sh" "$DEV_BENCH/config/start-app.sh"
install -o bhickta -g bhickta -m 0644 "$DEV_OPS/dev-frappe-bench.service" "$DEV_BENCH/config/dev-frappe-bench.service"
if [[ ! -e /etc/systemd/system/dev-frappe-bench.service ]]; then
    ln -s "$DEV_BENCH/config/dev-frappe-bench.service" /etc/systemd/system/dev-frappe-bench.service
else
    [[ $(readlink -f /etc/systemd/system/dev-frappe-bench.service) == "$DEV_BENCH/config/dev-frappe-bench.service" ]] || exit 1
fi
systemctl daemon-reload
systemctl enable dev-frappe-bench.service
if ! systemctl is-active --quiet dev-frappe-bench.service; then
    # Stop only the temporary development supervisor before systemd takes ownership.
    if [[ -S $DEV_BENCH/run/supervisor.sock ]]; then
        DEV_OLD_SUPERVISOR_PID=$(runuser -u bhickta -- /usr/bin/supervisorctl -c "$DEV_BENCH/config/supervisord.conf" pid)
        [[ $DEV_OLD_SUPERVISOR_PID =~ ^[0-9]+$ ]] || exit 1
        runuser -u bhickta -- /usr/bin/supervisorctl -c "$DEV_BENCH/config/supervisord.conf" shutdown
        for ((i=0; i<60; i++)); do
            if ! kill -0 "$DEV_OLD_SUPERVISOR_PID" 2>/dev/null && [[ ! -S $DEV_BENCH/run/supervisor.sock ]]; then break; fi
            sleep 1
        done
        if kill -0 "$DEV_OLD_SUPERVISOR_PID" 2>/dev/null; then
            echo 'Development Supervisor has not stopped; refusing to start a duplicate.' >&2
            exit 1
        fi
        [[ ! -S $DEV_BENCH/run/supervisor.sock ]] || exit 1
    fi
    systemctl enable --now dev-frappe-bench.service
fi
for ((i=0; i<60; i++)); do
    if curl --fail --silent --max-time 3 -H "Host: $DEV_DOMAIN" http://127.0.0.1:8081/api/method/ping >/dev/null; then break; fi
    sleep 1
done
curl --fail --silent --show-error --max-time 10 -H "Host: $DEV_DOMAIN" http://127.0.0.1:8081/api/method/ping >/dev/null
runuser -u bhickta -- "$DEV_BENCH/env/bin/python" "$DEV_OPS/sanitize.py"

# Keep a working HTTPS vhost when rerunning an already completed activation.
if [[ ! -f $DEV_BENCH/runtime/letsencrypt/live/$DEV_DOMAIN/fullchain.pem ]]; then
    install -o bhickta -g bhickta -m 0644 "$DEV_OPS/nginx-http.conf" "$DEV_NGINX_CONFIG"
else
    install -o bhickta -g bhickta -m 0644 "$DEV_OPS/nginx-https.conf" "$DEV_NGINX_CONFIG"
fi
if [[ ! -L $DEV_VHOST ]]; then
    ln -s "$DEV_NGINX_CONFIG" "$DEV_VHOST"
    if ! nginx -t; then
        rm -- "$DEV_VHOST"
        echo 'Development Nginx configuration rejected; production Nginx was not reloaded.' >&2
        exit 1
    fi
else
    nginx -t
fi
systemctl reload nginx

if ! dig @1.1.1.1 +short A "$DEV_DOMAIN" | grep -Fxq "$DEV_PUBLIC_IP"; then
    echo "Development services installed. DNS pending: create A record deverp -> $DEV_PUBLIC_IP, then rerun this script."
    exit 0
fi
certbot certonly --webroot --webroot-path "$DEV_BENCH/runtime/acme" \
    --domain "$DEV_DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email \
    --config-dir "$DEV_BENCH/runtime/letsencrypt" \
    --work-dir "$DEV_BENCH/runtime/certbot-work" \
    --logs-dir "$DEV_BENCH/logs/certbot" --keep-until-expiring
install -o bhickta -g bhickta -m 0644 "$DEV_OPS/nginx-https.conf" "$DEV_NGINX_CONFIG"
nginx -t
systemctl reload nginx
for DEV_UNIT in dev-frappe-cert-renew.service dev-frappe-cert-renew.timer; do
    install -o bhickta -g bhickta -m 0644 "$DEV_OPS/$DEV_UNIT" "$DEV_BENCH/config/$DEV_UNIT"
    if [[ ! -e /etc/systemd/system/$DEV_UNIT ]]; then
        ln -s "$DEV_BENCH/config/$DEV_UNIT" "/etc/systemd/system/$DEV_UNIT"
    else
        [[ $(readlink -f "/etc/systemd/system/$DEV_UNIT") == "$DEV_BENCH/config/$DEV_UNIT" ]] || exit 1
    fi
done
systemctl daemon-reload
systemctl enable --now dev-frappe-cert-renew.timer
curl --fail --silent --show-error --max-time 15 "https://$DEV_DOMAIN/api/method/ping"
echo
echo "Development ERP is live at https://$DEV_DOMAIN/"
