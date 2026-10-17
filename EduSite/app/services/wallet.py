"""Wallet operations. All mutations happen inside an IMMEDIATE transaction
opened by the caller; every change writes an immutable wallet_txns row."""
from .. import db


class WalletError(Exception):
    pass


def _ensure_wallet(conn, user_id):
    conn.execute(
        "INSERT OR IGNORE INTO wallets(user_id, balance) VALUES (?, 0)", (user_id,)
    )


def get_balance(conn, user_id):
    row = conn.execute(
        "SELECT balance FROM wallets WHERE user_id=?", (user_id,)
    ).fetchone()
    return row["balance"] if row else 0


def apply(conn, user_id, amount, kind, ref_type=None, ref_id=None, note=""):
    """Apply a signed amount to the wallet and record an immutable txn row.

    Must be called inside an open immediate_tx. Raises WalletError on
    insufficient balance (double-spending protection).
    """
    _ensure_wallet(conn, user_id)
    balance = get_balance(conn, user_id)
    new_balance = balance + amount
    if new_balance < 0:
        raise WalletError("موجودی کیف پول کافی نیست.")
    conn.execute(
        "UPDATE wallets SET balance=? WHERE user_id=?", (new_balance, user_id)
    )
    conn.execute(
        "INSERT INTO wallet_txns(user_id, amount, balance_after, kind, ref_type, ref_id, note)"
        " VALUES (?,?,?,?,?,?,?)",
        (user_id, amount, new_balance, kind, ref_type, ref_id, note),
    )
    return new_balance
