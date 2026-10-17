"""Gregorian -> Jalali conversion (display only) and Persian helpers."""
import datetime

MONTH_NAMES = [
    "", "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]
# Python date.weekday(): Mon=0 ... Sun=6 ; Persian week starts Saturday
WEEKDAY_NAMES = {
    5: "شنبه", 6: "یکشنبه", 0: "دوشنبه", 1: "سه‌شنبه",
    2: "چهارشنبه", 3: "پنجشنبه", 4: "جمعه",
}
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + \
        ((gy2 + 399) // 400) - 80 + gd + g_d_m[gm - 1]
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def fa_num(value):
    return str(value).translate(FA_DIGITS)


def format_date_fa(iso_date):
    """iso_date: 'YYYY-MM-DD' (Gregorian) -> 'شنبه ۱۲ مهر ۱۴۰۵'"""
    d = datetime.date.fromisoformat(iso_date)
    jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
    return "%s %s %s %s" % (
        WEEKDAY_NAMES[d.weekday()], fa_num(jd), MONTH_NAMES[jm], fa_num(jy)
    )


def format_time_fa(hhmm):
    h, m = hhmm.split(":")
    return "%s:%s" % (fa_num(h), fa_num(m))


def format_money(amount):
    return fa_num(f"{amount:,}")
