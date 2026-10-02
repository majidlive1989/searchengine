import asyncio, json, time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from app import db, main
from app.models import Rate, TravelSpec
from app.providers import DemoExecution, validate_result, RulesUnderstanding
from app.security import password_hash

H = {"X-Requested-With": "Atlas"}


def spec(**kw):
    s = dict(
        intent="PACKAGE_SEARCH",
        origin="IKA",
        destination="MCT",
        departure_date=(datetime.now(timezone.utc) + timedelta(days=14))
        .date()
        .isoformat(),
        return_date=(datetime.now(timezone.utc) + timedelta(days=18))
        .date()
        .isoformat(),
        adults=2,
        children=0,
        rooms=1,
        stars_min=4,
        direct_only=True,
        cabin="ECONOMY",
    )
    s.update(kw)
    return s


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ADMIN_PASSWORD", "test-password-12345")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@agency.local")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    main.LOGIN_ATTEMPTS.clear()
    main.SOURCE_LOCKS.clear()
    with TestClient(main.app) as c:
        c.headers.update(H)
        assert (
            c.post(
                "/api/auth/login",
                json={"email": "admin@agency.local", "password": "test-password-12345"},
            ).status_code
            == 200
        )
        yield c


def post(c, path, data=None, key=None):
    return c.post(
        "/api" + path,
        json=data or {},
        headers={"Idempotency-Key": key or db.uid("key")},
    )


def create(c):
    r = post(c, "/requests", {"customer_name": "Test customer", "spec": spec()})
    assert r.status_code == 200, r.text
    return r.json()


def prepare(c):
    req = create(c)
    r = post(c, "/requests/" + req["id"] + "/confirm", {"spec": spec(), "revision": 1})
    assert r.status_code == 200, r.text
    post(c, "/demo/setup")
    sources = c.get("/api/sources").json()
    return req, sources


def search(c):
    req, sources = prepare(c)
    r = post(
        c,
        "/requests/" + req["id"] + "/search-runs",
        {"source_ids": [s["id"] for s in sources]},
    )
    assert r.status_code == 200, r.text
    for _ in range(100):
        d = c.get("/api/requests/" + req["id"]).json()
        if d["status"] != "SEARCHING":
            return d
        time.sleep(0.02)
    pytest.fail("Search did not complete")


def draft(c, req, key=None):
    rates = [
        next(r for r in req["results"] if r["kind"] == k) for k in ["FLIGHT", "HOTEL"]
    ]
    return post(
        c,
        "/offers",
        {
            "request_id": req["id"],
            "result_ids": [r["id"] for r in rates],
            "markup_type": "PERCENT",
            "markup": "12.5",
        },
        key,
    )


def test_request_to_approved_offer(client):
    req = search(client)
    assert req["status"] == "RESULTS_READY"
    assert len(req["results"]) == 12
    r = draft(client, req)
    assert r.status_code == 200, r.text
    off = r.json()
    assert Decimal(off["total"]) == Decimal(off["net_total"]) + Decimal(
        off["markup_amount"]
    )
    assert off["demo"] is True
    assert (
        post(client, "/offers/" + off["id"] + "/approve").json()["status"] == "APPROVED"
    )
    req = client.get("/api/requests/" + req["id"]).json()
    assert req["status"] == "OFFER_READY"
    assert any(a["event"] == "OFFER_APPROVED" for a in req["activity"])


def test_confirmation_required(client):
    req = create(client)
    post(client, "/demo/setup")
    ss = client.get("/api/sources").json()
    assert (
        post(
            client,
            "/requests/" + req["id"] + "/search-runs",
            {"source_ids": [s["id"] for s in ss]},
        ).status_code
        == 409
    )


def test_same_key_no_duplicate_and_conflict(client):
    data = {"customer_name": "A", "spec": spec()}
    a = post(client, "/requests", data, "fixed")
    b = post(client, "/requests", data, "fixed")
    assert a.json()["id"] == b.json()["id"]
    assert len(client.get("/api/requests").json()) == 1
    assert (
        post(client, "/requests", {**data, "customer_name": "B"}, "fixed").status_code
        == 409
    )
    assert client.post("/api/requests", json=data).status_code == 400


def test_expired_rates_block_draft_and_approval(client):
    req = search(client)
    off = draft(client, req).json()
    with db.connect() as c:
        for r in db.all(c, "agency", "result"):
            r["expires_at"] = (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ).isoformat()
            db.save(c, "agency", "result", r)
        o = db.get(c, "agency", "offer", off["id"])
        for r in o["items"]:
            r["expires_at"] = (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ).isoformat()
        db.save(c, "agency", "offer", o)
    assert draft(client, req).status_code == 409
    assert post(client, "/offers/" + off["id"] + "/approve").status_code == 409


def test_previous_search_results_cannot_be_quoted(client):
    req = search(client)
    assert (
        post(
            client,
            "/requests/" + req["id"] + "/confirm",
            {"revision": req["revision"], "spec": spec(adults=3)},
        ).status_code
        == 200
    )
    assert draft(client, req).status_code == 409


def test_ambiguous_input_always_requires_confirmation(client):
    req = create(client)
    r = post(
        client,
        "/requests/" + req["id"] + "/messages",
        {"text": "دو نفر تهران مسقط ۱۲ مهر، مستقیم"},
    )
    assert r.status_code == 200
    assert r.json()["requires_confirmation"]
    assert r.json()["request"]["status"] == "QUALIFYING"
    assert "Offline parser" in r.json()["notes"][0]


def test_persian_digits_and_iso_dates():
    out = asyncio.run(
        RulesUnderstanding().understand(
            "۳ نفر تهران مسقط ۲۰۲۷-۱۰-۱۲ تا ۲۰۲۷-۱۰-۱۶ مستقیم هتل ۴ ستاره", TravelSpec()
        )
    )
    assert out["spec"]["adults"] == 3
    assert out["spec"]["origin"] == "IKA"
    assert out["spec"]["destination"] == "MCT"
    assert out["spec"]["departure_date"] == "2027-10-12"


def test_rbac_and_ownership(client):
    req = create(client)
    assert (
        post(
            client,
            "/users",
            {
                "name": "Agent",
                "email": "agent@agency.local",
                "password": "agent-password-123",
                "role": "AGENT",
            },
        ).status_code
        == 200
    )
    post(client, "/auth/logout")
    post(
        client,
        "/auth/login",
        {"email": "agent@agency.local", "password": "agent-password-123"},
    )
    assert client.get("/api/requests/" + req["id"]).status_code == 404
    assert client.get("/api/requests").json() == []
    assert post(client, "/demo/setup").status_code == 403
    assert client.get("/api/diagnostics").status_code == 403
    assert (
        post(
            client,
            "/users",
            {
                "name": "Bad",
                "email": "bad@x.test",
                "password": "password-123456",
                "role": "ADMIN",
            },
        ).status_code
        == 403
    )


def test_tenant_isolation(client):
    req = create(client)
    with db.connect() as c:
        c.execute(
            "INSERT INTO users VALUES(?,?,?,?,?,?)",
            (
                "other",
                "other-agency",
                "other@agency.local",
                "Other",
                "ADMIN",
                password_hash("other-password-123"),
            ),
        )
    post(client, "/auth/logout")
    post(
        client,
        "/auth/login",
        {"email": "other@agency.local", "password": "other-password-123"},
    )
    assert client.get("/api/requests/" + req["id"]).status_code == 404
    assert client.get("/api/requests").json() == []


def test_csrf_and_auth(client):
    assert (
        client.post(
            "/api/demo/setup", headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    post(client, "/auth/logout")
    assert client.get("/api/requests").status_code == 401
    with TestClient(main.app) as anonymous:
        assert (
            anonymous.post(
                "/api/auth/login", json={"email": "x", "password": "y"}
            ).status_code
            == 403
        )


def test_invalid_dates_and_children(client):
    req = create(client)
    for invalid in [
        spec(departure_date="2000-01-01"),
        spec(return_date="2000-01-01"),
        spec(origin="XXX"),
        spec(children=1),
        spec(origin="MCT"),
    ]:
        assert (
            post(
                client,
                "/requests/" + req["id"] + "/confirm",
                {"revision": 1, "spec": invalid},
            ).status_code
            == 422
        )


def test_partial_source_failure(client, monkeypatch):
    original = main.execute

    async def fail_one(job):
        if job["variant"] == 1:
            raise RuntimeError("INJECTED")
        return await original(job)

    monkeypatch.setattr(main, "execute", fail_one)
    req = search(client)
    assert req["status"] == "RESULTS_READY"
    assert req["runs"][0]["status"] == "PARTIAL"
    assert len(req["results"]) == 6


def test_malformed_source_fails_closed(client, monkeypatch):
    async def bad(self, job):
        out = await original(self, job)
        out.records[0].destination = "DXB"
        return out

    original = DemoExecution.execute
    monkeypatch.setattr(DemoExecution, "execute", bad)
    req = search(client)
    assert req["status"] == "READY_TO_SEARCH"
    assert not req["results"]
    assert req["runs"][0]["status"] == "FAILED"


def test_superseded_jobs_do_not_publish(client, monkeypatch):
    original = main.execute

    async def slow(job):
        await asyncio.sleep(0.25)
        return await original(job)

    monkeypatch.setattr(main, "execute", slow)
    req, sources = prepare(client)
    post(
        client,
        "/requests/" + req["id"] + "/search-runs",
        {"source_ids": [s["id"] for s in sources]},
    )
    post(client, "/requests/" + req["id"] + "/messages", {"text": "3 adults"})
    time.sleep(0.65)
    r = client.get("/api/requests/" + req["id"]).json()
    assert r["status"] == "QUALIFYING"
    assert r["results"] == []
    assert all(j["error_code"] == "STALE_JOB" for j in r["runs"][0]["jobs"])


def test_source_activation_gate_and_versions(client):
    source = post(
        client,
        "/sources",
        {"name": "Test fixture", "kind": "FLIGHT", "provider": "DEMO"},
    ).json()
    id = source["id"]
    assert post(client, "/sources/" + id + "/activate").status_code == 409
    for n in [1, 2, 3]:
        assert post(
            client,
            "/sources/" + id + "/test",
            {"spec": spec(intent="FLIGHT_SEARCH", adults=n)},
        ).json()["success"]
    assert post(client, "/sources/" + id + "/activate").json()["status"] == "ACTIVE"
    new = post(
        client,
        "/sources/" + id + "/versions",
        {"mapping_version": "v2", "notes": "test"},
    ).json()
    assert new["version"] == 2 and new["versions"][0]["mapping_version"] == "initial"
    assert post(client, "/sources/" + id + "/activate").status_code == 409


def test_distinct_test_gate(client):
    s = post(
        client,
        "/sources",
        {"name": "Test fixture", "kind": "HOTEL", "provider": "DEMO"},
    ).json()
    for _ in range(3):
        post(
            client,
            "/sources/" + s["id"] + "/test",
            {"spec": spec(intent="HOTEL_SEARCH")},
        )
    assert post(client, "/sources/" + s["id"] + "/activate").status_code == 409


def test_unsupported_booking_and_transitions(client):
    req = create(client)
    assert (
        post(
            client,
            "/requests/" + req["id"] + "/transition",
            {"state": "WON", "reason": "invalid early win"},
        ).status_code
        == 409
    )
    assert post(client, "/bookings", {}).status_code in [404, 405]


def test_duplicate_result_selection_and_currency(client):
    req = search(client)
    r = req["results"][0]
    assert (
        post(
            client,
            "/offers",
            {"request_id": req["id"], "result_ids": [r["id"], r["id"]], "markup": "0"},
        ).status_code
        == 422
    )
    with db.connect() as c:
        for rate in db.all(c, "agency", "result"):
            if rate["kind"] == "HOTEL":
                rate["currency"] = "EUR"
                db.save(c, "agency", "result", rate)
    assert draft(client, req).status_code == 422


def test_persistence_and_sanitized_diagnostics(client):
    req = search(client)
    db.init()
    assert (
        client.get("/api/requests/" + req["id"]).json()["customer_name"]
        == "Test customer"
    )
    d = client.get("/api/diagnostics").text
    assert "Test customer" not in d
    assert "net_price" not in d
    assert "test-password" not in d


def test_voice_unconfigured_does_not_claim_transcription(client):
    req = create(client)
    r = client.post(
        "/api/requests/" + req["id"] + "/voice",
        files={"file": ("test.wav", b"RIFFtest", "audio/wav")},
    )
    assert r.status_code == 503


def test_offer_idempotency(client):
    req = search(client)
    a = draft(client, req, "quote-fixed")
    b = draft(client, req, "quote-fixed")
    assert a.json()["id"] == b.json()["id"]


def test_restart_recovers_interrupted_run(client):
    req, sources = prepare(client)
    with db.connect() as c:
        r = db.get(c, "agency", "request", req["id"])
        r["status"] = "SEARCHING"
        r["active_run_id"] = "run_restart"
        db.save(c, "agency", "request", r)
        db.save(
            c,
            "agency",
            "run",
            {
                "id": "run_restart",
                "request_id": req["id"],
                "status": "SEARCHING",
                "jobs": [{"status": "RUNNING"}, {"status": "SUCCESS"}],
            },
        )
    with TestClient(main.app):
        pass
    with db.connect() as c:
        assert db.get(c, "agency", "request", req["id"])["status"] == "READY_TO_SEARCH"
        run = db.get(c, "agency", "run", "run_restart")
        assert run["status"] == "FAILED"
        assert run["jobs"][0]["error_code"] == "WORKER_RESTARTED"
        assert run["jobs"][1]["status"] == "SUCCESS"


def test_disabled_source_blocks_quote(client):
    req = search(client)
    r = next(r for r in req["results"] if r["kind"] == "FLIGHT")
    post(client, "/sources/" + r["source_id"] + "/disable")
    assert draft(client, req).status_code == 409


def test_demo_operator_disable(client, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO", "false")
    assert post(client, "/demo/setup").status_code == 403
    assert (
        post(
            client,
            "/sources",
            {"name": "demo bypass", "kind": "FLIGHT", "provider": "DEMO"},
        ).status_code
        == 403
    )


def test_backup_restore(client, tmp_path):
    import subprocess, sys
    from pathlib import Path

    req = search(client)
    root = Path(__file__).resolve().parents[2]
    backup = tmp_path / "backup.db"
    restored = tmp_path / "restored.db"
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts/backup.py"),
            "--database",
            db.DB_PATH,
            "--output",
            str(backup),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts/restore.py"),
            "--backup",
            str(backup),
            "--output",
            str(restored),
        ],
        check=True,
        capture_output=True,
    )
    import sqlite3

    with sqlite3.connect(restored) as c:
        assert c.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
        assert (
            c.execute(
                "SELECT count(*) FROM objects WHERE id=?", (req["id"],)
            ).fetchone()[0]
            == 1
        )
    retry = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/restore.py"),
            "--backup",
            str(backup),
            "--output",
            str(restored),
        ],
        capture_output=True,
    )
    assert retry.returncode != 0


def test_bridge_unconfigured_fail_closed(client, monkeypatch):
    monkeypatch.delenv("EXECUTION_BRIDGE_URL", raising=False)
    monkeypatch.delenv("EXECUTION_BRIDGE_TOKEN", raising=False)
    s = post(
        client,
        "/sources",
        {
            "name": "Real source awaiting bridge",
            "kind": "FLIGHT",
            "provider": "HTTP_BRIDGE",
            "account_ref": "profile-x",
        },
    ).json()
    result = post(
        client, "/sources/" + s["id"] + "/test", {"spec": spec(intent="FLIGHT_SEARCH")}
    )
    assert result.status_code == 200 and not result.json()["success"]
    assert post(client, "/sources/" + s["id"] + "/activate").status_code == 409
