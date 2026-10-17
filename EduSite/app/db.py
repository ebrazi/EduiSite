"""SQLite access layer: schema, per-request connection, IMMEDIATE transactions."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL DEFAULT '',
  owner_relation TEXT,
  grade TEXT,
  goals TEXT NOT NULL DEFAULT '',
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS wallets(
  user_id INTEGER PRIMARY KEY REFERENCES users(id),
  balance INTEGER NOT NULL DEFAULT 0 CHECK(balance >= 0)
);
CREATE TABLE IF NOT EXISTS wallet_txns(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  amount INTEGER NOT NULL,
  balance_after INTEGER NOT NULL,
  kind TEXT NOT NULL,
  ref_type TEXT,
  ref_id INTEGER,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS otp_codes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT NOT NULL,
  code_hash TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  used INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_otp_phone_created ON otp_codes(phone, created_at);
CREATE TABLE IF NOT EXISTS sessions(
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL DEFAULT 'user',
  user_id INTEGER,
  csrf TEXT NOT NULL,
  data TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS availability(
  date TEXT NOT NULL,
  slot_index INTEGER NOT NULL CHECK(slot_index IN (0,1,2)),
  is_active INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (date, slot_index)
);
CREATE TABLE IF NOT EXISTS reservations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  date TEXT NOT NULL,
  slot_index INTEGER NOT NULL CHECK(slot_index IN (0,1,2)),
  price INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN
    ('pending_payment','booked','cancelled_by_user','cancelled_by_teacher','completed')),
  refund_amount INTEGER NOT NULL DEFAULT 0,
  cancel_actor TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  cancelled_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_active_slot
  ON reservations(date, slot_index)
  WHERE status IN ('pending_payment','booked');
CREATE TABLE IF NOT EXISTS payments(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  kind TEXT NOT NULL DEFAULT 'topup',
  amount INTEGER NOT NULL CHECK(amount > 0),
  status TEXT NOT NULL DEFAULT 'initiated'
    CHECK(status IN ('initiated','verified','failed')),
  gateway TEXT NOT NULL DEFAULT 'mock',
  gateway_ref TEXT NOT NULL,
  gateway_tx_id TEXT UNIQUE,
  callback_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS settings(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  details TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TRIGGER IF NOT EXISTS wallet_txns_no_update BEFORE UPDATE ON wallet_txns
BEGIN SELECT RAISE(ABORT, 'wallet_txns is immutable'); END;
CREATE TRIGGER IF NOT EXISTS wallet_txns_no_delete BEFORE DELETE ON wallet_txns
BEGIN SELECT RAISE(ABORT, 'wallet_txns is immutable'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is immutable'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is immutable'); END;
"""


def utcnow_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def connect(db_path):
    conn = sqlite3.connect(db_path, timeout=20, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_schema(db_path):
    conn = sqlite3.connect(db_path, timeout=20)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def get_db():
    from flask import g
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE_PATH"], timeout=15, isolation_level=None
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.execute("PRAGMA busy_timeout=15000")
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def immediate_tx(conn):
    """Serialized write transaction; BEGIN IMMEDIATE prevents writer races."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def audit(conn, actor, action, details=""):
    conn.execute(
        "INSERT INTO audit_log(actor, action, details) VALUES (?,?,?)",
        (actor, action, details),
    )
