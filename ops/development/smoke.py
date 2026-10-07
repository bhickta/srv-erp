#!/usr/bin/env python3
"""Exercise the isolated bench locally; remove temporary credentials/documents afterwards."""

import os
import secrets
import time

import requests

from sanitize import BENCH, SITE, connect, run


def main():
    run()
    connect().close()
    os.chdir(BENCH / "sites")
    import frappe
    from frappe.utils.file_manager import save_file
    from frappe.utils.password import set_encrypted_password

    frappe.init(site=SITE)
    frappe.connect()
    frappe.set_user("Administrator")
    base = "http://127.0.0.1:8081"
    headers = {"Host": SITE, "X-Forwarded-Proto": "https"}
    api_key, api_secret = secrets.token_hex(20), secrets.token_hex(32)
    todo_name, file_doc, job = None, None, None
    try:
        response = requests.get(base + "/login", headers=headers, timeout=20)
        assert response.status_code == 200, f"Login page: {response.status_code}"
        assert response.headers.get("X-SRV-Environment") == "development"
        response = requests.get(base + "/api/method/ping", headers=headers, timeout=20)
        assert response.json() == {"message": "pong"}
        response = requests.get(base + "/assets/frappe/images/frappe-framework-logo.svg", headers=headers, timeout=20)
        assert response.status_code == 200, f"Static asset: {response.status_code}"
        response = requests.get(base + "/socket.io/?EIO=4&transport=polling", headers=headers, timeout=20)
        assert response.status_code == 200 and response.text.startswith("0{"), "Realtime handshake failed"
        print("PASS: login page, ping, static assets, realtime handshake")

        frappe.db.set_value("User", "Administrator", "api_key", api_key, update_modified=False)
        set_encrypted_password("User", "Administrator", api_secret, fieldname="api_secret")
        frappe.db.commit()
        auth_headers = headers | {"Authorization": f"token {api_key}:{api_secret}"}
        response = requests.get(base + "/api/method/frappe.auth.get_logged_user", headers=auth_headers, timeout=20)
        assert response.status_code == 200 and response.json()["message"] == "Administrator", "API authentication failed"
        response = requests.get(base + "/api/resource/Sales Order", params={"limit_page_length": 1}, headers=auth_headers, timeout=20)
        assert response.status_code == 200 and "data" in response.json(), "Copied ERP data unavailable"
        response = requests.get(base + "/app", headers=auth_headers, timeout=30)
        assert response.status_code == 200, f"Desk: {response.status_code}"
        print("PASS: authenticated ERP data and Desk")

        response = requests.post(base + "/api/resource/ToDo", json={"description": "Development isolation smoke test " + secrets.token_hex(8)}, headers=auth_headers, timeout=20)
        assert response.status_code == 200, f"Development write: {response.status_code}"
        todo_name = response.json()["data"]["name"]
        response = requests.delete(base + "/api/resource/ToDo/" + todo_name, headers=auth_headers, timeout=20)
        assert response.status_code == 202, f"Development delete: {response.status_code}"
        todo_name = None
        print("PASS: dev-only document creation and deletion")

        content = ("private development smoke test " + secrets.token_hex(16)).encode()
        file_doc = save_file("dev-smoke-" + secrets.token_hex(8) + ".txt", content, "User", "Administrator", is_private=1)
        frappe.db.commit()
        response = requests.get(base + file_doc.file_url, headers=headers, timeout=20)
        assert response.status_code in (403, 404), "Private file exposed to guest"
        response = requests.get(base + "/protected/private/files/" + file_doc.file_name, headers=auth_headers, timeout=20)
        assert response.status_code == 404, "Internal file path exposed"
        response = requests.get(base + file_doc.file_url, headers=auth_headers, timeout=20)
        assert response.status_code == 200 and response.content == content, "Authenticated private download failed"
        print("PASS: private file authorization and download")

        job = frappe.enqueue("frappe.utils.now", queue="short", job_id="dev-smoke-" + secrets.token_hex(8))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            status = job.get_status(refresh=True)
            if status in ("finished", "failed"):
                break
            time.sleep(0.5)
        assert job.get_status(refresh=True) == "finished", "Background worker failed"
        print("PASS: isolated background job")
    finally:
        frappe.db.rollback()
        if todo_name:
            frappe.delete_doc("ToDo", todo_name, force=True, ignore_permissions=True)
        if file_doc:
            frappe.delete_doc("File", file_doc.name, force=True, ignore_permissions=True)
        if job:
            job.delete()
        frappe.db.set_value("User", "Administrator", {"api_key": None, "api_secret": None}, update_modified=False)
        frappe.db.sql("DELETE FROM `__Auth` WHERE doctype='User' AND name='Administrator' AND fieldname='api_secret'")
        frappe.db.commit()
        frappe.clear_cache(user="Administrator")
        frappe.destroy()
    run()


if __name__ == "__main__":
    main()
