"""Development seed data (dev only): students, availability, reservations,
payments, cancellations. Uses fake data only.

Usage:  .venv\\Scripts\\python.exe seed.py
"""
import datetime as dt

from app import create_app
from app import db
from app.config import TZ, SESSION_PRICE
from app.services.wallet import apply

app = create_app()

SLOT_TIMES = app.config["SLOT_TIMES"]


def main():
    with app.app_context():
        conn = db.get_db()
        with db.immediate_tx(conn):
            # wipe previous dev data
            for t in ("payments", "reservations", "wallet_txns", "wallets",
                      "sessions", "otp_codes", "users", "availability"):
                conn.execute(f"DELETE FROM {t}")

            students = [
                ("09120000001", "علی رضایی", "self", "دهم", "تقویتی,آزمون / کنکور"),
                ("09120000002", "سارا محمدی", "parent", "نهم", "تقویتی"),
                ("09120000003", "محمد کریمی", "sibling", "یازدهم", "پیشرفته,المپیاد"),
                ("09120000004", "نگار احمدی", "self", "کنکوری", "آزمون / کنکور"),
            ]
            ids = {}
            for phone, name, rel, grade, goals in students:
                cur = conn.execute(
                    "INSERT INTO users(phone, name, owner_relation, grade, goals) "
                    "VALUES (?,?,?,?,?)", (phone, name, rel, grade, goals))
                ids[phone] = cur.lastrowid
                conn.execute(
                    "INSERT INTO wallets(user_id, balance) VALUES (?,?)",
                    (cur.lastrowid, 1_500_000))

            today = dt.datetime.now(TZ).date()
            dates = [(today + dt.timedelta(days=i)).isoformat() for i in range(14)]
            # default availability: all active, Fridays off
            for d in dates:
                friday = dt.date.fromisoformat(d).weekday() == 4
                for idx in range(3):
                    conn.execute(
                        "INSERT INTO availability(date, slot_index, is_active) VALUES (?,?,?)",
                        (d, idx, 0 if friday else 1))
            # one slot on day+2 disabled individually
            conn.execute(
                "UPDATE availability SET is_active=0 WHERE date=? AND slot_index=1",
                (dates[2],))

            # reservations
            r1 = conn.execute(
                "INSERT INTO reservations(user_id, date, slot_index, price, status) "
                "VALUES (?,?,?,?,'booked')",
                (ids["09120000001"], dates[1], 0, SESSION_PRICE)).lastrowid
            conn.execute(
                "INSERT INTO reservations(user_id, date, slot_index, price, status, refund_amount, cancel_actor) "
                "VALUES (?,?,?,?,'cancelled_by_teacher',?, 'teacher')",
                (ids["09120000002"], dates[1], 1, SESSION_PRICE, SESSION_PRICE))
            conn.execute(
                "INSERT INTO reservations(user_id, date, slot_index, price, status, refund_amount, cancel_actor) "
                "VALUES (?,?,?,?,'cancelled_by_user',?, 'user')",
                (ids["09120000003"], dates[0], 2, SESSION_PRICE, SESSION_PRICE))

            # successful topup payments + wallet history
            for phone in ids:
                p = conn.execute(
                    "INSERT INTO payments(user_id, kind, amount, status, gateway, gateway_ref, gateway_tx_id) "
                    "VALUES (?,?,?,'verified','mock',?,?)",
                    (ids[phone], "topup", 1_500_000, f"P{phone[-3:]}", f"MOCK-{phone[-3:]}")).lastrowid
                apply(conn, ids[phone], 1_500_000, "topup", "payment", p, note="شارژ کیف پول (تست)")

            # failed payment
            conn.execute(
                "INSERT INTO payments(user_id, kind, amount, status, gateway, gateway_ref) "
                "VALUES (?,?,?,'failed','mock',?)",
                (ids["09120000004"], "topup", 1_000_000, "PFAIL1"))

            # wallet history matching reservations
            apply(conn, ids["09120000001"], -SESSION_PRICE, "session_payment", "reservation", r1, note="رزرو جلسه")
            db.audit(conn, "seed", "seed.completed", "development test data")

        print("Seed data created (dev).")


if __name__ == "__main__":
    main()
