#!/usr/bin/env python3
"""Remove production integrations from the local development database before serving it."""

import argparse
import json
import uuid
from pathlib import Path

import pymysql
from cryptography.fernet import Fernet

BENCH = Path("/home/bhickta/development/dev-frappe-bench")
SITE = "deverp.srvelectricals.in"
TABLE_SETTINGS = {
    "Email Account": {"enable_incoming": 0, "enable_outgoing": 0},
    "Webhook": {"enabled": 0},
    "Notification": {"enabled": 0},
    "Auto Repeat": {"disabled": 1},
    "Server Script": {"disabled": 1},
    "Scheduled Job Type": {"stopped": 1},
    "Social Login Key": {"enable_social_login": 0},
    "Google Calendar": {"enable": 0},
    "Google Contacts": {"enable": 0},
}
SINGLE_SETTINGS = {
    "System Settings": {"enable_scheduler": "0", "enable_two_factor_auth": "0"},
    "GST Settings": {"enable_api": "0", "sandbox_mode": "1"},
    "Dropbox Settings": {"enabled": "0", "allow_dropbox_access": "0"},
    "S3 Backup Settings": {"enabled": "0"},
    "Google Drive": {"enable": "0"},
    "Google Settings": {"enable": "0", "google_drive_picker_enabled": "0", "api_key": ""},
    "SMS Settings": {"sms_gateway_url": ""},
    "Website Settings": {
        "app_name": "SRV ERP DEVELOPMENT",
        "title_prefix": "[DEV]",
        "enable_google_indexing": "0",
    },
}


def connect(config_only=False):
    config = json.loads((BENCH / "sites" / SITE / "site_config.json").read_text())
    common = json.loads((BENCH / "sites/common_site_config.json").read_text())
    effective = common | config
    expected = {"db_host": "127.0.0.1", "db_port": 3310, "db_name": "dev_srv_erp"}
    for key, value in expected.items():
        if effective.get(key) != value:
            raise SystemExit(f"Refusing to connect: {key} must be {value!r}")
    for key in ("pause_scheduler", "disable_scheduler", "mute_emails"):
        if effective.get(key) != 1:
            raise SystemExit(f"Refusing to proceed: {key} must be 1")
    if effective.get("db_ssl") or effective.get("server_script_enabled"):
        raise SystemExit("Unexpected production database or server-script configuration")
    for key, port in (("redis_cache", 13010), ("redis_queue", 11010), ("redis_socketio", 13010)):
        if effective.get(key) != f"redis://127.0.0.1:{port}":
            raise SystemExit(f"Unexpected Redis endpoint: {key}")
    if config_only:
        print("Development configuration verified: local database and dedicated Redis endpoints.")
        return
    return pymysql.connect(
        host=effective["db_host"], port=effective["db_port"],
        user=effective.get("db_user", effective["db_name"]),
        password=effective["db_password"], database=effective["db_name"],
        charset="utf8mb4", autocommit=False,
    )


def run(apply=False):
    connection = connect()
    problems = []
    with connection, connection.cursor() as cursor:
        cursor.execute("SHOW TABLES")
        tables = {row[0] for row in cursor.fetchall()}
        for doctype, values in TABLE_SETTINGS.items():
            table = "tab" + doctype
            if table not in tables:
                continue
            cursor.execute(f"SHOW COLUMNS FROM `{table}`")
            columns = {row[0] for row in cursor.fetchall()}
            for field, value in values.items():
                if field not in columns:
                    continue
                if apply:
                    cursor.execute(f"UPDATE `{table}` SET `{field}`=%s", (value,))
                cursor.execute(f"SELECT COUNT(*) FROM `{table}` WHERE COALESCE(`{field}`,0) <> %s", (value,))
                if cursor.fetchone()[0]:
                    problems.append(f"{doctype}.{field}")
        for doctype, values in SINGLE_SETTINGS.items():
            for field, value in values.items():
                if apply:
                    cursor.execute("DELETE FROM tabSingles WHERE doctype=%s AND field=%s", (doctype, field))
                    cursor.execute("INSERT INTO tabSingles (doctype,field,value) VALUES (%s,%s,%s)", (doctype, field, value))
                cursor.execute("SELECT value FROM tabSingles WHERE doctype=%s AND field=%s", (doctype, field))
                rows = cursor.fetchall()
                if not rows or any(str(row[0]) != value for row in rows):
                    problems.append(f"{doctype}.{field}")
        if apply:
            cursor.execute("DELETE FROM tabDefaultValue WHERE defkey='suspend_email_queue'")
            cursor.execute("INSERT INTO tabDefaultValue (name,parent,parenttype,parentfield,defkey,defvalue) VALUES (%s,'__default','__default','system_defaults','suspend_email_queue','1')", (uuid.uuid4().hex,))
            # Preserve login password hashes, but erase reusable production secrets.
            cursor.execute("DELETE FROM `__Auth` WHERE encrypted=1")
            cursor.execute("UPDATE tabUser SET api_key=NULL, api_secret=NULL")
            for table in ("tabSessions", "tabOAuth Bearer Token", "tabOAuth Authorization Code", "tabWeb Page View"):
                if table in tables:
                    cursor.execute(f"DELETE FROM `{table}`")
            cursor.execute("UPDATE `tabEmail Queue` SET status='Error', error='Sending disabled in development' WHERE status IN ('Not Sent','Sending','Partially Sent')")
            cursor.execute("UPDATE tabSingles SET value='' WHERE field REGEXP '(api_key|api_secret|access_token|refresh_token|access_key_id|secret_access_key|app_access_key|authorization_code)$'")
            connection.commit()
            # After erasing encrypted production values, use an independent master key.
            site_config = BENCH / "sites" / SITE / "site_config.json"
            config = json.loads(site_config.read_text())
            config["encryption_key"] = Fernet.generate_key().decode()
            site_config.write_text(json.dumps(config, indent=2) + "\n")
            site_config.chmod(0o600)
        for label, query in {
            "encrypted production secrets": "SELECT COUNT(*) FROM `__Auth` WHERE encrypted=1",
            "production API keys": "SELECT COUNT(*) FROM tabUser WHERE COALESCE(api_key,'')<>'' OR COALESCE(api_secret,'')<>''",
            "pending outbound emails": "SELECT COUNT(*) FROM `tabEmail Queue` WHERE status IN ('Not Sent','Sending','Partially Sent')",
        }.items():
            cursor.execute(query)
            count = cursor.fetchone()[0]
            if count:
                problems.append(f"{label}: {count}")
        cursor.execute("SELECT defvalue FROM tabDefaultValue WHERE parent='__default' AND defkey='suspend_email_queue'")
        if cursor.fetchall() != (("1",),):
            problems.append("email queue suspension")
    if problems:
        raise SystemExit("Isolation checks failed: " + ", ".join(problems))
    print("Development isolation verified: local database/Redis, email and integrations disabled, production secrets removed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Sanitize the local development database; default only verifies")
    parser.add_argument("--config-only", action="store_true", help="Validate endpoints before the local database starts")
    args = parser.parse_args()
    if args.config_only:
        connect(config_only=True)
    else:
        run(args.apply)
