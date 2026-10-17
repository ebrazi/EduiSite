"""End-to-end test suite (stdlib unittest + Flask test client).

Run:  .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""
import datetime as dt
import itertools
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ["DEV_MODE"] = "1"
_tmpdir = tempfile.mkdtemp(prefix="edusite_test_")
_DB_COUNTER = itertools.count()
os.environ["DATABASE_PATH"] = os.path.join(_tmpdir, "test.db")
os.environ["SECRET_KEY"] = "test-secret-key"

from app import create_app, db  # noqa: E402
from app.config import SESSION_PRICE, SLOT_TIMES, TZ  # noqa: E402
from app.services import booking, payments as pay_svc  # noqa: E402
from app.services.otp import issue_otp  # noqa: E402


def fresh_app():
    """App with a unique clean DB per test method."""
    base = os.path.join(_tmpdir, f"test{next(_DB_COUNTER)}.db")
    from app import create_app
    return create_app(database_path=base)


def reg_user(client, phone, relation="self", grade="دهم", goals=("تقویتی",), name="تست"):
    """Full registration flow through the real endpoints. Returns session csrf."""
    page = client.get("/register").get_data(as_text=True)
    csrf = get_csrf_from(page)
    assert csrf, "register page must embed csrf"
    resp = client.post("/register", data={"phone": phone, "csrf": csrf})
    page = client.get("/register/otp").get_data(as_text=True)
    dev_code = extract_dev_code(page)
    assert dev_code, "dev OTP must be visible in DEV_MODE"
    client.post("/register/otp", data={"code": dev_code, "csrf": csrf})
    client.post("/register/relation", data={"relation": relation, "name": name, "csrf": csrf})
    client.post("/register/grade", data={"grade": grade, "csrf": csrf})
    client.post("/register/goal", data={"goal": list(goals), "csrf": csrf})
    return get_csrf(client)


def get_csrf_from(html):
    import re
    m = re.search(r'name="csrf" value="([^"]+)"', html)
    return m.group(1) if m else None


def extract_dev_code(html):
    import re
    m = re.search(r"کد آزمایشی:\s*<strong>(\d{6})</strong>", html)
    return m.group(1) if m else None


def get_csrf(client):
    """Read the session csrf from a page that always renders a form."""
    html = client.get("/wallet").get_data(as_text=True)
    return get_csrf_from(html)


def top_up(client, csrf, amount=2_000_000):
    r = client.post("/wallet/topup", data={"amount": amount, "csrf": csrf})
    loc = r.headers["Location"]
    assert "/mock-gateway/pay/" in loc, f"expected mock gateway, got {loc}"
    page = client.get(loc).get_data(as_text=True)
    pay_csrf = get_csrf_from(page)
    return client.post(loc, data={"outcome": "success", "csrf": pay_csrf},
                       follow_redirects=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.app = fresh_app()
        self.app.config["TESTING"] = True
        self.app.config["TOPUP_AMOUNTS"] = [500000, 1000000, 2000000]
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()

    def tearDown(self):
        self.ctx.pop()


class TestRegistrationFlow(Base):
    def test_full_registration(self):
        csrf = reg_user(self.client, "09123456701", name="علی")
        self.assertIsNotNone(csrf)
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("داشبورد", html)

    def test_invalid_phone_rejected(self):
        page = self.client.get("/register").get_data(as_text=True)
        csrf = get_csrf_from(page)
        r = self.client.post("/register", data={"phone": "12345", "csrf": csrf})
        self.assertEqual(r.status_code, 400)

    def test_wrong_otp_rejected_then_correct(self):
        page = self.client.get("/register").get_data(as_text=True)
        csrf = get_csrf_from(page)
        self.client.post("/register", data={"phone": "09123456702", "csrf": csrf})
        r = self.client.post("/register/otp", data={"code": "000000", "csrf": csrf})
        self.assertEqual(r.status_code, 400)
        page = self.client.get("/register/otp").get_data(as_text=True)
        code = extract_dev_code(page)
        r = self.client.post("/register/otp", data={"code": code, "csrf": csrf})
        self.assertEqual(r.status_code, 302)

    def test_otp_rate_limit(self):
        self.app.config["OTP_RESEND_COOLDOWN"] = 0
        phone = "09123456703"
        ok1, _ = issue_otp(phone)
        issue_otp(phone)
        ok3, _ = issue_otp(phone)
        ok4, err = issue_otp(phone)  # 4th within window -> blocked
        self.assertFalse(ok4)
        self.assertIn("بیش از حد", err)

    def test_otp_resend_cooldown(self):
        phone = "09123456704"
        ok1, _ = issue_otp(phone)
        ok2, err = issue_otp(phone)
        self.assertFalse(ok2)
        self.assertIn("صبر کنید", err)


class TestBookingFlow(Base):
    def setUp(self):
        super().setUp()
        self.phone = "09123456710"
        self.csrf = reg_user(self.client, self.phone)
        top_up(self.client, self.csrf)

    def find_available_slot(self):
        html = self.client.get("/book").get_data(as_text=True)
        import re
        m = re.search(r'name="date" value="(\d{4}-\d{2}-\d{2})"', html)
        m2 = re.search(r'name="slot" value="(\d)"', html)
        return (m.group(1), int(m2.group(1))) if m and m2 else (None, None)

    def test_book_success(self):
        date, slot = self.find_available_slot()
        r = self.client.post("/book", data={"date": date, "slot": slot, "csrf": self.csrf})
        self.assertEqual(r.status_code, 302)
        conn = db.get_db()
        row = conn.execute(
            "SELECT status, price FROM reservations WHERE user_id=?",
            (security_user_id(self.client),),
        ).fetchone()
        self.assertEqual(row["status"], "booked")
        self.assertEqual(row["price"], SESSION_PRICE)
        # wallet deducted
        bal = conn.execute(
            "SELECT balance FROM wallets WHERE user_id=?",
            (security_user_id(self.client),),
        ).fetchone()["balance"]
        self.assertEqual(bal, 2_000_000 - SESSION_PRICE)

    def test_double_booking_same_user_and_other_user(self):
        date, slot = self.find_available_slot()
        r = self.client.post("/book", data={"date": date, "slot": slot, "csrf": self.csrf})
        self.assertEqual(r.status_code, 302)
        # second attempt (same user) -> blocked
        r2 = self.client.post("/book", data={"date": date, "slot": slot, "csrf": self.csrf})
        self.assertIn("error=", r2.headers["Location"])
        # another user, concurrent-ish: direct service-level race test below
        other = self.app.test_client()
        reg_user(other, "09123456711")
        top_up(other, get_csrf(other))
        r3 = other.post("/book", data={"date": date, "slot": slot, "csrf": get_csrf(other)})
        self.assertIn("error=", r3.headers["Location"])

    def test_insufficient_balance(self):
        date, slot = self.find_available_slot()
        broke = self.app.test_client()
        reg_user(broke, "09123456712")
        r = broke.post("/book", data={"date": date, "slot": slot, "csrf": get_csrf(broke)})
        self.assertIn("error=", r.headers["Location"])
        conn = db.get_db()
        n = conn.execute("SELECT COUNT(*) c FROM reservations").fetchone()["c"]
        self.assertEqual(n, 0)

    def test_double_booking_race_parallel(self):
        """Two truly concurrent booking requests -> exactly one succeeds."""
        date, slot = self.find_available_slot()
        other = self.app.test_client()
        reg_user(other, "09123456713")
        top_up(other, get_csrf(other))
        results = []

        def do(client, out):
            r = client.post("/book", data={"date": date, "slot": slot},
                            follow_redirects=True)
            out.append("رزرو شده" in r.get_data(as_text=True)
                       or "جلسات من" in r.get_data(as_text=True)
                       and "کنسل" in r.get_data(as_text=True))

        # Use direct service calls in threads to guarantee simultaneity
        u1 = security_user_id(self.client)
        u2 = security_user_id(other)
        errors = []

        def svc(uid):
            try:
                with self.app.test_request_context():
                    booking.book_slot(uid, date, slot)
                    errors.append("ok")
            except booking.BookingError as e:
                errors.append(str(e))

        t1 = threading.Thread(target=svc, args=(u1,))
        t2 = threading.Thread(target=svc, args=(u2,))
        t1.start(); t2.start(); t1.join(); t2.join()
        self.assertEqual(errors.count("ok"), 1, f"expected one success, got {errors}")


class TestCancellation(Base):
    def setUp(self):
        super().setUp()
        self.phone = "09123456720"
        self.csrf = reg_user(self.client, self.phone)
        top_up(self.client, self.csrf)

    def book_first(self):
        html = self.client.get("/book").get_data(as_text=True)
        import re
        m = re.search(r'name="date" value="(\d{4}-\d{2}-\d{2})"', html)
        m2 = re.search(r'name="slot" value="(\d)"', html)
        date, slot = m.group(1), int(m2.group(1))
        self.client.post("/book", data={"date": date, "slot": slot, "csrf": self.csrf})
        conn = db.get_db()
        return conn.execute(
            "SELECT id FROM reservations WHERE user_id=? AND status='booked'",
            (security_user_id(self.client),),
        ).fetchone()["id"]

    def test_user_cancel_full_refund(self):
        # booking_dates starts today -> a slot today is <24h away -> partial pct.
        # Book a slot >= CANCEL_FULL_HOURS away by picking the last day.
        dates = booking.booking_dates()
        target = dates[-1]
        slot = 0
        self.client.post("/book", data={"date": target, "slot": slot, "csrf": self.csrf})
        conn = db.get_db()
        rid = conn.execute(
            "SELECT id FROM reservations WHERE user_id=? AND status='booked'",
            (security_user_id(self.client),),
        ).fetchone()["id"]
        before = conn.execute(
            "SELECT balance FROM wallets WHERE user_id=?",
            (security_user_id(self.client),)).fetchone()["balance"]
        r = self.client.post(f"/cancel/{rid}", data={"csrf": self.csrf})
        self.assertEqual(r.status_code, 302)
        conn = db.get_db()
        row = conn.execute(
            "SELECT status, refund_amount FROM reservations WHERE id=?", (rid,)
        ).fetchone()
        self.assertEqual(row["status"], "cancelled_by_user")
        self.assertEqual(row["refund_amount"], SESSION_PRICE)  # >=24h -> 100%
        after = conn.execute(
            "SELECT balance FROM wallets WHERE user_id=?",
            (security_user_id(self.client),)).fetchone()["balance"]
        self.assertEqual(after, before + SESSION_PRICE)
        # slot free again
        self.assertFalse(booking.slot_taken(conn, target, slot))

    def test_user_cancel_partial_policy(self):
        # Slot today evening may be < CANCEL_PARTIAL_HOURS -> 0%; depends on clock.
        # Directly verify refund_percent_for boundaries instead (policy math).
        self.assertEqual(booking.refund_percent_for(48), 100)
        self.assertEqual(
            booking.refund_percent_for(
                (self.app.config["CANCEL_FULL_HOURS"] +
                 self.app.config["CANCEL_PARTIAL_HOURS"]) / 2),
            self.app.config["CANCEL_PARTIAL_PERCENT"])
        self.assertEqual(booking.refund_percent_for(1), 0)

    def test_teacher_cancel_full_refund(self):
        rid = self.book_first()
        admin = self.app.test_client()
        self.admin_login(admin)
        page = admin.get("/admin/reservations").get_data(as_text=True)
        csrf_admin = get_csrf_from(page)
        if csrf_admin is None:
            csrf_admin = get_csrf_from(
                admin.get("/admin/availability").get_data(as_text=True))
        r = admin.post(f"/admin/reservations/{rid}/cancel",
                       data={"csrf": csrf_admin})
        self.assertEqual(r.status_code, 302)
        conn = db.get_db()
        row = conn.execute(
            "SELECT status, refund_amount FROM reservations WHERE id=?", (rid,)
        ).fetchone()
        self.assertEqual(row["status"], "cancelled_by_teacher")
        self.assertEqual(row["refund_amount"], SESSION_PRICE)
        bal = conn.execute(
            "SELECT balance FROM wallets WHERE user_id=?",
            (security_user_id(self.client),)).fetchone()["balance"]
        self.assertEqual(bal, 2_000_000)  # fully refunded

    def admin_login(self, client):
        page = client.get("/admin/login").get_data(as_text=True)
        import re
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        r = client.post("/admin/login", data={"password": "admin1234", "csrf": csrf})
        self.assertEqual(r.status_code, 302)


class TestAvailabilityControl(Base):
    def setUp(self):
        super().setUp()
        self.admin = self.app.test_client()
        page = self.admin.get("/admin/login").get_data(as_text=True)
        import re
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        self.admin.post("/admin/login", data={"password": "admin1234", "csrf": csrf})
        self.csrf_user = reg_user(self.client, "09123456730")
        top_up(self.client, self.csrf_user)

    def test_day_disabled_blocks_all_slots(self):
        dates = booking.booking_dates()
        target = dates[5]
        page = self.admin.get("/admin/availability").get_data(as_text=True)
        import re
        csrf_admin = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        self.admin.post("/admin/availability/day",
                        data={"date": target, "mode": "close", "csrf": csrf_admin})
        conn = db.get_db()
        for idx in range(3):
            self.assertFalse(booking.is_slot_active(conn, target, idx))
        csrf_user = get_csrf(self.client)
        r = self.client.post("/book", data={"date": target, "slot": 0, "csrf": csrf_user},
                             follow_redirects=True)
        self.assertIn("فعال نیست", r.get_data(as_text=True))

    def test_single_slot_disabled(self):
        dates = booking.booking_dates()
        target = dates[6]
        page = self.admin.get("/admin/availability").get_data(as_text=True)
        import re
        csrf_admin = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        self.admin.post("/admin/availability/slot",
                        data={"date": target, "slot": 1, "active": "0", "csrf": csrf_admin})
        conn = db.get_db()
        self.assertFalse(booking.is_slot_active(conn, target, 1))
        self.assertTrue(booking.is_slot_active(conn, target, 0))
        self.assertTrue(booking.is_slot_active(conn, target, 2))
        csrf_user = get_csrf(self.client)
        r = self.client.post("/book", data={"date": target, "slot": 1, "csrf": csrf_user},
                             follow_redirects=True)
        self.assertIn("فعال نیست", r.get_data(as_text=True))
        r2 = self.client.post("/book", data={"date": target, "slot": 0, "csrf": csrf_user},
                              follow_redirects=True)
        self.assertNotIn("فعال نیست", r2.get_data(as_text=True))


class TestPayments(Base):
    def setUp(self):
        super().setUp()
        self.csrf = reg_user(self.client, "09123456740")

    def do_topup(self, outcome="success"):
        csrf = get_csrf(self.client)
        r = self.client.post("/wallet/topup",
                             data={"amount": 500000, "csrf": csrf})
        loc = r.headers["Location"]
        page = self.client.get(loc).get_data(as_text=True)
        pay_csrf = get_csrf_from(page)
        r2 = self.client.post(loc, data={"outcome": outcome, "csrf": pay_csrf})
        return r2.headers["Location"]

    def test_topup_success(self):
        loc = self.do_topup("success")
        r = self.client.get(loc)
        self.assertIn("موفقیت", r.get_data(as_text=True))
        conn = db.get_db()
        bal = conn.execute(
            "SELECT balance FROM wallets WHERE user_id=?",
            (security_user_id(self.client),)).fetchone()["balance"]
        self.assertEqual(bal, 500000)

    def test_topup_failed(self):
        loc = self.do_topup("failed")
        r = self.client.get(loc)
        self.assertIn("ناموفق", r.get_data(as_text=True))
        conn = db.get_db()
        bal = conn.execute(
            "SELECT balance FROM wallets WHERE user_id=?",
            (security_user_id(self.client),)).fetchone()["balance"]
        self.assertEqual(bal, 0)

    def test_duplicate_callback_idempotent(self):
        self.client.post("/wallet/topup",
                         data={"amount": 500000, "csrf": self.csrf})
        conn = db.get_db()
        p = conn.execute(
            "SELECT id FROM payments WHERE user_id=? AND status='initiated'",
            (security_user_id(self.client),)).fetchone()
        from app.services.payments import MockGateway
        from app.security import hmac_sign
        tx = "MOCK-DUP1"
        sig = hmac_sign(self.app.config["MOCK_GATEWAY_SECRET"],
                        f"{p['id']}:{tx}:success")
        url = (f"/payment/callback?payment_id={p['id']}&tx_id={tx}"
               f"&status=success&sig={sig}")
        self.client.get(url)
        self.client.get(url)  # replay
        self.client.get(url)  # replay again
        bal = conn.execute(
            "SELECT balance FROM wallets WHERE user_id=?",
            (security_user_id(self.client),)).fetchone()["balance"]
        self.assertEqual(bal, 500000, "double credit must not happen")

    def test_forged_callback_rejected(self):
        r = self.client.get(
            "/payment/callback?payment_id=1&tx_id=FAKE&status=success&sig=deadbeef")
        self.assertEqual(r.status_code, 400)
        conn = db.get_db()
        p = conn.execute("SELECT status FROM payments WHERE id=1").fetchone()
        # payment 1 may not exist; key check: no crash, no credit
        bal = conn.execute(
            "SELECT balance FROM wallets WHERE user_id=?",
            (security_user_id(self.client),)).fetchone()["balance"]
        self.assertEqual(bal, 0)


class TestSecurity(Base):
    def setUp(self):
        super().setUp()
        self.csrf = reg_user(self.client, "09123456750")
        top_up(self.client, self.csrf)
        self.other = self.app.test_client()
        reg_user(self.other, "09123456751")

    def test_anonymous_redirected(self):
        r = self.app.test_client().get("/dashboard")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    def test_admin_panel_blocked_for_user(self):
        r = self.client.get("/admin")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/admin/login", r.headers["Location"])
        r2 = self.client.get("/admin/reservations")
        self.assertIn("/admin/login", r2.headers["Location"])

    def test_wrong_admin_password(self):
        admin = self.app.test_client()
        page = admin.get("/admin/login").get_data(as_text=True)
        import re
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        r = admin.post("/admin/login", data={"password": "wrong", "csrf": csrf})
        self.assertEqual(r.status_code, 401)

    def test_csrf_required(self):
        r = self.client.post("/book", data={"date": "2099-01-01", "slot": 0})
        self.assertEqual(r.status_code, 400)

    def test_idor_cancel_other_users_reservation(self):
        # other user books a slot
        other_csrf = get_csrf(self.other)
        top_up(self.other, other_csrf)
        html = self.other.get("/book").get_data(as_text=True)
        import re
        date = re.search(r'name="date" value="(\d{4}-\d{2}-\d{2})"', html).group(1)
        slot = int(re.search(r'name="slot" value="(\d)"', html).group(1))
        self.other.post("/book", data={"date": date, "slot": slot, "csrf": other_csrf})
        conn = db.get_db()
        rid = conn.execute(
            "SELECT id FROM reservations WHERE user_id=? AND status='booked'",
            (security_user_id(self.other),)).fetchone()["id"]
        # our user tries to cancel it -> must not work
        r = self.client.post(f"/cancel/{rid}", data={"csrf": self.csrf})
        self.assertEqual(r.status_code, 302)
        row = conn.execute(
            "SELECT status FROM reservations WHERE id=?", (rid,)).fetchone()
        self.assertEqual(row["status"], "booked")

    def test_wallet_not_writable_via_params(self):
        # attempt to book with manipulated price (server uses config price)
        html = self.client.get("/book").get_data(as_text=True)
        import re
        date = re.search(r'name="date" value="(\d{4}-\d{2}-\d{2})"', html).group(1)
        slot = int(re.search(r'name="slot" value="(\d)"', html).group(1))
        r = self.client.post("/book",
                             data={"date": date, "slot": slot, "price": 1,
                                   "csrf": self.csrf})
        conn = db.get_db()
        row = conn.execute(
            "SELECT price FROM reservations WHERE user_id=?",
            (security_user_id(self.client),)).fetchone()
        self.assertEqual(row["price"], SESSION_PRICE)

    def test_otp_flood_blocked(self):
        # 4th send within window blocked (3 allowed)
        self.app.config["OTP_RESEND_COOLDOWN"] = 0
        phone = "09123456752"
        results = [issue_otp(phone)[0] for _ in range(4)]
        self.assertEqual(results, [True, True, True, False])

    def test_security_headers(self):
        r = self.client.get("/")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")

    def test_session_cookie_flags(self):
        r = self.client.get("/register")
        set_cookie = r.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Lax", set_cookie)


def security_user_id(client):
    """Get the logged-in user id for a test client (via session cookie)."""
    cookie = client.get_cookie(os.environ.get("SESSION_COOKIE_NAME", "sid")) \
        if hasattr(client, "get_cookie") else None
    # Flask 3 test client: client.get_cookie(name)
    conn = db.get_db()
    row = conn.execute(
        "SELECT user_id FROM sessions WHERE id=?", (cookie.value,)
    ).fetchone()
    return row["user_id"]


if __name__ == "__main__":
    unittest.main(verbosity=2)
