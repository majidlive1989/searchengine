import hashlib, hmac, os, secrets, time
from fastapi import Cookie, Depends, HTTPException
from . import db


def password_hash(password):
    salt = secrets.token_hex(16)
    return (
        salt
        + ":"
        + hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    )


def verify(password, stored):
    salt, expected = stored.split(":")
    return hmac.compare_digest(
        hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex(),
        expected,
    )


def current_user(atlas_session: str | None = Cookie(default=None)):
    if not atlas_session:
        raise HTTPException(401, "Please sign in")
    token = hashlib.sha256(atlas_session.encode()).hexdigest()
    with db.connect() as c:
        row = c.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?",
            (token, time.time()),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Session expired. Please sign in")
    u = dict(row)
    u.pop("password")
    return u


def admin(u=Depends(current_user)):
    if u["role"] != "ADMIN":
        raise HTTPException(403, "Administrator role required")
    return u


def own(u, request):
    if u["role"] == "AGENT" and request["owner_id"] != u["id"]:
        raise HTTPException(404, "Record not found")


def bootstrap():
    email = os.getenv("ADMIN_EMAIL", "admin@agency.local").lower()
    password = os.getenv("ADMIN_PASSWORD", "")
    with db.connect() as c:
        if c.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return
        if len(password) < 12:
            raise RuntimeError(
                "Set ADMIN_PASSWORD to at least 12 characters for first startup."
            )
        c.execute(
            "INSERT INTO users VALUES(?,?,?,?,?,?)",
            (
                db.uid("usr"),
                "agency",
                email,
                "Agency Admin",
                "ADMIN",
                password_hash(password),
            ),
        )
