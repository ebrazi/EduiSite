"""Application factory."""
import logging
import os

from flask import Flask, request, render_template

from . import db, security
from .config import config_dict, get_database_path


def create_app(database_path=None):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    cfg = config_dict()
    app.config.update(cfg)

    db_path = database_path or get_database_path()
    app.config["DATABASE_PATH"] = db_path

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db.init_schema(db_path)
    _ensure_admin_password(app)

    app.teardown_appcontext(db.close_db)

    _setup_admin_auth(app)

    from .routes import register_blueprints
    register_blueprints(app)

    @app.context_processor
    def inject_nav():
        # Read-only session lookup: avoids creating sessions for anonymous/crawler GETs.
        conn = db.get_db()
        uid = csrf = None
        sid = request.cookies.get(app.config["SESSION_COOKIE_NAME"])
        if sid:
            from datetime import datetime, timezone
            row = conn.execute(
                "SELECT user_id, csrf, expires_at FROM sessions WHERE id=? "
                "AND kind='user' AND expires_at > ?",
                (sid, datetime.now(timezone.utc).isoformat()),
            ).fetchone()
            if row:
                uid, csrf = row["user_id"], row["csrf"]
        return dict(session_user_id=uid, csrf_user=csrf)

    @app.before_request
    def csrf_protect():
        from flask import abort
        if request.method == "POST":
            if not security.csrf_check():
                from flask import abort
                abort(400, "درخواست نامعتبر (CSRF).")

    @app.after_request
    def touch_cookies(resp):
        return security.touch_cookie_headers(resp)

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; img-src 'self' data:; "
            "script-src 'self'; form-action 'self'; base-uri 'self'; "
            "frame-ancestors 'none'"
        )
        return resp

    @app.errorhandler(404)
    def not_found(e):
        return render_template("message.html", title="یافت نشد",
                               text="صفحه مورد نظر پیدا نشد."), 404

    @app.errorhandler(500)
    def server_error(e):
        if app.config["DEV_MODE"]:
            return render_template("message.html", title="خطا",
                                   text="خطای داخلی سرور (حالت توسعه)."), 500
        app.logger.error("500 on %s", request.path)
        return render_template("message.html", title="خطا",
                               text="خطای داخلی سرور. لطفاً بعداً تلاش کنید."), 500

    logging.basicConfig(
        level=logging.DEBUG if app.config["DEV_MODE"] else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return app


def _ensure_admin_password(app):
    conn = db.connect(app.config["DATABASE_PATH"])
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key='admin_pw_hash'"
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES ('admin_pw_hash', ?)",
                (security.hash_password(app.config["ADMIN_PASSWORD"]),),
            )
            conn.commit()
    finally:
        conn.close()


def _setup_admin_auth(app):
    """Expose verify_admin_password on the app config for the admin login view."""
    conn = db.connect(app.config["DATABASE_PATH"])
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key='admin_pw_hash'"
        ).fetchone()
        stored = row["value"]
    finally:
        conn.close()

    def verify(password):
        return security.verify_password(password, stored)

    app.config["VERIFY_ADMIN"] = verify
