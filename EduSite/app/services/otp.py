"""OTP issue/verify with expiry, attempt limit, resend cooldown and rate limit."""
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app

from .. import db
from ..security import sha256_hash


def _hash_code(code):
    return sha256_hash(code, "otp:")


def normalize_phone(raw):
    digits = str(raw).translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    )
    digits = "".join(ch for ch in digits if ch.isdigit())
    if digits.startswith("98") and len(digits) == 12:
        digits = "0" + digits[2:]
    if digits.startswith("9") and len(digits) == 10:
        digits = "0" + digits
    if len(digits) != 11 or not digits.startswith("09") or not digits.isdigit():
        return None
    return digits


def issue_otp(phone):
    """Create an OTP respecting rate limits.

    Returns (ok, error_or_code). In DEV_MODE the plain code is returned so it
    can be shown in the UI (development mechanism only); in production it is
    only sent over SMS.
    """
    cfg = current_app.config
    conn = db.get_db()
    now = datetime.now(timezone.utc)

    with db.immediate_tx(conn):
        recent = conn.execute(
            "SELECT created_at FROM otp_codes WHERE phone=? AND created_at > ? "
            "ORDER BY created_at DESC",
            (phone, (now - timedelta(seconds=cfg["OTP_SEND_WINDOW_SECONDS"])).isoformat()),
        ).fetchall()
        if len(recent) >= cfg["OTP_MAX_SENDS_PER_WINDOW"]:
            return False, "تعداد درخواست کد بیش از حد مجاز است. بعداً تلاش کنید."
        if recent:
            last = datetime.fromisoformat(recent[0]["created_at"].replace("Z", "+00:00"))
            elapsed = (now - last).total_seconds()
            if elapsed < cfg["OTP_RESEND_COOLDOWN"]:
                wait = int(cfg["OTP_RESEND_COOLDOWN"] - (now - last).total_seconds())
                return False, f"برای درخواست مجدد {wait} ثانیه صبر کنید."

        code = f"{int.from_bytes(secrets.token_bytes(4), 'big') % 1000000:06d}"
        expires = (now + timedelta(seconds=cfg["OTP_TTL_SECONDS"])).isoformat()
        conn.execute(
            "INSERT INTO otp_codes(phone, code_hash, expires_at) VALUES (?,?,?)",
            (phone, _hash_code(code), expires),
        )
        conn.execute(
            "DELETE FROM otp_codes WHERE created_at < ?",
            ((now - timedelta(hours=1)).isoformat(),),
        )

    _send_sms(phone, code)
    return True, (code if cfg["DEV_MODE"] else None)


def _send_sms(phone, code):
    from .sms import get_sms_provider
    # Never log the code in production logging; ConsoleSms prints it only in DEV.
    get_sms_provider(current_app.config).send_otp(phone, f"کد تأیید شما: {code}")


def verify_otp(phone, code):
    """Return (ok, error). Marks code used on success, counts attempts otherwise."""
    cfg = current_app.config
    conn = db.get_db()
    now = datetime.now(timezone.utc)
    code = str(code).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")).strip()
    with db.immediate_tx(conn):
        row = conn.execute(
            "SELECT * FROM otp_codes WHERE phone=? AND used=0 AND expires_at > ? "
            "ORDER BY id DESC LIMIT 1",
            (phone, now.isoformat()),
        ).fetchone()
        if row is None:
            return False, "کد منقضی یا نامعتبر است. کد جدید بگیرید."
        if row["attempts"] >= cfg["OTP_MAX_ATTEMPTS"]:
            return False, "تعداد تلاش‌ها بیش از حد مجاز است. کد جدید بگیرید."
        if not hmac.compare_digest(_hash_code(code), row["code_hash"]):
            conn.execute(
                "UPDATE otp_codes SET attempts=attempts+1 WHERE id=?", (row["id"],)
            )
            remaining = max(cfg["OTP_MAX_ATTEMPTS"] - row["attempts"] - 1, 0)
            return False, f"کد نادرست است. {remaining} تلاش باقی مانده."
        conn.execute("UPDATE otp_codes SET used=1 WHERE id=?", (row["id"],))
    return True, None
