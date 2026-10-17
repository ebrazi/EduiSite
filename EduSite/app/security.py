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
    created = getattr(g, "_sessions_created", [])
    created.append(sess)
    g._sessions_created = created
    return sess


def _request_token():
    """Unique token for the current request context (Werkzeug reuses request objects)."""
    tok = getattr(g, "_req_tok", None)
    if tok is None:
        tok = secrets.token_hex(8)
        g._req_tok = tok
    return tok


def current_session(kind="user"):
    """Load (or create) the session for this request, cached on flask.g.

    Cache key includes the cookie value so multiple Flask test clients sharing
    one long-lived app context cannot leak sessions into each other.
    """
    sid_cookie = request.cookies.get(_cookie_name(kind)) or ""
    cache_attr = "_session_%s_%s" % (kind, sid_cookie or ("_pending_%s" % _request_token()))
    sess = getattr(g, cache_attr, None)
    if sess is not None:
        return sess
    # Mid-request newly created session (Set-Cookie not yet round-tripped).
    pending_attr = "_session_%s__pending_%s" % (kind, _request_token())
    if not sid_cookie:
        sess = getattr(g, pending_attr, None)
        if sess is not None:
            return sess
    conn = db.get_db()
    row = None
    if sid_cookie:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id=? AND kind=? AND expires_at > ?",
            (sid_cookie, kind, _now_utc().isoformat()),
        ).fetchone()
    if row:
        sess = dict(row)
        setattr(g, cache_attr, sess)
    else:
        sess = _new_session(kind)
        setattr(g, pending_attr, sess)
        setattr(g, cache_attr, sess)
    return sess


def touch_cookie_headers(response):
    """Set session cookies only for sessions created during THIS request."""
    for sess in getattr(g, "_sessions_created", []):
        kind = sess.get("kind", "user")
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
    """Update JSON data; when key is user_id also keep the column in sync.

    The sessions.user_id column is used by the context_processor (nav) and by
    tests; the JSON field is the primary store for all session state.
    """
    conn = db.get_db()
    data = json.loads(sess.get("data") or "{}")
    data[key] = value
    if key == "user_id":
        # Keep the denormalized column in sync (NULL when logged out / cleared).
        conn.execute(
            "UPDATE sessions SET data=?, user_id=? WHERE id=?",
            (json.dumps(data), value, sess["id"]),
        )
        sess["user_id"] = value
    else:
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
