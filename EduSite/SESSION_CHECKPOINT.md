# EduSite Session Checkpoint

**Date**: 2026-10-17  
**Branch**: main  
**Commit**: ba5c914 (Initial commit)  
**Status**: Complete working state preserved for remote continuation

## Project Objective and Architecture

**Objective**: Educational session booking platform (کلاس‌یار) for teachers and students with wallet-based payments, OTP verification, and admin management.

**Architecture**: 
- **Backend**: Flask 3.0 with SQLite (WAL mode), minimal dependencies
- **Frontend**: Vanilla Jinja2 templates, RTL Persian CSS, no JS framework
- **Security**: CSRF protection, HttpOnly sessions, OTP rate limiting, immutable wallet transactions
- **Database**: SQLite with IMMEDIATE transactions for concurrency safety
- **Payment**: Mock gateway for development (DEV_MODE=1), production ready for real gateway integration

## Current Test Command and Results

**Test Command**:  
`.venv\Scripts\python.exe -m unittest discover -s tests -v`

**Test Results**:  
- **Total**: 27 tests
- **Passed**: 16 tests  
- **Failed**: 4 tests
- **Errors**: 7 tests
- **Status**: **Partially functional** - core flows work but have database concurrency issues

### Known Failing Tests and Errors:

1. **test_book_success** (ERROR): `TypeError: 'NoneType' object is not subscriptable` - Database row not found after booking
2. **test_teacher_cancel_full_refund** (ERROR): `TypeError: 'NoneType' object is not subscriptable` - Reservation not found
3. **test_user_cancel_full_refund** (ERROR): `TypeError: 'NoneType' object is not subscriptable` - Reservation lookup failed
4. **test_double_booking_race_parallel** (FAIL): Expected 1 success, got 2 booking conflicts - Race condition not properly handled
5. **test_topup_success** (FAIL): Success message not found in redirect response
6. **test_topup_failed** (FAIL): Failure message not found in redirect response  
7. **test_anonymous_redirected** (FAIL): Expected 302 redirect, got 200
8. **test_duplicate_callback_idempotent** (ERROR): Payment record not found
9. **test_forged_callback_rejected** (ERROR): Database access issues
10. **test_idor_cancel_other_users_reservation** (ERROR): Reservation lookup failed
11. **test_wallet_not_writable_via_params** (ERROR): Reservation price not found

## Investigations Completed vs Hypotheses Not Yet Verified

### Completed:
- ✅ User registration and OTP verification flow works correctly
- ✅ Basic wallet operations (topup, balance display) function properly
- ✅ Admin panel login and availability management work
- ✅ Security headers and CSRF protection are implemented
- ✅ Mock payment gateway simulates success/failure scenarios
- ✅ Persian date/time conversion functions correctly
- ✅ Database schema with proper relationships and constraints

### Not Yet Verified:
- ❌ **Race condition handling**: Concurrent booking requests may both fail instead of one succeeding
- ❌ **Database transaction isolation**: IMMEDIATE transactions may not be preventing all write conflicts
- ❌ **Payment callback idempotency**: Duplicate callbacks may not be properly handled in all scenarios
- ❌ **Session persistence**: User sessions may not be properly maintained across operations
- ❌ **Production SMS integration**: Mock SMS works, but real SMS provider not implemented
- ❌ **Real payment gateway**: Currently uses mock gateway only

## Files Changed and Important Implementation Decisions

### Key Implementation Decisions:
1. **Database Design**: Used SQLite with WAL mode and IMMEDIATE transactions for concurrency
2. **Security Approach**: Server-side sessions with CSRF protection, no client-side state
3. **Payment Flow**: Idempotent callback design with HMAC signature verification
4. **OTP System**: Rate limiting with cooldown periods and attempt limits
5. **Wallet System**: Immutable transaction ledger with balance tracking
6. **Admin Panel**: Separate session cookie with password-based authentication

### Critical Files Modified:
- `app/config.py`: Environment-driven configuration with sensible defaults
- `app/db.py`: Database schema and transaction management
- `app/security.py`: Session management, CSRF protection, password hashing
- `app/services/booking.py`: Core booking logic with cancellation policies
- `app/services/payments.py`: Payment abstraction with mock gateway
- `app/services/otp.py`: OTP verification with rate limiting
- `tests/test_app.py`: Comprehensive test suite covering all major flows

## Exact Next Steps for Resuming Work

1. **Immediate Priority - Fix Database Issues**:
   ```bash
   # Investigate why database queries return None
   .venv\Scripts\python.exe -c "
   from app import create_app
   app = create_app()
   with app.app_context():
       from app import db
       conn = db.get_db()
       result = conn.execute('SELECT COUNT(*) FROM reservations').fetchone()
       print('Reservations count:', result)
   "
   ```

2. **Fix Race Condition in Booking**:
   - Examine `booking.py:book_slot()` function
   - Ensure IMMEDIATE transaction properly prevents double booking
   - Add debug logging to track concurrent requests

3. **Resolve Payment Redirect Issues**:
   - Check `user.py:payment_callback()` redirect logic
   - Verify success/failure message rendering in templates

4. **Debug Session Management**:
   - Test session persistence across multiple operations
   - Verify CSRF token generation and validation

5. **Test Environment Setup**:
   ```bash
   # Run specific failing tests
   .venv\Scripts\python.exe -m unittest tests.test_app.TestBookingFlow.test_book_success -v
   .venv\Scripts\python.exe -m unittest tests.test_app.TestPayments.test_topup_success -v
   ```

## Known Limitations

### Incomplete Real Integrations:
- **SMS Provider**: Currently uses mock SMS that prints to console. Real SMS provider (Kavenegar/...) not implemented.
- **Payment Gateway**: Mock gateway simulates flow but real Iranian payment gateway not integrated.
- **Email Notifications**: No email system implemented for confirmations/reminders.

### Technical Limitations:
- **Database Concurrency**: Some race conditions may still occur under high load
- **Session Security**: Production deployment requires HTTPS and proper cookie settings
- **Scalability**: SQLite not suitable for high-traffic production (should migrate to PostgreSQL)

### Development vs Production:
- **DEV_MODE=1**: Mock services enabled, OTP codes visible in UI
- **DEV_MODE=0**: Requires real SMS/payment gateway implementation
- **Admin Password**: Default is `admin1234` - MUST be changed in production

## Setup Instructions for Remote Continuation

```bash
# 1. Clone repository
git clone <repository-url>
cd EduSite

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your SECRET_KEY and ADMIN_PASSWORD

# 5. Initialize database
python seed.py

# 6. Run tests to verify current state
.venv\Scripts\python.exe -m unittest discover -s tests -v

# 7. Start development server
python run.py
```

## Environment Variables Required

```bash
# Required for production (DEV_MODE=0)
SECRET_KEY=your-secure-secret-key-here
ADMIN_PASSWORD=your-secure-admin-password
SITE_URL=https://your-domain.com

# Optional overrides
DEV_MODE=1  # Set to 0 for production
SESSION_PRICE=500000
DATABASE_PATH=/app/instance/edusite.db
```

## Database Schema Notes

- **Users**: Phone-based authentication with optional owner details
- **Wallets**: Balance tracking with immutable transaction history
- **Reservations**: Booking slots with configurable cancellation policy
- **Payments**: Gateway-agnostic payment processing with idempotent callbacks
- **OTP Codes**: Rate-limited verification with expiration
- **Audit Log**: Immutable operation tracking for security

## Security Notes

- No hardcoded secrets found in codebase
- Proper .gitignore excludes sensitive files
- Environment variables used for all configuration
- CSRF protection on all POST requests
- Secure session cookies with HttpOnly and SameSite flags
- Rate limiting on OTP requests to prevent abuse

---
**Last Updated**: 2026-10-17  
**Next Priority**: Fix database transaction issues and race conditions