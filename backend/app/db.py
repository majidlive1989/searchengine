import json, os, sqlite3, uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from fastapi import HTTPException

DB_PATH = os.getenv("DATABASE_PATH", "data/copilot.db")


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return prefix + "_" + uuid.uuid4().hex[:16]


def dumps(v):
    return json.dumps(v, ensure_ascii=False, default=str, separators=(",", ":"))


@contextmanager
def connect():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()


def init():
    with connect() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
        INSERT OR IGNORE INTO schema_version VALUES(1);
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,tenant TEXT NOT NULL,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,role TEXT NOT NULL,password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS objects(id TEXT PRIMARY KEY,tenant TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL,created TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS objects_tenant_kind ON objects(tenant,kind);
        CREATE INDEX IF NOT EXISTS objects_request_id ON objects(tenant,kind,json_extract(body,'$.request_id'),created DESC);
        CREATE INDEX IF NOT EXISTS objects_run_id ON objects(tenant,kind,json_extract(body,'$.run_id'),created DESC);
        CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT,tenant TEXT NOT NULL,actor TEXT NOT NULL,entity TEXT NOT NULL,event TEXT NOT NULL,detail TEXT NOT NULL,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS idempotency(tenant TEXT NOT NULL,actor TEXT NOT NULL,path TEXT NOT NULL,key TEXT NOT NULL,hash TEXT NOT NULL,response TEXT NOT NULL,PRIMARY KEY(tenant,actor,path,key));
        """)


def save(c, tenant, kind, obj):
    c.execute(
        "INSERT INTO objects VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body WHERE objects.tenant=excluded.tenant AND objects.kind=excluded.kind",
        (obj["id"], tenant, kind, dumps(obj), obj.get("created_at", now())),
    )
    return obj


def get(c, tenant, kind, id):
    r = c.execute(
        "SELECT body FROM objects WHERE tenant=? AND kind=? AND id=?",
        (tenant, kind, id),
    ).fetchone()
    if not r:
        raise HTTPException(404, "Record not found")
    return json.loads(r[0])


def all(c, tenant, kind):
    return [
        json.loads(r[0])
        for r in c.execute(
            "SELECT body FROM objects WHERE tenant=? AND kind=? ORDER BY created DESC",
            (tenant, kind),
        )
    ]


def audit(c, u, entity, event, detail=None):
    c.execute(
        "INSERT INTO audit(tenant,actor,entity,event,detail,created) VALUES(?,?,?,?,?,?)",
        (u["tenant"], u["id"], entity, event, dumps(detail or {}), now()),
    )


def related(c, tenant, kind, field, value):
    """Select related objects in SQL, preserving tenant isolation and ordering."""
    if field not in {"request_id", "run_id"}:
        raise ValueError("Unsupported relationship field")
    return [
        json.loads(row[0])
        for row in c.execute(
            f"SELECT body FROM objects WHERE tenant=? AND kind=? "
            f"AND json_extract(body,'$.{field}')=? ORDER BY created DESC",
            (tenant, kind, value),
        )
    ]
