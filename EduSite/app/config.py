"""Central configuration. All values overridable via environment variables."""
import json
import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.abspath(
    os.environ.get("INSTANCE_DIR") or os.path.join(BASE_DIR, "..", "instance")
)

# DEV_MODE: enables Mock SMS / Mock Payment / dev OTP display.
# In production MUST be set to "0" (see README).
DEV_MODE = os.environ.get("DEV_MODE", "1") == "1"

SITE_NAME = os.environ.get("SITE_NAME", "کلاس‌یار")
SITE_URL = os.environ.get("SITE_URL", "http://localhost:5000").rstrip("/")

_db_url = os.environ.get("DATABASE_PATH") or os.path.join(INSTANCE_DIR, "edusite.db")
DATABASE_PATH = _db_url


def get_database_path():
    """Get current database path from environment (for testing)."""
    return os.environ.get("DATABASE_PATH") or os.path.join(INSTANCE_DIR, "edusite.db")


def _secret_key():
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    # Dev convenience: persist a random key under instance/ so sessions survive restarts.
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    path = os.path.join(INSTANCE_DIR, "secret_key")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            key = f.read().strip()
        if key:
            return key
    key = secrets.token_hex(32)
    if not DEV_MODE:
        raise RuntimeError(
            "SECRET_KEY environment variable is required in production."
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write(key)
    return key


SECRET_KEY = _secret_key()

# ---- sessions ----
SESSION_TTL_HOURS = int(os.environ.get("SESSION_TTL_HOURS", "168"))
SESSION_COOKIE_NAME = "sid"
ADMIN_COOKIE_NAME = "asid"

# ---- OTP ----
OTP_TTL_SECONDS = int(os.environ.get("OTP_TTL_SECONDS", "120"))
OTP_MAX_ATTEMPTS = int(os.environ.get("OTP_MAX_ATTEMPTS", "5"))
OTP_MAX_SENDS_PER_WINDOW = int(os.environ.get("OTP_MAX_SENDS", "3"))
OTP_SEND_WINDOW_SECONDS = int(os.environ.get("OTP_SEND_WINDOW", "600"))
OTP_RESEND_COOLDOWN = int(os.environ.get("OTP_RESEND_COOLDOWN", "60"))

# ---- scheduling ----
# Three default slots: (start, end) 24h "HH:MM"
SLOT_TIMES = json.loads(
    os.environ.get(
        "SLOT_TIMES",
        '[["15:30","17:00"],["17:00","18:30"],["18:30","20:00"]]',
    )
)
BOOKING_DAYS_AHEAD = int(os.environ.get("BOOKING_DAYS_AHEAD", "14"))

# ---- money (integer Toman) ----
SESSION_PRICE = int(os.environ.get("SESSION_PRICE", "500000"))
TOPUP_AMOUNTS = json.loads(
    os.environ.get("TOPUP_AMOUNTS", "[200000, 500000, 1000000]")
)

# ---- cancellation policy (configurable, not hard-coded) ----
CANCEL_FULL_HOURS = float(os.environ.get("CANCEL_FULL_HOURS", "24"))
CANCEL_PARTIAL_HOURS = float(os.environ.get("CANCEL_PARTIAL_HOURS", "6"))
CANCEL_PARTIAL_PERCENT = int(os.environ.get("CANCEL_PARTIAL_PERCENT", "50"))

# ---- admin ----
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin1234")  # dev default

# ---- payment (mock gateway, dev only) ----
MOCK_GATEWAY_SECRET = os.environ.get("MOCK_GATEWAY_SECRET", "dev-mock-gateway-secret")

# ---- timezone: Iran Standard Time (no DST since 2022) ----
import datetime as _dt
TZ = _dt.timezone(_dt.timedelta(hours=3, minutes=30), "Asia/Tehran")

RELATION_CHOICES = [
    ("self", "خود دانش‌آموز"),
    ("parent", "پدر / مادر"),
    ("guardian", "خواهر / برادر / سرپرست"),
]
GRADE_CHOICES = ["هفتم", "هشتم", "نهم", "دهم", "یازدهم", "دوازدهم", "کنکوری", "دانشگاهی"]
GOAL_CHOICES = ["تقویتی", "پیشرفته", "المپیاد", "آزمون / کنکور"]


def config_dict():
    """All module-level UPPERCASE constants as a dict for Flask config."""
    return {
        k: v for k, v in globals().items()
        if k.isupper() and not k.startswith("_")
    }
