"""Scheduling & reservation logic: slots, availability, booking, cancellation."""
import datetime as _dt
import sqlite3

from flask import current_app

from .. import db
from ..jalali import format_date_fa, format_time_fa
from .wallet import apply, WalletError

def tehran_now():
    return _dt.datetime.now(current_app.config["TZ"])


def slot_start_end(date_iso, slot_index):
    """Return (start_dt, end_dt) aware datetimes in Tehran time."""
    start_hhmm, end_hhmm = current_app.config["SLOT_TIMES"][slot_index]
    d = _dt.date.fromisoformat(date_iso)
    sh, sm = map(int, start_hhmm.split(":"))
    eh, em = map(int, end_hhmm.split(":"))
    tz = current_app.config["TZ"]
    start = _dt.datetime(d.year, d.month, d.day, sh, sm, tzinfo=tz)
    end = _dt.datetime(d.year, d.month, d.day, eh, em, tzinfo=tz)
    return start, end


def booking_dates():
    """Next N days (today included) as ISO strings."""
    n = current_app.config["BOOKING_DAYS_AHEAD"]
    today = tehran_now().date()
    return [(today + _dt.timedelta(days=i)).isoformat() for i in range(n)]


def is_slot_active(conn, date_iso, slot_index):
    row = conn.execute(
        "SELECT is_active FROM availability WHERE date=? AND slot_index=?",
        (date_iso, slot_index),
    ).fetchone()
    return row["is_active"] == 1 if row else True  # default: active


def slot_taken(conn, date_iso, slot_index):
    row = conn.execute(
        "SELECT 1 FROM reservations WHERE date=? AND slot_index=? "
        "AND status IN ('pending_payment','booked')",
        (date_iso, slot_index),
    ).fetchone()
    return row is not None


def refund_percent_for(hours_until):
    cfg = current_app.config
    if hours_until >= cfg["CANCEL_FULL_HOURS"]:
        return 100
    if hours_until >= cfg["CANCEL_PARTIAL_HOURS"]:
        return cfg["CANCEL_PARTIAL_PERCENT"]
    return 0


def refund_percent_for_reservation(date_iso, slot_index):
    start, _ = slot_start_end(date_iso, slot_index)
    seconds = (start - tehran_now()).total_seconds()
    return refund_percent_for(seconds / 3600.0)


class BookingError(Exception):
    pass


def book_slot(user_id, date_iso, slot_index):
    """Atomically: check availability/past/taken, deduct wallet, insert reservation.

    Concurrency: single IMMEDIATE transaction + explicit check + partial UNIQUE index on
    (date, slot_index) for active reservations -> only one concurrent booking
    can succeed.
    """
    cfg = current_app.config
    price = cfg["SESSION_PRICE"]
    conn = db.get_db()
    start, _end = slot_start_end(date_iso, slot_index)
    if start <= tehran_now():
        raise BookingError("این زمان گذشته است.")
    with db.immediate_tx(conn):
        if not is_slot_active(conn, date_iso, slot_index):
            raise BookingError("این بازه برای رزرو فعال نیست.")
        if slot_taken(conn, date_iso, slot_index):
            raise BookingError("این زمان قبلاً رزرو شده است.")
        try:
            cur = conn.execute(
                "INSERT INTO reservations(user_id, date, slot_index, price, status) "
                "VALUES (?,?,?,?, 'booked')",
                (user_id, date_iso, slot_index, price),
            )
        except sqlite3.IntegrityError:
            raise BookingError("این زمان قبلاً رزرو شده است.")
        try:
            apply(conn, user_id, -price, "session_payment", "reservation",
                  cur.lastrowid, note="رزرو جلسه")
        except WalletError:
            raise BookingError("موجودی کیف پول کافی نیست. ابتدا کیف پول را شارژ کنید.")
        db.audit(conn, f"user:{user_id}", "reservation.created",
                 f"reservation_id={cur.lastrowid} date={date_iso} slot={slot_index}")
        return cur.lastrowid


def cancel_by_user(user_id, reservation_id):
    """User cancels own reservation; refund per configurable policy."""
    conn = db.get_db()
    now = tehran_now()
    with db.immediate_tx(conn):
        r = conn.execute(
            "SELECT * FROM reservations WHERE id=? AND user_id=?",
            (reservation_id, user_id),
        ).fetchone()
        if r is None or r["status"] != "booked":
            raise BookingError("رزرو قابل کنسل نیست.")
        start, _end = slot_start_end(r["date"], r["slot_index"])
        if start <= now:
            raise BookingError("زمان جلسه شروع شده؛ کنسلی ممکن نیست.")
        hours = (start - now).total_seconds() / 3600.0
        pct = refund_percent_for(hours)
        refund = r["price"] * pct // 100
        conn.execute(
            "UPDATE reservations SET status='cancelled_by_user', refund_amount=?, "
            "cancelled_at=?, cancel_actor='user' WHERE id=?",
            (refund, db.utcnow_iso(), r["id"]),
        )
        if refund > 0:
            apply(conn, user_id, refund, "refund", "reservation", r["id"],
                  note=f"برگشت {pct}٪ مبلغ کنسلی")
        db.audit(conn, f"user:{user_id}", "reservation.cancelled_by_user",
                 f"reservation_id={r['id']} refund={refund}")
        return refund


def cancel_by_teacher(reservation_id):
    """Teacher cancels; student gets 100% refund to wallet."""
    conn = db.get_db()
    with db.immediate_tx(conn):
        r = conn.execute(
            "SELECT * FROM reservations WHERE id=? AND status='booked'",
            (reservation_id,),
        ).fetchone()
        if r is None:
            raise BookingError("رزرو قابل کنسل نیست.")
        refund = r["price"]
        conn.execute(
            "UPDATE reservations SET status='cancelled_by_teacher', refund_amount=?, "
            "cancelled_at=?, cancel_actor='teacher' WHERE id=?",
            (refund, db.utcnow_iso(), r["id"]),
        )
        apply(conn, r["user_id"], refund, "refund", "reservation", r["id"],
              note="کنسلی از طرف مدرس؛ برگشت کامل مبلغ")
        db.audit(conn, "admin", "reservation.cancelled_by_teacher",
                 f"reservation_id={r['id']} refund={refund} user={r['user_id']}")
        return refund


def set_availability(date_iso, slot_index, active, actor="admin"):
    conn = db.get_db()
    with db.immediate_tx(conn):
        conn.execute(
            "INSERT INTO availability(date, slot_index, is_active) VALUES (?,?,?) "
            "ON CONFLICT(date, slot_index) DO UPDATE SET is_active=excluded.is_active",
            (date_iso, slot_index, 1 if active else 0),
        )
        db.audit(conn, actor, "availability.set",
                 f"date={date_iso} slot={slot_index} active={int(bool(active))}")


def formatted_slot(slot_index):
    s, e = current_app.config["SLOT_TIMES"][slot_index]
    return f"{format_time_fa(s)} تا {format_time_fa(e)}"
