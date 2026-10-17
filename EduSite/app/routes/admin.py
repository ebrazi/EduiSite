"""Teacher (admin) panel: separate session cookie, password login, strict
server-side authorization on every route."""
import functools

from flask import (Blueprint, abort, current_app, g, make_response,
                   redirect, render_template, request, url_for)

from .. import db, security
from ..jalali import format_date_fa, format_money
from ..services import booking

bp = Blueprint("admin", __name__)


def admin_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        sess = security.current_session("admin")
        if not security.session_get(sess, "admin"):
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)
    return wrapped


@bp.route("/admin/login", methods=["GET", "POST"])
def login():
    sess = security.current_session("admin")
    if request.method == "POST":
        password = request.form.get("password", "")
        if not current_app.config["VERIFY_ADMIN"](password):
            db.audit(db.get_db(), "anonymous", "admin.login_failed",
                     f"ip={request.remote_addr}")
            return render_template("admin_login.html",
                                   error="رمز نادرست است.", csrf=sess["csrf"]), 401
        security.session_put(sess, "admin", True)
        db.audit(db.get_db(), "admin", "admin.login", f"ip={request.remote_addr}")
        return redirect(url_for("admin.panel"))
    return render_template("admin_login.html", error=None, csrf=sess["csrf"])


@bp.route("/admin/logout", methods=["POST"])
def logout():
    sess = security.current_session("admin")
    security.destroy_session(sess)
    resp = make_response(redirect(url_for("admin.login")))
    resp.delete_cookie(current_app.config["ADMIN_COOKIE_NAME"], path="/")
    return resp


@bp.route("/admin")
@admin_required
def panel():
    return render_template("admin_panel.html")


@bp.route("/admin/availability")
@admin_required
def availability():
    conn = db.get_db()
    days = []
    now = booking.tehran_now()
    for date_iso in booking.booking_dates():
        slots = []
        for idx in range(len(current_app.config["SLOT_TIMES"])):
            start, _end = booking.slot_start_end(date_iso, idx)
            slots.append({
                "idx": idx,
                "label": booking.formatted_slot(idx),
                "active": booking.is_slot_active(conn, date_iso, idx),
                "past": start <= now,
            })
        days.append({"iso": date_iso, "label": format_date_fa(date_iso),
                     "slots": slots})
    return render_template("admin_availability.html", days=days,
                           csrf=security.current_session("admin")["csrf"])


@bp.route("/admin/availability/day", methods=["POST"])
@admin_required
def set_day():
    date_iso = request.form.get("date", "")
    try:
        from datetime import date as _date
        _date.fromisoformat(date_iso)
    except ValueError:
        abort(400)
    # "mode" = open (all slots active) or close (whole day disabled)
    mode = request.form.get("mode")
    if mode not in ("open", "close"):
        abort(400)
    conn = db.get_db()
    active = 1 if mode == "open" else 0
    with db.immediate_tx(conn):
        for idx in range(len(current_app.config["SLOT_TIMES"])):
            conn.execute(
                "INSERT INTO availability(date, slot_index, is_active) VALUES (?,?,?) "
                "ON CONFLICT(date, slot_index) DO UPDATE SET is_active=excluded.is_active",
                (date_iso, idx, active),
            )
        db.audit(conn, "admin", "availability.day",
                 f"date={date_iso} mode={mode}")
    return redirect(url_for("admin.availability"))


@bp.route("/admin/availability/slot", methods=["POST"])
@admin_required
def set_slot():
    date_iso = request.form.get("date", "")
    try:
        from datetime import date as _date
        _date.fromisoformat(date_iso)
        slot_index = int(request.form["slot"])
        if slot_index not in (0, 1, 2):
            raise ValueError
    except (KeyError, ValueError):
        abort(400)
    active = request.form.get("active") == "1"
    booking.set_availability(date_iso, slot_index, active, actor="admin")
    return redirect(url_for("admin.availability"))


@bp.route("/admin/reservations")
@admin_required
def reservations():
    conn = db.get_db()
    rows = conn.execute(
        "SELECT r.*, u.name AS u_name, u.phone AS u_phone, "
        "u.owner_relation AS u_relation, u.grade AS u_grade, u.goals AS u_goals "
        "FROM reservations r JOIN users u ON u.id = r.user_id "
        "ORDER BY r.id DESC LIMIT 100"
    ).fetchall()
    items = []
    for r in rows:
        items.append({
            "row": r,
            "date_fa": format_date_fa(r["date"]),
            "slot_fa": booking.formatted_slot(r["slot_index"]),
            "relation_fa": dict(current_app.config["RELATION_CHOICES"]).get(
                r["u_relation"], r["u_relation"]),
            "can_cancel": r["status"] == "booked",
        })
    return render_template("admin_reservations.html", items=items,
                           money=format_money,
                           csrf=security.current_session("admin")["csrf"])


@bp.route("/admin/reservations/<int:rid>/cancel", methods=["POST"])
@admin_required
def cancel_reservation(rid):
    from ..services.booking import BookingError
    try:
        booking.cancel_by_teacher(rid)
    except booking.BookingError:
        pass
    return redirect(url_for("admin.reservations"))


@bp.route("/admin/payments")
@admin_required
def payments():
    conn = db.get_db()
    rows = conn.execute(
        "SELECT p.*, u.phone AS u_phone FROM payments p "
        "JOIN users u ON u.id=p.user_id ORDER BY p.id DESC LIMIT 100"
    ).fetchall()
    wallets = conn.execute(
        "SELECT u.name, u.phone, w.balance FROM wallets w "
        "JOIN users u ON u.id=w.user_id ORDER BY u.id"
    ).fetchall()
    return render_template("admin_payments.html", payments=rows, wallets=wallets,
                           money=format_money)
