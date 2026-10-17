"""Authenticated user pages: dashboard, booking, wallet, cancellation."""
import functools

from flask import (Blueprint, current_app, g, redirect, render_template,
                   request, url_for)

from .. import db, security
from ..jalali import format_date_fa, format_money
from ..services import booking, payments as pay_svc
from ..services.wallet import get_balance

bp = Blueprint("user", __name__)


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        sess = security.current_session("user")
        if not security.session_get(sess, "user_id"):
            return redirect(url_for("auth.login"))
        g.user_id = security.session_get(sess, "user_id")
        return view(*args, **kwargs)
    return wrapped


def current_user(conn=None):
    conn = conn or db.get_db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (g.user_id,)).fetchone()
    return row


@bp.route("/dashboard")
@login_required
def dashboard():
    conn = db.get_db()
    user = current_user(conn)
    if user is None:
        # User not found in database - this should not happen with @login_required
        # but handle it gracefully
        return redirect(url_for("auth.login"))
    balance = get_balance(conn, g.user_id)
    today = booking.tehran_now().date().isoformat()
    reservations = conn.execute(
        "SELECT * FROM reservations WHERE user_id=? AND date >= ? "
        "AND status IN ('booked','cancelled_by_user','cancelled_by_teacher') "
        "ORDER BY date, slot_index",
        (g.user_id, today),
    ).fetchall()
    items = []
    for r in reservations:
        can_cancel = (r["status"] == "booked"
                      and booking.slot_start_end(r["date"], r["slot_index"])[0]
                      > booking.tehran_now())
        items.append({
            "row": r,
            "date_fa": format_date_fa(r["date"]),
            "slot_fa": booking.formatted_slot(r["slot_index"]),
            "can_cancel": can_cancel,
            "refund_pct": booking.refund_percent_for_reservation(r["date"], r["slot_index"]),
        })
    return render_template("dashboard.html", user=user, balance=balance,
                           reservations=items, money=format_money)


@bp.route("/book")
@login_required
def book():
    conn = db.get_db()
    user = current_user(conn)
    if user is None:
        return redirect(url_for("auth.login"))
    balance = get_balance(conn, g.user_id)
    price = current_app.config["SESSION_PRICE"]
    days = []
    now = booking.tehran_now()
    for date_iso in booking.booking_dates():
        slots = []
        for idx in range(len(current_app.config["SLOT_TIMES"])):
            start, _end = booking.slot_start_end(date_iso, idx)
            active = booking.is_slot_active(conn, date_iso, idx)
            taken = booking.slot_taken(conn, date_iso, idx)
            past = start <= now
            slots.append({
                "idx": idx, "label": booking.formatted_slot(idx),
                "available": active and not taken and not past,
            })
        days.append({"iso": date_iso, "label": format_date_fa(date_iso), "slots": slots})
    return render_template("book.html", days=days, balance=balance, price=price,
                           money=format_money, user=user,
                           error=request.args.get("error"))


@bp.route("/book", methods=["POST"])
@login_required
def book_post():
    try:
        date_iso = request.form["date"]
        slot_index = int(request.form["slot"])
        if slot_index not in (0, 1, 2):
            raise ValueError
        from ..services.booking import BookingError
        booking.book_slot(g.user_id, date_iso, slot_index)
    except (KeyError, ValueError):
        return redirect(url_for("user.book", error="درخواست نامعتبر است."))
    except booking.BookingError as e:
        return redirect(url_for("user.book", error=str(e)))
    return redirect(url_for("user.dashboard"))


@bp.route("/cancel/<int:reservation_id>", methods=["POST"])
@login_required
def cancel(reservation_id):
    from ..services.booking import BookingError
    try:
        booking.cancel_by_user(g.user_id, reservation_id)
    except booking.BookingError:
        pass
    return redirect(url_for("user.dashboard"))


@bp.route("/wallet")
@login_required
def wallet():
    conn = db.get_db()
    user = current_user(conn)
    if user is None:
        return redirect(url_for("auth.login"))
    balance = get_balance(conn, g.user_id)
    txns = conn.execute(
        "SELECT * FROM wallet_txns WHERE user_id=? ORDER BY id DESC LIMIT 20",
        (g.user_id,),
    ).fetchall()
    amounts = current_app.config["TOPUP_AMOUNTS"]
    status = request.args.get("payment")
    return render_template("wallet.html", user=user, balance=balance, txns=txns,
                           amounts=amounts, money=format_money,
                           payment_status=status, payment_failed=request.args.get("fail"))


@bp.route("/wallet/topup", methods=["POST"])
@login_required
def wallet_topup():
    try:
        amount = int(request.form["amount"])
    except (KeyError, ValueError):
        return redirect(url_for("user.wallet"))
    if amount not in current_app.config["TOPUP_AMOUNTS"]:
        return redirect(url_for("user.wallet"))
    payment_id = pay_svc.create_topup_payment(g.user_id, amount)
    if current_app.config["DEV_MODE"]:
        from ..services.payments import MockGateway
        return redirect(MockGateway.pay_url(payment_id))
    # Production: redirect to the real gateway's payment URL here.
    return redirect(url_for("user.wallet"))


@bp.route("/payment/callback")
def payment_callback():
    """Gateway-agnostic callback endpoint.

    In DEV the MockGateway verifies the signed params; in production a real
    gateway adapter performs verification (e.g. server-side API verify call).
    """
    if current_app.config["DEV_MODE"]:
        from ..services.payments import MockGateway
        try:
            payment_id = int(request.args["payment_id"])
        except (KeyError, ValueError):
            return render_template("message.html", title="پرداخت",
                                   text="درخواست نامعتبر."), 400
        ok, reason = MockGateway.verify_callback(
            payment_id,
            request.args.get("tx_id", ""),
            request.args.get("status", ""),
            request.args.get("sig", ""),
        )
        if not ok:
            # Invalid/forged callback: no state change.
            return render_template("message.html", title="پرداخت",
                                   text="اطلاعات callback معتبر نیست."), 400
        result, _already = pay_svc.process_callback(
            payment_id, request.args["tx_id"],
            request.args.get("status") == "success",
        )
        if result == "verified":
            return redirect(url_for("user.wallet", payment="ok"))
        if result in ("failed", "already"):
            return redirect(url_for("user.wallet",
                                    payment="failed" if result == "failed" else "ok"))
        return render_template("message.html", title="پرداخت",
                               text="پرداخت یافت نشد."), 404
    # Production gateway callback handling goes here.
    return render_template("message.html", title="پرداخت",
                           text="درگاه پرداخت واقعی هنوز متصل نیست."), 501
