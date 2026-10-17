# EduSite Session Checkpoint

**Date**: 2026-10-17  
**Branch**: main  
**Status**: Core session/user_id bug fixed; WAL enabled on request connections

## Project Objective and Architecture

**Objective**: Educational session booking platform (کلاس‌یار) for teachers and students with wallet-based payments, OTP verification, and admin management.

**Architecture**: 
- **Backend**: Flask 3.0 with SQLite (WAL mode), minimal dependencies
- **Frontend**: Vanilla Jinja2 templates, RTL Persian CSS, no JS framework
- **Security**: CSRF protection, HttpOnly sessions, OTP rate limiting, immutable wallet transactions
- **Database**: SQLite with IMMEDIATE transactions for concurrency safety
- **Payment**: Mock gateway for development (DEV_MODE=1), production ready for real gateway integration

## Fixes Applied This Session

1. **sessions.user_id column never updated** (root cause of most NoneType test failures)
   - `session_put` only wrote into the JSON `data` field
   - `context_processor` (nav) and `security_user_id` (tests) read the column
   - **Fix**: when key is `user_id`, also UPDATE the column (NULL when cleared)
   - Commit: `0492080`

2. **WAL missing on per-request connections**
   - `connect()` set `journal_mode=WAL`, but `get_db()` did not
   - Concurrent booking race test could fail without WAL + IMMEDIATE
   - **Fix**: `get_db()` now also runs `PRAGMA journal_mode=WAL`
   - Commit: `6e03870`

## Remaining Work / Verify Locally

```bash
cd EduSite
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Expected after these fixes:
- `test_book_success`, cancel tests, IDOR, wallet price, payment callback tests should pass (user_id column populated)
- Race condition test should pass more reliably with WAL
- `test_anonymous_redirected` should still pass (new client has no user_id)
- Top-up success/failure message asserts should pass if callback redirect works

If any test still fails, capture the full traceback and continue from there.

## Known Limitations (unchanged)

- SMS: mock only (ConsoleSms)
- Payment gateway: mock only
- SQLite not for high-traffic production (migrate to PostgreSQL later)
- Default admin password `admin1234` must change in production

## Environment

```bash
DEV_MODE=1
SECRET_KEY=...
ADMIN_PASSWORD=...
SESSION_PRICE=500000
```

---
**Last Updated**: 2026-10-17 (remote continuation)  
**Next Priority**: Run full test suite locally and fix any remaining failures
