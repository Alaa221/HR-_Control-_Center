"""Egypt local clock helpers for date calculations and naive attendance timestamps."""
from datetime import datetime
from datetime import date as Date
from zoneinfo import ZoneInfo

CAIRO = ZoneInfo("Africa/Cairo")


def now() -> datetime:
    return datetime.now(CAIRO)


def now_naive() -> datetime:
    return now().replace(tzinfo=None)


def today() -> Date:
    return now().date()
