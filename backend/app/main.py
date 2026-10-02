import asyncio, hashlib, json, os, secrets, time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Request,
    Response,
    UploadFile,
    File,
    Header,
)
from fastapi.responses import FileResponse, JSONResponse
from . import db
from .integrations import ai_config, NativeAPIExecution, IntegrationError
from .models import *
from .security import current_user, admin, own, bootstrap, password_hash, verify
from .providers import (
    RulesUnderstanding,
    GeminiUnderstanding,
    DemoExecution,
    HttpExecution,
    validate_result,
)

TASKS = set()
SOURCE_LOCKS = defaultdict(asyncio.Lock)
LOGIN_ATTEMPTS = defaultdict(deque)
TERMINAL = {"WON", "LOST", "CANCELLED"}


def begin_task(coro):
    task = asyncio.create_task(coro)
    TASKS.add(task)
    task.add_done_callback(TASKS.discard)


@asynccontextmanager
async def lifespan(app):
    db.init()
    bootstrap()
    # A pilot worker is deliberately single-process. Interrupted work is visible, never silently retried.
    with db.connect() as c:
        for row in c.execute(
            "SELECT * FROM objects WHERE kind IN ('run','request')"
        ).fetchall():
            obj = json.loads(row["body"])
            if obj.get("status") == "SEARCHING":
                obj["status"] = "FAILED" if row["kind"] == "run" else "READY_TO_SEARCH"
                if row["kind"] == "run":
                    for j in obj["jobs"]:
                        if j["status"] in ["QUEUED", "RUNNING"]:
                            j.update(status="FAILED", error_code="WORKER_RESTARTED")
                db.save(c, row["tenant"], row["kind"], obj)
    yield
    for task in list(TASKS):
        task.cancel()
    await asyncio.gather(*list(TASKS), return_exceptions=True)


app = FastAPI(title="Atlas Travel Agency Copilot", version="0.2.1", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request, call_next):
    if request.url.path.startswith("/api/") and request.method not in {
        "GET",
        "HEAD",
        "OPTIONS",
    }:
        if request.headers.get("X-Requested-With") != "Atlas":
            return JSONResponse({"detail": "Missing request protection header"}, 403)
        origin = request.headers.get("origin")
        allowed = os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin and origin not in allowed:
            return JSONResponse({"detail": "Origin not allowed"}, 403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# Idempotent mutations execute and store their response in the SAME write transaction.
def mutation(c, u, path, key, payload, operation):
    if not key or len(key) > 100:
        raise HTTPException(400, "Idempotency-Key header required (max 100 characters)")
    digest = hashlib.sha256(db.dumps(payload).encode()).hexdigest()
    c.execute("BEGIN IMMEDIATE")
    previous = c.execute(
        "SELECT hash,response FROM idempotency WHERE tenant=? AND actor=? AND path=? AND key=?",
        (u["tenant"], u["id"], path, key),
    ).fetchone()
    if previous:
        if previous[0] != digest:
            raise HTTPException(409, "Idempotency key reused with different payload")
        return json.loads(previous[1]), False
    result = operation()
    c.execute(
        "INSERT INTO idempotency VALUES(?,?,?,?,?,?)",
        (u["tenant"], u["id"], path, key, digest, db.dumps(result)),
    )
    return result, True


def request_get(c, u, id):
    req = db.get(c, u["tenant"], "request", id)
    own(u, req)
    return req


def detail(c, u, req):
    t = u["tenant"]
    id = req["id"]
    return {
        **req,
        "runs": db.related(c, t, "run", "request_id", id),
        "results": db.related(c, t, "result", "request_id", id),
        "offers": db.related(c, t, "offer", "request_id", id),
        "activity": [
            dict(r)
            for r in c.execute(
                "SELECT actor,event,detail,created FROM audit WHERE tenant=? AND entity=? ORDER BY seq DESC LIMIT 80",
                (t, id),
            )
        ],
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.2.1"}


@app.post("/api/auth/login")
def login(body: LoginIn, response: Response, request: Request):
    bucket = (request.client.host, body.email.lower())
    attempts = LOGIN_ATTEMPTS[bucket]
    n = time.time()
    while attempts and attempts[0] < n - 900:
        attempts.popleft()
    if len(attempts) >= 10:
        raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
    attempts.append(n)
    with db.connect() as c:
        row = c.execute(
            "SELECT * FROM users WHERE email=?", (body.email.lower(),)
        ).fetchone()
        if not row or not verify(body.password, row["password"]):
            raise HTTPException(401, "Invalid email or password")
        attempts.clear()
        token = secrets.token_urlsafe(32)
        c.execute("DELETE FROM sessions WHERE expires<?", (n,))
        c.execute(
            "INSERT INTO sessions VALUES(?,?,?)",
            (hashlib.sha256(token.encode()).hexdigest(), row["id"], n + 28800),
        )
        user = dict(row)
        user.pop("password")
        db.audit(c, user, user["id"], "SIGNED_IN")
    response.set_cookie(
        "atlas_session",
        token,
        httponly=True,
        samesite="strict",
        secure=os.getenv("COOKIE_SECURE", "false") == "true",
        max_age=28800,
        path="/",
    )
    return user


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, u=Depends(current_user)):
    with db.connect() as c:
        c.execute(
            "DELETE FROM sessions WHERE token=?",
            (hashlib.sha256(request.cookies["atlas_session"].encode()).hexdigest(),),
        )
    response.delete_cookie("atlas_session", path="/")
    return {"ok": True}


@app.get("/api/me")
def me(u=Depends(current_user)):
    return u


@app.get("/api/users")
def users(u=Depends(admin)):
    with db.connect() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT id,name,email,role FROM users WHERE tenant=?", (u["tenant"],)
            )
        ]


@app.post("/api/users")
def add_user(body: UserIn, u=Depends(admin)):
    if len(body.password) < 12:
        raise HTTPException(422, "Password needs at least 12 characters")
    with db.connect() as c:
        if c.execute(
            "SELECT 1 FROM users WHERE email=?", (body.email.lower(),)
        ).fetchone():
            raise HTTPException(409, "Email already exists")
        id = db.uid("usr")
        c.execute(
            "INSERT INTO users VALUES(?,?,?,?,?,?)",
            (
                id,
                u["tenant"],
                body.email.lower(),
                body.name,
                body.role,
                password_hash(body.password),
            ),
        )
        db.audit(c, u, id, "USER_CREATED", {"role": body.role})
    return {"id": id, "name": body.name, "role": body.role}


@app.get("/api/settings")
def settings(u=Depends(current_user)):
    cfg=ai_config(u['tenant'])
    return {'ai_provider':'GEMINI' if cfg['enabled'] and cfg['key'] and cfg['model'] else 'OFFLINE_RULES',
            'voice_enabled':bool(cfg['enabled'] and cfg['key'] and cfg['model']),
            'bridge_configured':bool(os.getenv('EXECUTION_BRIDGE_URL') and os.getenv('EXECUTION_BRIDGE_TOKEN')),
            'deployment':'Single-agency local installation','version':'0.2.1','native_api':True,'manual_sources':True}


@app.get("/api/requests")
def list_requests(u=Depends(current_user)):
    with db.connect() as c:
        return [
            r
            for r in db.all(c, u["tenant"], "request")
            if u["role"] != "AGENT" or r["owner_id"] == u["id"]
        ]


@app.post("/api/requests")
def create_request(
    body: RequestIn,
    u=Depends(current_user),
    idempotency_key: str | None = Header(default=None),
):
    with db.connect() as c:

        def op():
            r = {
                "id": db.uid("req"),
                "customer_name": body.customer_name,
                "owner_id": u["id"],
                "owner_name": u["name"],
                "status": "QUALIFYING",
                "spec": body.spec.model_dump(mode="json"),
                "revision": 1,
                "confirmed_revision": 0,
                "messages": (
                    [{"role": "user", "text": body.text, "created_at": db.now()}]
                    if body.text
                    else []
                ),
                "created_at": db.now(),
                "updated_at": db.now(),
                "active_run_id": None,
            }
            db.save(c, u["tenant"], "request", r)
            db.audit(c, u, r["id"], "REQUEST_CREATED")
            return r

        return mutation(
            c, u, "requests", idempotency_key, body.model_dump(mode="json"), op
        )[0]


@app.get("/api/requests/{id}")
def get_request(id: str, u=Depends(current_user)):
    with db.connect() as c:
        return detail(c, u, request_get(c, u, id))


@app.post("/api/requests/{id}/messages")
async def message(id: str, body: TextIn, u=Depends(current_user)):
    with db.connect() as c:
        req = request_get(c, u, id)
        if req["status"] in TERMINAL:
            raise HTTPException(409, "Closed request cannot be modified")
        revision = req["revision"]
    provider = (
        GeminiUnderstanding(u["tenant"])
        if settings(u)["ai_provider"]=="GEMINI"
        else RulesUnderstanding()
    )
    try:
        understood = await provider.understand(
            body.text, TravelSpec.model_validate(req["spec"])
        )
    except Exception:
        raise HTTPException(
            502,
            "Understanding provider failed. Use the structured form; no request fields were changed.",
        )
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        req = request_get(c, u, id)
        if req["revision"] != revision or req["status"] in TERMINAL:
            raise HTTPException(409, "Request changed. Reload before retrying.")
        req.update(
            spec=understood["spec"],
            revision=revision + 1,
            status="QUALIFYING",
            updated_at=db.now(),
            active_run_id=None,
        )
        req["messages"] += [
            {"role": "user", "text": body.text, "created_at": db.now()},
            {
                "role": "assistant",
                "text": " ".join(understood["notes"]),
                "created_at": db.now(),
            },
        ]
        db.save(c, u["tenant"], "request", req)
        db.audit(
            c,
            u,
            id,
            "INTENT_EXTRACTED",
            {"provider": understood["provider"], "revision": req["revision"]},
        )
    return {
        **understood,
        "request": req,
        "issues": TravelSpec.model_validate(req["spec"]).issues(),
    }


@app.post("/api/requests/{id}/voice")
async def voice(id: str, file: UploadFile = File(...), u=Depends(current_user)):
    with db.connect() as c:
        request_get(c, u, id)
    if file.content_type not in {
        "audio/webm",
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp4",
        "audio/ogg",
    }:
        raise HTTPException(415, "Use WAV, MP3, M4A, OGG or WebM audio")
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "Audio limit is 10 MB")
    if not settings(u)["voice_enabled"]:
        raise HTTPException(503, "Voice requires Gemini configuration")
    try:
        transcript = await GeminiUnderstanding(u["tenant"]).transcribe(data, file.content_type)
    except Exception:
        raise HTTPException(502, "Transcription failed; audio was not stored")
    with db.connect() as c:
        db.audit(c, u, id, "VOICE_TRANSCRIBED", {"retained_audio": False})
    return {
        "transcript": transcript[:6000],
        "requires_confirmation": True,
        "audio_retained": False,
    }


@app.post("/api/requests/{id}/confirm")
def confirm(id: str, body: ConfirmIn, u=Depends(current_user)):
    if body.spec.issues():
        raise HTTPException(422, "; ".join(body.spec.issues()))
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        req = request_get(c, u, id)
        if req["status"] in TERMINAL:
            raise HTTPException(409, "Request is closed")
        if req["revision"] != body.revision:
            raise HTTPException(409, "Request changed. Reload and confirm again.")
        req.update(
            spec=body.spec.model_dump(mode="json"),
            revision=req["revision"] + 1,
            confirmed_revision=req["revision"] + 1,
            status="READY_TO_SEARCH",
            active_run_id=None,
            updated_at=db.now(),
        )
        db.save(c, u["tenant"], "request", req)
        db.audit(c, u, id, "SPEC_CONFIRMED", {"revision": req["revision"]})
    return req


@app.post("/api/requests/{id}/transition")
def transition(id: str, body: TransitionIn, u=Depends(current_user)):
    allowed = {
        "QUALIFYING": {"CANCELLED", "ON_HOLD"},
        "READY_TO_SEARCH": {"CANCELLED", "ON_HOLD"},
        "RESULTS_READY": {"SALES_REVIEW", "ON_HOLD", "CANCELLED"},
        "SALES_REVIEW": {"ON_HOLD", "CANCELLED"},
        "OFFER_READY": {"WAITING_CUSTOMER", "WON", "LOST", "ON_HOLD", "CANCELLED"},
        "WAITING_CUSTOMER": {"WON", "LOST", "ON_HOLD", "CANCELLED"},
        "ON_HOLD": {"SALES_REVIEW", "CANCELLED"},
    }
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        req = request_get(c, u, id)
        old = req["status"]
        if body.state not in allowed.get(old, set()):
            raise HTTPException(409, f"Cannot move {old} to {body.state}")
        req.update(status=body.state, updated_at=db.now())
        db.save(c, u["tenant"], "request", req)
        db.audit(
            c,
            u,
            id,
            "STATE_CHANGED",
            {"from": old, "to": body.state, "reason": body.reason},
        )
    return req


@app.get("/api/sources")
def list_sources(u=Depends(current_user)):
    with db.connect() as c:
        sources=db.all(c, u["tenant"], "source")
        if u['role']!='ADMIN':
            for source in sources:
                source['versions']=[{k:v for k,v in version.items() if k!='api_config'} for version in source['versions']]
        return sources


@app.post("/api/sources")
def add_source(body: SourceIn, u=Depends(admin)):
    if body.provider == "DEMO" and os.getenv("ENABLE_DEMO", "true") != "true":
        raise HTTPException(403, "Demo sources disabled by operator")
    if body.provider == "HTTP_BRIDGE" and not body.account_ref:
        raise HTTPException(422, "Live sources need a bridge account reference")
    with db.connect() as c:
        s = {
            "id": db.uid("src"),
            **body.model_dump(),
            "status": "DRAFT",
            "version": 1,
            "active_version": None,
            "versions": [
                {
                    "version": 1,
                    "mapping_version": "initial",
                    "notes": "Initial configuration",
                    "created_at": db.now(),
                }
            ],
            "tests": [],
            "created_at": db.now(),
        }
        db.save(c, u["tenant"], "source", s)
        db.audit(c, u, s["id"], "SOURCE_CREATED", {"provider": s["provider"]})
        return s


@app.post("/api/demo/setup")
def demo_setup(u=Depends(admin)):
    if os.getenv("ENABLE_DEMO", "true") != "true":
        raise HTTPException(403, "Demo sources disabled by operator")
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        if any(s["provider"] == "DEMO" for s in db.all(c, u["tenant"], "source")):
            return {"ok": True}
        for kind in ["FLIGHT", "HOTEL"]:
            for i in range(2):
                s = {
                    "id": db.uid("src"),
                    "name": f"{'Skyline' if kind == 'FLIGHT' else 'Stayline'} {chr(65 + i)} · Demo",
                    "kind": kind,
                    "provider": "DEMO",
                    "account_ref": "demo",
                    "classification": "AGENCY_TAUGHT",
                    "notes": "Synthetic fixtures. No live supplier connection.",
                    "status": "ACTIVE",
                    "version": 1,
                    "active_version": 1,
                    "versions": [
                        {
                            "version": 1,
                            "mapping_version": "demo-v1",
                            "notes": "Built-in demo fixture",
                            "created_at": db.now(),
                        }
                    ],
                    "tests": [],
                    "created_at": db.now(),
                    "variant": i,
                }
                db.save(c, u["tenant"], "source", s)
        db.audit(c, u, "sources", "DEMO_SOURCES_INSTALLED")
    return {"ok": True}


@app.post("/api/sources/{id}/versions")
def source_version(id: str, body: WorkflowIn, u=Depends(admin)):
    with db.connect() as c:
        current=db.get(c,u["tenant"],"source",id)
        if current["provider"] in {"JSON_API","MANUAL"}:raise HTTPException(409,"Use this source configuration editor to publish a version")
        c.execute("BEGIN IMMEDIATE")
        s = db.get(c, u["tenant"], "source", id)
        s["version"] += 1
        s["versions"].append(
            {"version": s["version"], **body.model_dump(), "created_at": db.now()}
        )
        s["status"] = "DRAFT"
        s["active_version"] = None
        db.save(c, u["tenant"], "source", s)
        db.audit(c, u, id, "WORKFLOW_VERSION_CREATED", {"version": s["version"]})
        return s


def make_job(source, spec, tenant, run_id, revision):
    version = source["active_version"] or source["version"]
    v = next(v for v in source["versions"] if v["version"] == version)
    return {
        "job_id": db.uid("job"),
        "tenant_id": tenant,
        "source_id": source["id"],
        "search_run_id": run_id,
        "request_revision": revision,
        "workflow_id": source["id"] + "." + source["kind"].lower() + "_search",
        "workflow_version": version,
        "mapping_version": v["mapping_version"],
        "browser_profile_ref": source["account_ref"],
        "kind": source["kind"],
        "provider": source["provider"],
        "input": spec,
        "deadline_at": (datetime.now(timezone.utc) + timedelta(seconds=35)).isoformat(),
        "variant": source.get("variant", 0),
    }


async def execute(job):
    async with SOURCE_LOCKS[(job["tenant_id"], job["source_id"])]:
        if job['provider']=='MANUAL':raise IntegrationError('MANUAL_ENTRY_REQUIRED')
        provider = DemoExecution() if job["provider"] == "DEMO" else NativeAPIExecution() if job['provider']=='JSON_API' else HttpExecution()
        return validate_result(
            await asyncio.wait_for(provider.execute(job), timeout=32), job
        )


@app.post("/api/sources/{id}/test")
async def source_test(id: str, body: TestIn, u=Depends(admin)):
    if body.spec.issues():
        raise HTTPException(422, "; ".join(body.spec.issues()))
    with db.connect() as c:
        s = db.get(c, u["tenant"], "source", id)
    job = make_job(s, body.spec.model_dump(mode="json"), u["tenant"], "golden-test", 0)
    start = time.monotonic()
    try:
        result = await execute(job)
        success = result.status == "SUCCESS" and bool(result.records)
        code = result.error_code
    except IntegrationError as e:
        success=False;code=e.code
    except Exception:
        success = False
        code = "EXECUTION_OR_SCHEMA_FAILED"
    test = {
        "id": db.uid("test"),
        "version": s["version"],
        "spec": body.spec.model_dump(mode="json"),
        "success": success,
        "error_code": code,
        "duration_ms": int((time.monotonic() - start) * 1000),
        "created_at": db.now(),
    }
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        s = db.get(c, u["tenant"], "source", id)
        s["tests"].append(test)
        s["tests"] = s["tests"][-100:]
        db.save(c, u["tenant"], "source", s)
        db.audit(c, u, id, "SOURCE_TESTED", test)
    return test


@app.post("/api/sources/{id}/activate")
def source_activate(id: str, u=Depends(admin)):
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        s = db.get(c, u["tenant"], "source", id)
        good = {
            db.dumps(t["spec"])
            for t in s["tests"]
            if t["version"] == s["version"] and t["success"]
        }
        latest = [t for t in s["tests"] if t["version"] == s["version"]]
        if len(good) < 3 or not latest or not latest[-1]["success"]:
            raise HTTPException(
                409,
                "Pass three distinct golden searches on this version, with the latest test passing, before activation",
            )
        s.update(status="ACTIVE", active_version=s["version"])
        db.save(c, u["tenant"], "source", s)
        db.audit(c, u, id, "SOURCE_ACTIVATED", {"version": s["version"]})
        return s


@app.post("/api/sources/{id}/disable")
def source_disable(id: str, u=Depends(admin)):
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        s = db.get(c, u["tenant"], "source", id)
        s["status"] = "DISABLED"
        db.save(c, u["tenant"], "source", s)
        db.audit(c, u, id, "SOURCE_DISABLED")
        return s


@app.post("/api/requests/{id}/search-runs")
async def start_search(
    id: str,
    body: SearchIn,
    u=Depends(current_user),
    idempotency_key: str | None = Header(default=None),
):
    with db.connect() as c:

        def op():
            req = request_get(c, u, id)
            spec = TravelSpec.model_validate(req["spec"])
            if (
                req["status"] in TERMINAL
                or req["confirmed_revision"] != req["revision"]
                or spec.issues()
            ):
                raise HTTPException(409, "Review and confirm valid travel fields first")
            if req["status"] == "SEARCHING":
                raise HTTPException(409, "A search is already running")
            sources = [
                db.get(c, u["tenant"], "source", sid)
                for sid in dict.fromkeys(body.source_ids)
            ]
            kinds = (
                {"FLIGHT"}
                if spec.intent == "FLIGHT_SEARCH"
                else {"HOTEL"}
                if spec.intent == "HOTEL_SEARCH"
                else {"FLIGHT", "HOTEL"}
            )
            if any(s["status"] != "ACTIVE" or s["kind"] not in kinds or s["provider"]=="MANUAL" for s in sources):
                raise HTTPException(409, "Select active sources matching the request")
            if {s["kind"] for s in sources} != kinds:
                raise HTTPException(409, "Choose a source for every requested service")
            if os.getenv("ENABLE_DEMO", "true") != "true" and any(
                s["provider"] == "DEMO" for s in sources
            ):
                raise HTTPException(403, "Demo sources disabled by operator")
            if len({s["provider"] == "DEMO" for s in sources}) > 1:
                raise HTTPException(409, "Demo and live sources cannot be mixed")
            run = {
                "id": db.uid("run"),
                "request_id": id,
                "revision": req["revision"],
                "spec": req["spec"],
                "status": "SEARCHING",
                "created_at": db.now(),
                "jobs": [],
            }
            for s in sources:
                job = make_job(s, req["spec"], u["tenant"], run["id"], req["revision"])
                job.update(status="QUEUED", source_name=s["name"])
                run["jobs"].append(job)
            req.update(status="SEARCHING", active_run_id=run["id"], updated_at=db.now())
            db.save(c, u["tenant"], "request", req)
            db.save(c, u["tenant"], "run", run)
            db.audit(
                c,
                u,
                id,
                "SEARCH_STARTED",
                {"run_id": run["id"], "sources": len(sources)},
            )
            return run

        run, created = mutation(
            c, u, "search/" + id, idempotency_key, body.model_dump(), op
        )
    if created:
        begin_task(orchestrate(u, run["id"]))
    return run


async def orchestrate(u, run_id):
    t = u["tenant"]
    with db.connect() as c:
        run = db.get(c, t, "run", run_id)

    async def worker(job):
        start = time.monotonic()
        with db.connect() as c:
            r = db.get(c, t, "run", run_id)
            next(j for j in r["jobs"] if j["job_id"] == job["job_id"])["status"] = (
                "RUNNING"
            )
            db.save(c, t, "run", r)
        try:
            with db.connect() as c:
                source = db.get(c, t, "source", job["source_id"])
            if source["status"] != "ACTIVE":
                raise RuntimeError("SOURCE_DISABLED")
            result = await execute(job)
            status = result.status
            code = result.error_code
        except asyncio.TimeoutError:
            result = None
            status = "FAILED"
            code = "TIMEOUT"
        except Exception:
            result = None
            status = "FAILED"
            code = "EXECUTION_OR_SCHEMA_FAILED"
        with db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            r = db.get(c, t, "run", run_id)
            req = db.get(c, t, "request", r["request_id"])
            source = db.get(c, t, "source", job["source_id"])
            if req["active_run_id"] != run_id or req["revision"] != r["revision"]:
                status = "CANCELLED"
                code = "STALE_JOB"
                result = None
            elif source["status"] != "ACTIVE":
                status = "FAILED"
                code = "SOURCE_DISABLED"
                result = None
            target = next(j for j in r["jobs"] if j["job_id"] == job["job_id"])
            target.update(
                status=status,
                error_code=code,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            if result and status == "SUCCESS":
                seen = set()
                for rate in result.records:
                    if rate.external_id in seen:
                        continue
                    seen.add(rate.external_id)
                    obj = {
                        "id": db.uid("rate"),
                        **rate.model_dump(mode="json"),
                        "source_id": job["source_id"],
                        "source_name": job["source_name"],
                        "run_id": run_id,
                        "request_id": r["request_id"],
                        "workflow_version": job["workflow_version"],
                        "created_at": db.now(),
                    }
                    db.save(c, t, "result", obj)
            if status == "RECONNECT_REQUIRED":
                source["status"] = "RECONNECT_REQUIRED"
                db.save(c, t, "source", source)
            db.save(c, t, "run", r)
            db.audit(
                c,
                u,
                r["request_id"],
                "SOURCE_FINISHED",
                {
                    "run_id": run_id,
                    "source_id": job["source_id"],
                    "status": status,
                    "error_code": code,
                },
            )

    await asyncio.gather(*(worker(j) for j in run["jobs"]))
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        r = db.get(c, t, "run", run_id)
        req = db.get(c, t, "request", r["request_id"])
        statuses = [j["status"] for j in r["jobs"]]
        r["status"] = (
            "SUCCESS"
            if all(s == "SUCCESS" for s in statuses)
            else "PARTIAL"
            if "SUCCESS" in statuses
            else "FAILED"
        )
        r["completed_at"] = db.now()
        db.save(c, t, "run", r)
        if req["active_run_id"] == run_id:
            req["status"] = (
                "RESULTS_READY" if "SUCCESS" in statuses else "READY_TO_SEARCH"
            )
            db.save(c, t, "request", req)
        db.audit(
            c,
            u,
            req["id"],
            "SEARCH_FINISHED",
            {"run_id": run_id, "status": r["status"]},
        )


@app.get("/api/search-runs/{id}/results")
def results(id: str, u=Depends(current_user)):
    with db.connect() as c:
        run = db.get(c, u["tenant"], "run", id)
        request_get(c, u, run["request_id"])
        return {
            "run": run,
            "results": db.related(c, u["tenant"], "result", "run_id", id),
        }


def check_offer_rates(c, u, req, rates):
    n = datetime.now(timezone.utc)
    if req["status"] in TERMINAL or req["confirmed_revision"] != req["revision"]:
        raise HTTPException(409, "Request must be open and confirmed")
    if any(
        db.get(c, u["tenant"], "source", r["source_id"])["status"] != "ACTIVE"
        for r in rates
    ):
        raise HTTPException(
            409, "A selected source is no longer active. Revalidate after reconnecting."
        )
    if len({r["id"] for r in rates}) != len(rates):
        raise HTTPException(422, "Duplicate selections")
    if any(
        r["request_id"] != req["id"] or r["run_id"] != req["active_run_id"]
        for r in rates
    ):
        raise HTTPException(409, "Use rates from the current search only")
    if any(datetime.fromisoformat(r["expires_at"]) <= n for r in rates):
        raise HTTPException(
            409, "Rates expired. Search again before creating or approving an offer."
        )
    if len({r["currency"] for r in rates}) != 1:
        raise HTTPException(
            422, "Currencies cannot be combined without an explicit FX policy"
        )
    if len({r["demo"] for r in rates}) != 1:
        raise HTTPException(422, "Demo/live mixing is prohibited")
    expected = (
        {"FLIGHT"}
        if req["spec"]["intent"] == "FLIGHT_SEARCH"
        else {"HOTEL"}
        if req["spec"]["intent"] == "HOTEL_SEARCH"
        else {"FLIGHT", "HOTEL"}
    )
    if {r["kind"] for r in rates} != expected or len(rates) != len(expected):
        raise HTTPException(422, "Select exactly one rate for each requested service")


@app.post("/api/offers")
def offer(
    body: OfferIn,
    u=Depends(current_user),
    idempotency_key: str | None = Header(default=None),
):
    with db.connect() as c:

        def op():
            req = request_get(c, u, body.request_id)
            rates = [db.get(c, u["tenant"], "result", id) for id in body.result_ids]
            check_offer_rates(c, u, req, rates)
            if body.markup_type == "PERCENT" and body.markup > 100:
                raise HTTPException(422, "Percentage markup cannot exceed 100%")
            currency = rates[0]["currency"]
            quantum = (
                Decimal("0.001")
                if currency == "OMR"
                else Decimal("1")
                if currency == "IRR"
                else Decimal("0.01")
            )
            net = sum(Decimal(r["net_price"]) for r in rates).quantize(
                quantum, rounding=ROUND_HALF_UP
            )
            margin = (
                net * body.markup / 100
                if body.markup_type == "PERCENT"
                else body.markup
            ).quantize(quantum, rounding=ROUND_HALF_UP)
            obj = {
                "id": db.uid("off"),
                "request_id": req["id"],
                "customer_name": req["customer_name"],
                "items": rates,
                "net_total": str(net),
                "markup_amount": str(margin),
                "total": str(net + margin),
                "currency": currency,
                "demo": rates[0]["demo"],
                "status": "DRAFT",
                "created_at": db.now(),
                "note": body.note,
                "created_by": u["id"],
                "revision": req["revision"],
            }
            db.save(c, u["tenant"], "offer", obj)
            req["status"] = "SALES_REVIEW"
            db.save(c, u["tenant"], "request", req)
            db.audit(c, u, req["id"], "OFFER_DRAFTED", {"offer_id": obj["id"]})
            return obj

        return mutation(
            c, u, "offers", idempotency_key, body.model_dump(mode="json"), op
        )[0]


@app.post("/api/offers/{id}/approve")
def approve_offer(id: str, u=Depends(current_user)):
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        off = db.get(c, u["tenant"], "offer", id)
        req = request_get(c, u, off["request_id"])
        if off["status"] == "APPROVED":
            return off
        check_offer_rates(c, u, req, off["items"])
        off.update(status="APPROVED", approved_by=u["id"], approved_at=db.now())
        db.save(c, u["tenant"], "offer", off)
        req["status"] = "OFFER_READY"
        db.save(c, u["tenant"], "request", req)
        db.audit(
            c, u, req["id"], "OFFER_APPROVED", {"offer_id": id, "demo": off["demo"]}
        )
        return off


@app.get("/api/metrics")
def metrics(u=Depends(current_user)):
    with db.connect() as c:
        reqs = [
            r
            for r in db.all(c, u["tenant"], "request")
            if u["role"] != "AGENT" or r["owner_id"] == u["id"]
        ]
        ids = {r["id"] for r in reqs}
        runs = [r for r in db.all(c, u["tenant"], "run") if r["request_id"] in ids]
        offers = [o for o in db.all(c, u["tenant"], "offer") if o["request_id"] in ids]
    done = [r for r in runs if r["status"] != "SEARCHING"]
    durations = [
        (
            datetime.fromisoformat(r["completed_at"])
            - datetime.fromisoformat(r["created_at"])
        ).total_seconds()
        for r in done
        if "completed_at" in r
    ]
    return {
        "requests": len(reqs),
        "open": sum(r["status"] not in TERMINAL for r in reqs),
        "offers": len(offers),
        "approved_offers": sum(o["status"] == "APPROVED" for o in offers),
        "searches": len(runs),
        "search_success_pct": round(
            100 * sum(r["status"] in {"SUCCESS", "PARTIAL"} for r in done) / len(done)
        )
        if done
        else None,
        "mean_search_seconds": round(sum(durations) / len(durations), 1)
        if durations
        else None,
        "won": sum(r["status"] == "WON" for r in reqs),
        "demo_runs": sum(any(j["provider"] == "DEMO" for j in r["jobs"]) for r in runs),
    }


@app.get("/api/diagnostics")
def diagnostics(u=Depends(admin)):
    with db.connect() as c:
        sources = db.all(c, u["tenant"], "source")
        runs = db.all(c, u["tenant"], "run")
        return {
            "version": "0.2.1",
            "created_at": db.now(),
            "sources": [
                {
                    "id": s["id"],
                    "status": s["status"],
                    "version": s["version"],
                    "provider": s["provider"],
                }
                for s in sources
            ],
            "job_errors": [
                {"code": j.get("error_code"), "workflow_version": j["workflow_version"]}
                for r in runs
                for j in r["jobs"]
                if j.get("error_code")
            ],
            "redaction": "No passenger data, request text, rates, transcripts, account references, secrets, or source URLs included.",
        }


from fastapi.exceptions import RequestValidationError

@app.exception_handler(IntegrationError)
async def integration_error(request,exc):
    return JSONResponse({'detail':exc.code},422)

@app.exception_handler(RequestValidationError)
async def redacted_validation(request,exc):
    return JSONResponse({'detail':'; '.join('.'.join(str(v) for v in e['loc'])+': '+e['msg'] for e in exc.errors())},422)

from .config_routes import router as config_router
app.include_router(config_router)

WEB = Path(
    os.getenv(
        "FRONTEND_DIST", str(Path(__file__).resolve().parents[2] / "frontend" / "dist")
    )
).resolve()


@app.get("/{path:path}", include_in_schema=False)
def web(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "API endpoint not found")
    file = (WEB / path).resolve()
    if not file.is_relative_to(WEB):
        raise HTTPException(404)
    if file.is_file():
        return FileResponse(file)
    index = WEB / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse(
        {"detail": "Frontend not built. Run npm ci && npm run build inside frontend."},
        503,
    )
