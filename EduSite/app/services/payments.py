"""Payment gateway abstraction.

Production replaces MockGateway with a real Iranian gateway adapter; the rest
of the code only talks to the gateway-agnostic helper functions below.
"""
import secrets
from datetime import datetime, timezone

from flask import current_app

from .. import db
from ..security import hmac_sign, constant_eq
from .wallet import apply


def new_gateway_ref():
    return "P" + secrets.token_hex(12)


class MockGateway:
    """DEV ONLY. Registered only when DEV_MODE=1.

    Simulates: success, failure, signed callback, idempotent replays,
    transaction id and verification.
    """

    name = "mock"

    @staticmethod
    def pay_url(payment_id):
        return f"/mock-gateway/pay/{payment_id}"

    @staticmethod
    def sign(payment_id, tx_id, status):
        return hmac_sign(
            current_app.config["MOCK_GATEWAY_SECRET"],
            f"{payment_id}:{tx_id}:{status}",
        )

    @classmethod
    def callback_url(cls, payment_id, tx_id, status):
        sig = cls.sign(payment_id, tx_id, status)
        return (f"/payment/callback?payment_id={payment_id}"
                f"&tx_id={tx_id}&status={status}&sig={sig}")

    @classmethod
    def verify_callback(cls, payment_id, tx_id, status, sig):
        """Returns (ok, reason). Signature check only; state change happens in
        process_callback inside a DB transaction."""
        if not constant_eq(sig, cls.sign(payment_id, tx_id, status)):
            return False, "امضای callback نامعتبر است."
        if status not in ("success", "failed"):
            return False, "وضعیت callback نامعتبر است."
        return True, None


def create_topup_payment(user_id, amount):
    """Create an initiated topup payment row; returns its id."""
    conn = db.get_db()
    with db.immediate_tx(conn):
        cur = conn.execute(
            "INSERT INTO payments(user_id, kind, amount, gateway, gateway_ref) "
            "VALUES (?, 'topup', ?, 'mock', ?)",
            (user_id, amount, new_gateway_ref()),
        )
        return cur.lastrowid


def process_callback(payment_id, tx_id, ok):
    """Idempotent callback processing. Returns (result, already_seen).

    - Only transitions initiated -> verified/failed.
    - Replay on a terminal payment is acknowledged without side effects
      (idempotency; gateway_tx_id UNIQUE is a backstop).
    - Wallet credit and status change happen in ONE transaction.
    """
    conn = db.get_db()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    with db.immediate_tx(conn):
        p = conn.execute(
            "SELECT * FROM payments WHERE id=?", (payment_id,)
        ).fetchone()
        if p is None:
            return "not_found", False
        if p["status"] != "initiated":
            return "already", True
        if ok:
            conn.execute(
                "UPDATE payments SET status='verified', gateway_tx_id=?, "
                "callback_count=callback_count+1, updated_at=? WHERE id=?",
                (tx_id, now, p["id"]),
            )
            apply(conn, p["user_id"], p["amount"], "topup", "payment", p["id"],
                  note=f"شارژ کیف پول ({tx_id})")
            db.audit(conn, "gateway", "payment.verified",
                     f"payment_id={p['id']} amount={p['amount']} tx={tx_id}")
            return "verified", False
        conn.execute(
            "UPDATE payments SET status='failed', gateway_tx_id=?, "
            "callback_count=callback_count+1, updated_at=? WHERE id=?",
            (tx_id, now, p["id"]),
        )
        db.audit(conn, "gateway", "payment.failed",
                 f"payment_id={p['id']} tx={tx_id}")
        return "failed", False
