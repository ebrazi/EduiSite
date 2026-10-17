"""Security helpers: hashing, HMAC signing, CSRF, server-side sessions.

Cookies carry only an opaque session id; all state lives in the sessions
table. Cookies are HttpOnly, SameSite=Lax and Secure in production.
"""
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app, g, request

from . import db


# ---------- password hashing (scrypt, salted) ----------

def hash_password(password):
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1)
    return "scrypt$%s$%s" % (salt.hex(), dk.hex())


def verify_password(password, stored):
    try:
        _, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=2 ** 14, r=8, p=1,
        )
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def sha256_hash(value, salt=""):
    return hashlib.sha256((salt + value).encode("utf-8")).hexdigest()


def hmac_sign(secret, message):
    return hmac.new(secret.encode("utf-8"),
                    message.encode("utf-8"), hashlib.sha256).hexdigest()


def constant_eq(a, b):
    return hmac.compare_digest(str(a), str(b))


# ---------- server-side sessions ----------

def _cookie_name(kind):
    return (current_app.config["SESSION_COOKIE_NAME"] if kind == "user"
            else current_app.config["ADMIN_COOKIE_NAME"])


def _now_utc():
    return datetime.now(timezone.utc)


def _new_session(kind):
    conn = db.get_db()
    sid = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    expires = _now_utc() + timedelta(hours=current_app.config["SESSION_TTL_HOURS"])
    conn.execute(
        "INSERT INTO sessions(id, kind, csrf, data, expires_at) VALUES (?,?,?,?,?)",
        (sid, kind, csrf, "{}", expires.isoformat()),
    )
    sess = {"id": sid, "kind": kind, "user_id": None, "csrf": csrf,
            "data": "{}", "expires_at": expires.isoformat()}
    new_set = getattr(g, "_new_sessions", set())
    new_set.add(kind)
    g._new_sessions = new_set
    return sess


def current_session(kind="user"):
    """Load (or create) the session for this request, cached on flask.g."""
    attr = "_session_" + kind
    sess = getattr(g, attr, None)
    if sess is not None:
        return sess
    conn = db.get_db()
    sid = request.cookies.get(_cookie_name(kind))
    row = None
    if sid:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id=? AND kind=? AND expires_at > ?",
            (sid, kind, _now_utc().isoformat()),
        ).fetchone()
    sess = dict(row) if row else _new_session(kind)
    setattr(g, attr, sess)
    return sess


def touch_cookie_headers(response):
    """Set session cookies for any sessions created during this request."""
    for kind in g.get("_new_sessions", set()):
        sess = g.get("_session_" + kind)
        if sess:
            response.set_cookie(
                _cookie_name(kind), sess["id"],
                max_age=current_app.config["SESSION_TTL_HOURS"] * 3600,
                httponly=True,
                secure=not current_app.config["DEV_MODE"],
                samesite="Lax", path="/",
            )
    return response


def session_get(sess, key, default=None):
    return json.loads(sess.get("data") or "{}").get(key, default)


def session_put(sess, key, value):
    conn = db.get_db()
    data = json.loads(sess.get("data") or "{}")
    data[key] = value
    conn.execute("UPDATE sessions SET data=? WHERE id=?",
                 (json.dumps(data), sess["id"]))
    sess["data"] = json.dumps(data)


def destroy_session(sess):
    conn = db.get_db()
    conn.execute("DELETE FROM sessions WHERE id=?", (sess["id"],))


def csrf_check():
    """Validate CSRF token for POST requests (called from before_request)."""
    kind = "admin" if request.path.startswith("/admin") else "user"
    sess = current_session(kind)
    token = request.form.get("csrf", "")
    return bool(token) and constant_eq(token, sess["csrf"])
