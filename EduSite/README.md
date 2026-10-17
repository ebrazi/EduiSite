# EduSite — کلاس‌یار

وب‌سایت شخصی برای فروش و رزرو جلسات تدریس. طراحی شده با تمرکز بر سادگی، امنیت و وابستگی‌های حداقل.

## ویژگی‌ها

- **ثبت‌نام مرحله‌ای**: شماره موبایل → OTP پیامکی → نسبت صاحب شماره → مقطع تحصیلی → هدف آموزشی
- **کیف پول داخلی**: شارژ آنلاین (درگاه Mock در توسعه)، پرداخت جلسه از موجودی کیف پول
- **تقویم رزرو**: نمایش بازه‌های زمانی آزاد (۳ بازه پیش‌فرض در روز)
- **پنل مدرس**: فعال/غیرفعال کردن روزها و بازه‌ها، مشاهده رزروها، کنسلی جلسه توسط مدرس
- **سیاست کنسلی قابل تنظیم**: بازرداد ۱۰۰٪ تا ۲۴ ساعت قبل، ۵۰٪ بین ۶ تا ۲۴ ساعت، ۰٪ کمتر از ۶ ساعت
- **امنیت**: CSRF protection، HttpOnly cookies، rate limiting OTP، server-side validation، idempotent payment callbacks
- **SEO-friendly**: semantic HTML، robots.txt، sitemap.xml، Open Graph، canonical URLs
- **RTL، Mobile-first، Responsive**: فونت‌های سیستم (Tahoma/Arial)، بدون فونت خارجی، بدون انیمیشن‌های غیرضروری

## تکنولوژی

- **Python 3.10+**, **Flask 3.0** (minimal dependencies)
- **SQLite** (built-in) with WAL mode, IMMEDIATE transactions
- **Jinja2** templates, vanilla CSS (no JS framework)
- **Waitress** WSGI server for production
- **Docker** containerization

## اجرا در محیط توسعه

### پیش‌نیازها
- Python 3.10+
- pip

### نصب و اجرا
```bash
# 1. کلون مخزن
git clone <repo-url>
cd EduSite

# 2. محیط مجازی
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

# 3. نصب وابستگی‌ها (از میرور علی‌بابا برای سرعت در ایران)
pip install --disable-pip-version-check -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r requirements.txt

# 4. متغیرهای محیطی (کپی و ویرایش)
cp .env.example .env
# در .env مقادیر SECRET_KEY و ADMIN_PASSWORD را تنظیم کنید

# 5. اجرای سرور توسعه
python run.py
# سرور در http://127.0.0.1:5000 بالا می‌آید
```

### حساب‌های پیش‌فرض (بعد از اجرای seed.py)
- **دانش‌آموزان**: ۴ کاربر تستی با شماره‌های 09120000001 تا 09120000004 (موجودی ۱.۵ میلیون تومان)
- **مدرس**: رمز پنل پیش‌فرض `admin1234` (در .env تغییر دهید)

### داده‌های تستی
```bash
.venv\Scripts\python.exe seed.py
```

## اجرا با Docker (تولید)

### پیش‌نیازها
- Docker و Docker Compose

### متغیرهای محیطی (اجباری در تولید)
فایل `.env` را با مقادیر واقعی پر کنید:
```bash
cp .env.example .env
# SECRET_KEY، ADMIN_PASSWORD، SITE_URL را تنظیم کنید
```

### بالا آوردن
```bash
docker compose up -d --build
```
سرویس در پورت 5000 در دسترس است.

### حالت توسعه با Docker
```bash
DEV_MODE=1 docker compose up -d --build
# درگاه Mock و OTP در کنسول نمایش داده می‌شود
```

## تنظیمات قابل تغییر (Environment Variables)

| متغیر | پیش‌فرض | توضیح |
|--------|---------|-------|
| `DEV_MODE` | `1` | در توسعه `1`، در تولید **باید `0` باشد** |
| `SECRET_KEY` | (auto) | کلید امضای سشن/CSRF — در تولید الزامی |
| `ADMIN_PASSWORD` | `admin1234` | رمز پنل مدرس — در تولید تغییر دهید |
| `SITE_URL` | `http://localhost:5000` | آدرس kanonikal سایت |
| `SESSION_PRICE` | `500000` | قیمت هر جلسه (تومان) |
| `TOPUP_AMOUNTS` | `[200000,500000,1000000]` | مبالغ پیش‌فرض شارژ کیف پول |
| `CANCEL_FULL_HOURS` | `24` | ساعت برای بازرداد ۱۰۰٪ |
| `CANCEL_PARTIAL_HOURS` | `6` | ساعت برای بازرداد جزئی |
| `CANCEL_PARTIAL_PERCENT` | `50` | درصد بازرداد جزئی |
| `OTP_TTL_SECONDS` | `120` | انقضای کد OTP |
| `OTP_MAX_ATTEMPTS` | `5` | حداکثر تلاش وارد کردن کد |
| `OTP_MAX_SENDS` | `3` | حداکثر ارسال در پنجره زمانی |
| `OTP_SEND_WINDOW` | `600` | پنجره نرخ‌ محدود کردن ارسال (ثانیه) |
| `OTP_RESEND_COOLDOWN` | `60` | مهلت بین دو ارسال (ثانیه) |
| `SLOT_TIMES` | ۳ بازه پیش‌فرض | بازه‌های زمانی روز |
| `BOOKING_DAYS_AHEAD` | `14` | روزهای قابل رزرو از امروز |

## تست‌ها

```bash
# اجرای تمام تست‌ها
.venv\Scripts\python.exe -m unittest discover -s tests -v

# تست‌های خاص
.venv\Scripts\python.exe -m unittest tests.test_app.TestRegistrationFlow -v
.venv\Scripts\python.exe -m unittest tests.test_app.TestBookingFlow -v
```

**وضعیت تست‌ها**: ۱۷ تست عبور، ۱۷ تست ناموفق (معمولاً به دلیل توکن CSRF در درخواست‌های POST تست‌های امنیتی). جریان‌های اصلی (ثبت‌نام، رزرو، کیف پول، پنل مدرس) تست شده‌اند.

## معماری و اصول طراحی

### کمینه‌سازی وابستگی‌ها
تنها وابستگی‌های خارجی: `Flask`، `Jinja2`، `Werkzeug`، `Waitress`. بدون ORM، بدون فریم‌ورک فرانت‌اند، بدون CDN فونت.

### امنیت
- **CSRF**: توکن در تمام فرم‌های POST، چک سروری
- **سشن**: سمت سرور، کوکی HttpOnly + SameSite=Lax
- **OTP**: انقضا، محدودیت تلاش، نرخ‌ محدود کردن ارسال، مکانیزم توسعه بدون سرویس خارجی
- **پرداخت**: callbackهای idempotent، تراکنش‌های IMMEDIATE، جلوگیری از دو بار پرداخت
- **رزرو**: قفل سطر + UNIQUE جزئی برای جلوگیری از Double Booking
- **کیف پول**: تراکنش‌های immutable، audit log، موجودی در تراکنش واحد

### پایگاه داده
SQLite با WAL mode و `BEGIN IMMEDIATE` برای سریالی‌سازی نویسندگان. جداول:
- `users`, `wallets`, `wallet_txns` (immutable)
- `otp_codes`, `sessions`
- `availability`, `reservations` (UNIQUE جزئی روی اسلات فعال)
- `payments`, `settings`, `audit_log` (immutable)

### تقویم
تبدیل تاریخ میلادی به شمسی (جلالی) با الگوریتم استاندارد، بدون وابستگی خارجی.

## ساختار پروژه

```
EduSite/
├── app/
│   ├── __init__.py          # Factory برنامه
│   ├── config.py            # تنظیمات (env-driven)
│   ├── db.py                # اسکیمای دیتابیس و تراکنش‌ها
│   ├── jalali.py            # تبدیل تاریخ میلادی ↔ شمسی
│   ├── security.py          # هش، HMAC، CSRF، سشن
│   ├── routes/              # بلوپرینت‌ها
│   │   ├── public.py        # صفحات عمومی، robots، sitemap
│   │   ├── auth.py          # ثبت‌نام، OTP، ورود
│   │   ├── user.py          # داشبورد، رزرو، کیف پول
│   │   ├── admin.py         # پنل مدرس
│   │   └── mockgw.py        # درگاه Mock (فقط DEV_MODE)
│   ├── services/            # منطق کسب‌وکار
│   │   ├── otp.py
│   │   ├── sms.py
│   │   ├── wallet.py
│   │   ├── payments.py
│   │   └── booking.py
│   ├── templates/           # قالب‌های RTL فارسی
│   └── static/style.css     # CSS مینیمال
├── tests/test_app.py        # تست‌های یکپارچه (unittest)
├── seed.py                  # داده‌های توسعه
├── run.py                   # نقطه ورود توسعه
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
└── README.md
```

## تولید (Production Checklist)

- [ ] `DEV_MODE=0` در .env
- [ ] `SECRET_KEY` قوی و منحصر به فرد
- [ ] `ADMIN_PASSWORD` پیچیده و منحصر به فرد
- [ ] `SITE_URL` با HTTPS واقعی
- [ ] درگاه پرداخت واقعی جایگزین MockGateway در `services/payments.py`
- [ ] سرویس SMS واقعی در `services/sms.py`
- [ ] HTTPS termination (Nginx/Traefik) یا Load Balancer
- [ ] بک‌آپ منظم فایل دیتابیس (`instance/edusite.db`)

## مجوز

MIT License — استفاده آزاد با حفظ کپی‌رایت.

---

**نکته مهم**: این یک MVP قابل اجرا است. برای تولید واقعی، درگاه پرداخت و سرویس SMS واقعی باید پیاده‌سازی شوند. تست‌های امنیتی جزئی نیاز به تکمیل دارند (مشاهده گزارش تست).