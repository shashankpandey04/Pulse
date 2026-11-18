"""End-to-end smoke test for Task 2 against a real local MongoDB.

Uses a dedicated test database (PULSE_MONGO_DB=pulse_test), exercises the API
with role-based access control, then runs the health-check CRON against a local
fixture server and verifies: check results stored, state transitions, automated
incident open/close, and webhook notifications recorded.

Run:  D:\\Pulse\\backend\\.venv\\Scripts\\python.exe D:\\Pulse\\smoke_task2.py
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
    """Force one CRON sweep that definitely checks ``service_id`` now."""
    database.update_one("services", {"service_id": service_id}, {"monitoring.next_check_at": None})
    asyncio.run(run_sweep())


# --- fixture: local HTTP server whose mode the test toggles -------------------
fixture_state = {"mode": "healthy"}


class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        if fixture_state["mode"] == "healthy":
            body, code = b"ok", 200
        elif fixture_state["mode"] == "slow":
            time.sleep(0.4)
            body, code = b"slow", 200
        else:
            body, code = b"boom", 500
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence
        pass


server = HTTPServer(("127.0.0.1", 8971), Fixture)
threading.Thread(target=server.serve_forever, daemon=True).start()

# Clean test database
database.get_db().client.drop_database("pulse_test")

with TestClient(app) as client:  # enters lifespan: indexes + scheduler + bootstrap
    # --- auth & RBAC ---------------------------------------------------------
    r = client.post("/auth/register", json={"email": "alice@example.com", "password": "alice-pass-1"})
    assert r.status_code == 201, r.text
    alice = r.json()
    assert alice["user"]["role"] == "subscriber" and alice["token_type"] == "bearer"
    ok("register creates subscriber + returns bearer token")

    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    r = client.get("/auth/me", headers=alice_headers)
    assert r.status_code == 200 and r.json()["email"] == "alice@example.com"
    ok("GET /auth/me")

    r = client.post("/auth/register", json={"email": "alice@example.com", "password": "whatever-123"})
    assert r.status_code == 409
    ok("duplicate email -> 409")

    r = client.post("/auth/login", json={"email": "alice@example.com", "password": "wrong-pass-99"})
    assert r.status_code == 401
    ok("wrong password -> 401")

    r = client.post("/auth/login", json={"email": "alice@example.com", "password": "alice-pass-1"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "subscriber"
    ok("login returns subscriber")

    r = client.get("/admin/users", headers=alice_headers)
    assert r.status_code == 403
    ok("subscriber cannot list users (403)")

    r = client.get("/admin/users")
    assert r.status_code == 401
    ok("anonymous rejected (401)")

    r = client.post("/auth/login", json={"email": "admin@example.com", "password": "admin-password-1"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin", r.text
    admin_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    ok("bootstrapped admin can log in")

    r = client.get("/admin/users", headers=admin_headers)
    assert r.status_code == 200 and r.json()["total"] >= 2
    alice_uid = next(u["uid"] for u in r.json()["users"] if u["email"] == "alice@example.com")
    ok("admin lists users")

    r = client.patch(f"/admin/users/{alice_uid}", json={"role": "operator"}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["role"] == "operator"
    ok("admin upgrades alice -> operator")

    r = client.patch(f"/admin/users/{alice_uid}", json={"active": False}, headers=admin_headers)
    assert r.status_code == 200
    r = client.get("/auth/me", headers=alice_headers)
    assert r.status_code == 401, "deactivated account must not pass auth"
    ok("deactivated account token rejected (401)")

    r = client.patch(f"/admin/users/{alice_uid}", json={"active": True}, headers=admin_headers)
    assert r.status_code == 200
    ok("admin reactivates alice")

    r = client.delete(f"/admin/users/{alice_uid}", headers=admin_headers)
    assert r.status_code == 200
    ok("admin soft-deletes account")

    client.patch(f"/admin/users/{alice_uid}", json={"active": True}, headers=admin_headers)
    operator_headers = alice_headers  # role comes from the DB, not the old token claim

    # --- catalogue -----------------------------------------------------------
    svc_payload = {
        "name": "Fixture Service",
        "health_url": "http://127.0.0.1:8971/health",
        "check_interval_seconds": 5,
        "timeout_seconds": 1,
        "owner_email": "alice@example.com",
        "reliability_target": 99.0,
    }
    r = client.post("/catalogue", json=svc_payload, headers=operator_headers)
    assert r.status_code == 403, "operator must not create catalogue entries"
    ok("operator cannot create services (403)")

    r = client.post("/catalogue", json=svc_payload, headers=admin_headers)
    assert r.status_code == 201, r.text
    service_id = r.json()["service_id"]
    assert r.json()["slug"] == "fixture-service" and r.json()["owner_uid"]
    ok("admin registers service (slug derived)")

    r = client.post("/catalogue", json=svc_payload, headers=admin_headers)
    assert r.status_code == 409
    ok("duplicate service -> 409")

    r = client.post(
        "/catalogue",
        json={**svc_payload, "name": "Bad Owner", "owner_email": "ghost@example.com"},
        headers=admin_headers,
    )
    assert r.status_code == 404
    ok("unknown owner email -> 404")

    r = client.get("/catalogue", headers=operator_headers)
    assert r.status_code == 200 and r.json()["total"] == 1
    ok("operator can view catalogue")

    r = client.patch(f"/catalogue/{service_id}", json={"timeout_seconds": 60}, headers=admin_headers)
    assert r.status_code == 422, "timeout(60) must be < interval(5) after merge"
    ok("PATCH revalidates timeout < interval")

    r = client.patch(f"/catalogue/{service_id}", json={"reliability_target": 99.9}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["reliability_target"] == 99.9
    ok("admin patches service")

    # --- states --------------------------------------------------------------
    r = client.get(f"/states/{service_id}", headers=operator_headers)
    assert r.status_code == 200 and r.json()["down"]["consecutive_failures"] == 3
    assert r.json()["colors"]["flaky"] == "#800000"
    ok("default state config returned when none stored")

    r = client.put(f"/states/{service_id}", json={"down": {"consecutive_failures": 3}}, headers=operator_headers)
    assert r.status_code == 200 and r.json()["down"]["consecutive_failures"] == 3
    ok("operator upserts state config")

    r = client.patch(f"/states/{service_id}", json={"slow": {"latency_ms": 300}}, headers=operator_headers)
    assert r.status_code == 200 and r.json()["slow"]["latency_ms"] == 300
    assert r.json()["down"]["consecutive_failures"] == 3, "PATCH must not clobber other policies"
    ok("operator patches only provided policies")

    r = client.get("/states", headers=operator_headers)
    assert r.status_code == 200 and r.json()["total"] == 1
    ok("state configs listed")

    r = client.delete(f"/states/{service_id}", headers=operator_headers)
    assert r.status_code == 403, "only admins may reset configs"
    ok("operator cannot delete state config (403)")

    r = client.delete(f"/states/{service_id}", headers=admin_headers)
    assert r.status_code == 200
    ok("admin resets state config (defaults back)")

    # --- health check CRON ---------------------------------------------------
    fixture_state["mode"] = "broken"  # 3 failures expected (default down policy)
    for _ in range(3):
        sweep_once(service_id)
    service_doc = database.find_one("services", {"service_id": service_id})
    assert service_doc["monitoring"]["current_state"] == "down", service_doc["monitoring"]
    ok("CRON marks service down after 3 failed checks")

    checks = database.find_many("check_results", {"service_id": service_id})
    assert len(checks) == 3 and all(not c["success"] for c in checks)
    ok("every check result stored")

    incident = database.find_one("incidents", {"service_id": service_id})
    assert incident and incident["status"] == "open" and incident["current_state"] == "down"
    assert incident["timeline"][0]["type"] == "opened"
    ok("incident auto-opened with timeline")

    notifications = database.find_many("notifications", {"event_type": "incident_opened"})
    assert len(notifications) == 1 and notifications[0]["service_id"] == service_id
    assert notifications[0]["delivered"] is False  # receiver not running in this test
    ok("webhook notification recorded on incident open")

    # recovery: 2 consecutive successful checks (default recovery policy)
    fixture_state["mode"] = "healthy"
    for _ in range(2):
        sweep_once(service_id)
    service_doc = database.find_one("services", {"service_id": service_id})
    assert service_doc["monitoring"]["current_state"] == "healthy", service_doc["monitoring"]
    ok("service recovers to healthy after 2 successful checks")

    incident = database.find_one("incidents", {"service_id": service_id})
    assert incident["status"] == "resolved" and incident["duration_seconds"] is not None
    ok("incident auto-resolved on recovery")

    notifications = database.find_many("notifications", {"event_type": "incident_resolved"})
    assert len(notifications) == 1
    ok("webhook notification recorded on incident resolve")

    # --- flaky detection -----------------------------------------------------
    # Tight window (3) so flaky fires quickly: 2 failures in 3 checks = 67% > 30%.
    r = client.put(
        f"/states/{service_id}",
        json={"flaky": {"failure_rate": 0.3, "window_size": 3}},
        headers=admin_headers,
    )
    assert r.status_code == 200
    for mode in ("broken", "healthy", "broken"):
        fixture_state["mode"] = mode
        sweep_once(service_id)
    incident = database.find_one("incidents", {"service_id": service_id, "status": {"$in": ["open", "acknowledged"]}})
    assert incident is not None and incident["current_state"] == "flaky", incident
    assert "failure rate" in incident["opened_reason"]
    ok("intermittent failures detected as flaky -> incident opened")

    fixture_state["mode"] = "healthy"
    for _ in range(2):
        sweep_once(service_id)
    incident = database.find_one("incidents", {"incident_id": incident["incident_id"]})
    assert incident["status"] == "resolved" and incident["current_state"] == "flaky"
    ok("flaky incident resolved on recovery")

    # --- second service, own schedule ----------------------------------------
    r = client.post(
        "/catalogue",
        json={**svc_payload, "name": "Second Service", "slug": "second-service"},
        headers=admin_headers,
    )
    second_id = r.json()["service_id"]
    sweep_once(second_id)
    second = database.find_one("services", {"service_id": second_id})
    assert second["monitoring"]["last_check_at"] is not None
    ok("second service checked independently on its own schedule")

    # JWT tamper
    r = client.get("/catalogue", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401
    ok("tampered token rejected")

    # OpenAPI sanity: routers registered
    paths = client.get("/openapi.json").json()["paths"]
    for expected in ("/auth/register", "/auth/login", "/auth/me", "/admin/users", "/catalogue", "/states"):
        assert any(p == expected or p.startswith(expected + "/") for p in paths), expected
    ok("OpenAPI exposes auth/catalogue/states")

print(f"\nALL TASK 2 SMOKE CHECKS PASSED ({passed} checks)")
server.shutdown()
