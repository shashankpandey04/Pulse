"""End-to-end smoke test for Task 3: incidents/metrics/reliability/public/notification/dashboard.

Run:  D:\\Pulse\\backend\\.venv\\Scripts\\python.exe D:\\Pulse\\smoke_task3.py
"""

import asyncio
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ["PULSE_MONGO_DB"] = "pulse_test"
os.environ["PULSE_WEBHOOK_URL"] = "http://127.0.0.1:9900"
os.environ["PULSE_ADMIN_EMAIL"] = "admin@example.com"
os.environ["PULSE_ADMIN_PASSWORD"] = "admin-password-1"

sys.path.insert(0, r"D:\Pulse\backend")

from fastapi.testclient import TestClient

from core import database
from core.scheduler import run_sweep
from main import app

passed = 0


def ok(label: str) -> None:
    global passed
    passed += 1
    print(f"  PASS  {label}")


def sweep_once(service_id: str) -> None:
    database.update_one("services", {"service_id": service_id}, {"monitoring.next_check_at": None})
    asyncio.run(run_sweep())


fixture_state = {"mode": "healthy"}


class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        if fixture_state["mode"] == "healthy":
            body, code = b"ok", 200
        else:
            body, code = b"boom", 500
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


server = HTTPServer(("127.0.0.1", 8972), Fixture)
threading.Thread(target=server.serve_forever, daemon=True).start()

database.get_db().client.drop_database("pulse_test")

with TestClient(app) as client:
    # --- accounts -------------------------------------------------------------
    r = client.post("/auth/register", json={"email": "bob@example.com", "password": "bob-pass-123"})
    subscriber_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post("/auth/register", json={"email": "alice@example.com", "password": "alice-pass-1"})
    alice_token = r.json()
    alice_uid = alice_token["user"]["uid"]
    admin_headers = {
        "Authorization": "Bearer "
        + client.post("/auth/login", json={"email": "admin@example.com", "password": "admin-password-1"}).json()[
            "access_token"
        ]
    }
    client.patch(f"/admin/users/{alice_uid}", json={"role": "operator"}, headers=admin_headers)
    operator_headers = {"Authorization": f"Bearer {alice_token['access_token']}"}
    ok("accounts ready (admin, operator, subscriber)")

    # --- catalogue + an incident via the CRON ---------------------------------
    r = client.post(
        "/catalogue",
        json={
            "name": "Checkout API",
            "health_url": "http://127.0.0.1:8972/health",
            "check_interval_seconds": 5,
            "timeout_seconds": 1,
            "owner_email": "alice@example.com",
            "reliability_target": 99.9,
        },
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    service_id = r.json()["service_id"]

    fixture_state["mode"] = "broken"
    for _ in range(3):
        sweep_once(service_id)
    incident = database.find_one("incidents", {"service_id": service_id})
    assert incident and incident["status"] == "open"
    incident_id = incident["incident_id"]
    ok("CRON opened an incident")

    # --- RBAC on the new routers ---------------------------------------------
    for path in ("/incidents", "/metrics", "/reliability", "/notifications"):
        r = client.get(path, headers=subscriber_headers)
        assert r.status_code == 403, (path, r.status_code)
    r = client.get("/dashboard")
    assert r.status_code == 401
    ok("subscriber blocked from ops routers (403), anonymous dashboard 401")

    # --- incidents router -----------------------------------------------------
    r = client.get("/incidents", headers=operator_headers)
    assert r.status_code == 200 and r.json()["total"] == 1
    r = client.get("/incidents", headers=operator_headers, params={"status": "open"})
    assert r.json()["total"] == 1
    r = client.get("/incidents", headers=operator_headers, params={"status": "resolved"})
    assert r.json()["total"] == 0
    ok("operator lists/filters incidents")

    r = client.get(f"/incidents/{incident_id}", headers=operator_headers)
    assert r.status_code == 200 and r.json()["timeline"][0]["type"] == "opened"
    ok("operator views incident timeline")

    r = client.patch(
        f"/incidents/{incident_id}/ack", json={"note": "On it — investigating."}, headers=operator_headers
    )
    assert r.status_code == 200 and r.json()["status"] == "acknowledged"
    assert r.json()["acknowledged_by_email"] == "alice@example.com"
    assert any(e["type"] == "acknowledged" for e in r.json()["timeline"])
    r = client.patch(f"/incidents/{incident_id}/ack", json={}, headers=operator_headers)
    assert r.status_code == 409
    ok("ack sets acknowledged + timeline event; re-ack -> 409")

    r = client.post(
        f"/incidents/{incident_id}/notes", json={"note": "Root cause identified."}, headers=operator_headers
    )
    assert r.status_code == 200
    r = client.post(
        f"/incidents/{incident_id}/notes",
        json={"note": "Internal: suspected deploy regression.", "visibility": "internal"},
        headers=operator_headers,
    )
    assert r.status_code == 200
    timeline = r.json()["timeline"]
    assert sum(1 for e in timeline if e["type"] == "note") == 2
    ok("public + internal notes appended")

    # public page must show public notes only, never internal ones
    slug = "checkout-api"
    r = client.get(f"/public/status/{slug}")
    assert r.status_code == 200
    detail = r.json()
    all_messages = " | ".join(e["message"] for i in detail["incidents"] for e in i["events"])
    assert "Root cause identified." in all_messages
    assert "Internal: suspected deploy regression." not in all_messages
    assert "alice@example.com" not in str(detail)  # no owner emails leak
    ok("public detail shows public notes only; no internal data leak")

    # --- manual resolve via API -----------------------------------------------
    r = client.post(f"/incidents/{incident_id}/resolve", json={"note": "Rollback complete."}, headers=operator_headers)
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    assert r.json()["duration_seconds"] is not None
    r = client.post(f"/incidents/{incident_id}/resolve", json={}, headers=operator_headers)
    assert r.status_code == 409
    ok("manual resolve works; re-resolve -> 409")

    r = client.get("/notifications", headers=admin_headers)
    assert r.status_code == 200
    types = {n["event_type"] for n in r.json()["notifications"]}
    assert {"incident_opened", "incident_resolved"} <= types
    ok("notification delivery history recorded")

    # --- metrics ---------------------------------------------------------------
    fixture_state["mode"] = "healthy"
    sweep_once(service_id)
    sweep_once(service_id)  # 2 consecutive successes -> state back to healthy

    r = client.get("/metrics", headers=operator_headers)
    assert r.status_code == 200
    m = r.json()["services"][0]
    assert m["total_checks"] >= 5 and m["failed_checks"] >= 3
    assert 0 < m["success_rate"] < 1
    assert m["mttr_seconds"] is not None and m["mttd_seconds"] is not None
    assert m["open_incidents"] == 0
    ok("metrics overview: checks, rates, MTTD/MTTR computed")

    r = client.get(f"/metrics/{service_id}", headers=operator_headers, params={"window_hours": 24})
    assert r.status_code == 200 and r.json()["service_name"] == "Checkout API"
    r = client.get(f"/metrics/{service_id}/checks", headers=operator_headers, params={"success": False})
    assert r.status_code == 200 and all(c["success"] is False for c in r.json()["checks"])
    assert r.json()["total"] >= 3
    ok("per-service metrics + raw checks with success filter")

    # --- reliability -----------------------------------------------------------
    r = client.get("/reliability", headers=operator_headers)
    assert r.status_code == 200
    rel = r.json()["services"][0]
    assert rel["total_checks"] >= 5 and rel["failed_checks"] >= 3
    assert rel["availability_pct"] < 100 and rel["meeting_target"] is False
    assert rel["consumed_downtime_minutes"] > 0 and rel["error_budget_pct"] == 0.1
    assert rel["incident_count"] == 1
    r = client.get(f"/reliability/{service_id}", headers=operator_headers)
    assert r.status_code == 200 and r.json()["service_id"] == service_id
    ok("reliability: availability vs target + error budget")

    # --- public status page ----------------------------------------------------
    r = client.get("/public/status")
    assert r.status_code == 200
    page = r.json()
    assert page["summary"].get("healthy") == 1 and page["colors"]["flaky"] == "#800000"
    assert page["services"][0]["state"] == "healthy"
    assert page["active_incidents"] == []  # incident resolved
    r = client.get("/public/status/unknown-slug")
    assert r.status_code == 404
    ok("public status page (no auth) + 404 unknown slug")

    # --- dashboard per role -----------------------------------------------------
    r = client.get("/dashboard", headers=subscriber_headers)
    assert r.status_code == 200
    d = r.json()
    assert d["role"] == "subscriber" and d["status"] is not None and d["services"] is None
    assert d["status"]["summary"]["healthy"] == 1
    ok("subscriber dashboard: status page view only")

    r = client.get("/dashboard", headers=operator_headers)
    assert r.status_code == 200
    d = r.json()
    assert d["role"] == "operator"
    assert d["status"] is None and len(d["services"]) == 1
    assert d["incidents_summary"]["resolved_24h"] == 1 and d["incidents_summary"]["open"] == 0
    assert d["metrics"] and d["metrics"]["services"][0]["mttr_seconds"] is not None
    assert d["reliability"] and d["users_summary"] is None and d["notifications_summary"] is None
    ok("operator dashboard: services + incidents + metrics + reliability")

    r = client.get("/dashboard", headers=admin_headers)
    assert r.status_code == 200
    d = r.json()
    assert d["role"] == "admin"
    assert d["users_summary"]["total"] == 3 and d["users_summary"]["by_role"]["admin"] == 1
    assert d["notifications_summary"]["total"] >= 2
    assert d["reliability"] and d["metrics"]
    ok("admin dashboard: adds users + notifications summaries")

    # --- 404s -------------------------------------------------------------------
    r = client.get("/incidents/00000000-0000-0000-0000-000000000000", headers=operator_headers)
    assert r.status_code == 404
    r = client.get("/metrics/00000000-0000-0000-0000-000000000000", headers=operator_headers)
    assert r.status_code == 404
    r = client.get("/reliability/00000000-0000-0000-0000-000000000000", headers=operator_headers)
    assert r.status_code == 404
    ok("unknown ids -> 404 on incidents/metrics/reliability")

    paths = client.get("/openapi.json").json()["paths"]
    for expected in (
        "/incidents",
        "/metrics",
        "/reliability",
        "/public/status",
        "/notifications",
        "/dashboard",
    ):
        assert any(p == expected or p.startswith(expected + "/") for p in paths), expected
    ok("OpenAPI exposes all Task 3 routers")

print(f"\nALL TASK 3 SMOKE CHECKS PASSED ({passed} checks)")
server.shutdown()
