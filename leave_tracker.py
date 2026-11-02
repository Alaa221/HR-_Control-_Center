"""Persistent leave records and balance calculations."""
from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import math
import re
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Generator

import pandas as pd

from att_config import HOLIDAYS, SETTINGS
import local_time

DB_FILE = Path(__file__).parent / "data" / "hr_leaves.sqlite3"
VACATION_FILE = Path(__file__).parent / "Vacations_2026.xlsx"
VACATION_SHEET = "Records"
_IMPORT_MANAGER = "Import Vacations_2026.xlsx"
_IMPORT_NOTES = "Imported from Vacations_2026.xlsx"
_VACATION_IMPORT_VERSION = "3"
_SQLITE_TIMEOUT_SECONDS = 30
_SCHEMA_LOCK = Lock()
_SCHEMA_PATH: str | None = None

LEAVE_TYPES = {
    "A": "annual",
    "C": "casual",
    "DE": "bereavement",
    "V": "no_fingerprint",
    "W": "marriage",
    "S": "sick",
    "P": "official",
    "OFF": "weekly_rest",
    "MI": "maternity",
    "M": "mission",
    "D": "unpaid",
    "ADA": "extra_leave",
    "AD": "extra_paid",
    "PERM": "permission",
}
_REST_DAY_WORDS = [
    ("الاثنين", 0), ("الإثنين", 0), ("الثلاثاء", 1), ("الاربعاء", 2),
    ("الأربعاء", 2), ("الخميس", 3), ("الجمعة", 4), ("السبت", 5),
    ("الاحد", 6), ("الأحد", 6),
]


def rest_days(work_group, fallback=None) -> set[int]:
    text = str(work_group or "")
    days = {day for word, day in _REST_DAY_WORDS if word in text}
    return days or set(fallback or {4, 5})


def sick_rest_days(employee: dict) -> set[int]:
    if str(employee.get("department") or "").strip() == "خدمة العملاء":
        return {4}
    return rest_days(employee.get("work_group"), SETTINGS.get("weekend_default", {4, 5}))


def sick_leave_end_date(employee: dict, leave_date: dt.date, days: float) -> dt.date:
    remaining = math.ceil(days)
    rest = sick_rest_days(employee)
    end_date = leave_date
    while remaining:
        if end_date.weekday() not in rest and end_date.isoformat() not in HOLIDAYS:
            remaining -= 1
        if remaining:
            end_date += dt.timedelta(days=1)
    return end_date


def _normalized_end_date(employee: dict, leave_code: str, leave_date: dt.date,
                         end_date: dt.date, days: float) -> dt.date:
    if leave_code == "S" and math.isfinite(days) and days > 0:
        return sick_leave_end_date(employee, leave_date, days)
    return end_date


@contextmanager
def _connection(path: Path) -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(path, timeout=_SQLITE_TIMEOUT_SECONDS)
    conn.execute(f"PRAGMA busy_timeout = {_SQLITE_TIMEOUT_SECONDS * 1000}")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_schema(path: Path) -> None:
    global _SCHEMA_PATH
    resolved = str(path.resolve())
    if _SCHEMA_PATH == resolved:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_PATH == resolved:
            return
        with _connection(path) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leave_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    leave_code TEXT NOT NULL,
                    leave_date TEXT NOT NULL,
                    end_date TEXT NOT NULL DEFAULT '',
                    days REAL NOT NULL DEFAULT 0,
                    hours REAL NOT NULL DEFAULT 0,
                    manager_name TEXT NOT NULL DEFAULT '',
                    manager_approved INTEGER NOT NULL DEFAULT 0,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(leave_entries)")}
            if "end_date" not in columns:
                conn.execute("ALTER TABLE leave_entries ADD COLUMN end_date TEXT NOT NULL DEFAULT ''")
                conn.execute("UPDATE leave_entries SET end_date = leave_date WHERE end_date = ''")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS employee_leave_policy (
                    code TEXT PRIMARY KEY,
                    weekend_comp TEXT NOT NULL DEFAULT '',
                    season_comp TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leave_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    leave_code TEXT NOT NULL,
                    leave_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    days REAL NOT NULL DEFAULT 0,
                    hours REAL NOT NULL DEFAULT 0,
                    manager_email TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    approval_token_hash TEXT,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leave_source_sync (
                    source TEXT PRIMARY KEY,
                    signature TEXT NOT NULL,
                    synced_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leave_source_balance (
                    code TEXT PRIMARY KEY,
                    year INTEGER NOT NULL,
                    annual_entitlement REAL,
                    annual_used REAL,
                    casual_entitlement REAL,
                    casual_used REAL,
                    extra_leave REAL
                )
            """)
        _SCHEMA_PATH = resolved


@contextmanager
def connect() -> Generator[sqlite3.Connection, None, None]:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    path = DB_FILE
    _ensure_schema(path)
    conn = sqlite3.connect(path, timeout=_SQLITE_TIMEOUT_SECONDS)
    conn.execute(f"PRAGMA busy_timeout = {_SQLITE_TIMEOUT_SECONDS * 1000}")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _as_date(value) -> dt.date | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (dt.datetime, pd.Timestamp)):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return pd.Timestamp(value).date()


def _sheet_date(value) -> dt.date | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (dt.datetime, pd.Timestamp)):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, (int, float)) and 25000 <= value <= 70000:
        return (dt.datetime(1899, 12, 30) + dt.timedelta(days=float(value))).date()
    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def _permission_date(value, year: int) -> dt.date | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (dt.datetime, pd.Timestamp, dt.date)):
        return value.date() if isinstance(value, (dt.datetime, pd.Timestamp)) else value
    text = str(value).strip()
    day_month = re.fullmatch(r"(\d{1,2})[-/](\d{1,2})", text)
    if day_month:
        day, month = map(int, day_month.groups())
        try:
            return dt.date(year, month, day)
        except ValueError:
            return None
    return _sheet_date(value)


def _vacation_sheet_entries() -> tuple[
    list[tuple[str, str, str, str, float, float, str, int, str]],
    list[tuple[str, int, float | None, float | None, float | None, float | None, float | None]],
]:
    sheet = pd.read_excel(VACATION_FILE, sheet_name=VACATION_SHEET, header=None, dtype=object)
    if len(sheet.index) < 5 or len(sheet.columns) < 5:
        raise ValueError(f"ورقة {VACATION_SHEET} لا تحتوي على بيانات إجازات صالحة.")

    date_columns: list[tuple[int, dt.date]] = []
    for column in range(4, len(sheet.columns)):
        date = _sheet_date(sheet.iat[3, column])
        if date is None:
            if date_columns:
                break
            continue
        if date_columns and date != date_columns[-1][1] + dt.timedelta(days=1):
            break
        date_columns.append((column, date))
    if not date_columns:
        raise ValueError(f"لم يتم العثور على تواريخ يومية متتابعة في ورقة {VACATION_SHEET}.")

    def normalized_header(value) -> str:
        text = str(value or "").strip().lower()
        return text.translate(str.maketrans({
            "أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه",
        }))

    month_names = {
        "يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "مايو": 5,
        "يونيه": 6, "يونيو": 6, "يوليو": 7, "اغسطس": 8, "سبتمبر": 9,
        "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
    }
    balance_years = [
        int(year)
        for value in sheet.iloc[3].tolist()
        for year in re.findall(r"\b20\d{2}\b", str(value))
    ]
    balance_year = max(balance_years, default=local_time.today().year)
    year_token = str(balance_year)
    balance_columns: dict[str, int] = {}
    permission_columns: list[int] = []
    for column, value in enumerate(sheet.iloc[3].tolist()):
        header = normalized_header(value)
        if "اذن" in header:
            month = next((number for name, number in month_names.items() if name in header), None)
            if month is not None and ("اول" in header or "ثان" in header):
                permission_columns.append(column)
        if year_token in header and "رصيد" in header:
            if "سنوي" in header and "مستنفذ" not in header:
                balance_columns["annual_entitlement"] = column
            elif "سنوي" in header and "مستنفذ" in header:
                balance_columns["annual_used"] = column
            elif "عارضه" in header and "مستنفذ" not in header:
                balance_columns["casual_entitlement"] = column
            elif "عارضه" in header and "مستنفذ" in header:
                balance_columns["casual_used"] = column
        elif "ايام العمل" in header and "الاضافيه" in header and "رصيد الاجازات" in header:
            balance_columns["extra_leave"] = column

    def cell_number(row_index: int, field: str) -> float | None:
        column = balance_columns.get(field)
        if column is None:
            return None
        value = pd.to_numeric(sheet.iat[row_index, column], errors="coerce")
        return float(value) if pd.notna(value) else None

    imported: list[tuple[str, str, str, str, float, float, str, int, str]] = []
    balances: list[
        tuple[str, int, float | None, float | None, float | None, float | None, float | None]
    ] = []
    unknown_codes: set[str] = set()
    for row_index in range(4, len(sheet.index)):
        raw_code = sheet.iat[row_index, 0]
        if raw_code is None or pd.isna(raw_code) or not str(raw_code).strip():
            continue
        code = str(int(raw_code)) if isinstance(raw_code, (int, float)) and float(raw_code).is_integer() else str(raw_code).strip()
        balances.append((
            code, balance_year, cell_number(row_index, "annual_entitlement"),
            cell_number(row_index, "annual_used"), cell_number(row_index, "casual_entitlement"),
            cell_number(row_index, "casual_used"), cell_number(row_index, "extra_leave"),
        ))
        for column, leave_date in date_columns:
            raw_leave_code = sheet.iat[row_index, column]
            if raw_leave_code is None or pd.isna(raw_leave_code) or not str(raw_leave_code).strip():
                continue
            leave_code = str(raw_leave_code).strip().upper()
            if leave_code == "ML":
                leave_code = "MI"
            if leave_code not in LEAVE_TYPES:
                unknown_codes.add(leave_code)
                continue
            date_text = leave_date.isoformat()
            imported.append((
                code, leave_code, date_text, date_text, 1.0, 0.0,
                _IMPORT_MANAGER, 1, _IMPORT_NOTES,
            ))
        for column in permission_columns:
            raw_permission_date = sheet.iat[row_index, column]
            if raw_permission_date is None or pd.isna(raw_permission_date) or not str(raw_permission_date).strip():
                continue
            permission_date = _permission_date(raw_permission_date, balance_year)
            if permission_date is None:
                raise ValueError(
                    f"تاريخ إذن غير صالح في عمود {str(sheet.iat[3, column]).strip()}."
                )
            date_text = permission_date.isoformat()
            imported.append((
                code, "PERM", date_text, date_text, 0.0, 2.0,
                _IMPORT_MANAGER, 1, _IMPORT_NOTES,
            ))
    if unknown_codes:
        raise ValueError(
            f"أكواد إجازات غير معروفة في ورقة {VACATION_SHEET}: "
            + ", ".join(sorted(unknown_codes))
        )
    if not imported:
        raise ValueError(f"لم يتم العثور على حركات إجازات في ورقة {VACATION_SHEET}.")
    return imported, balances


def sync_vacation_sheet() -> None:
    """Refresh imported leave-day entries when the source workbook changes."""
    stat = VACATION_FILE.stat()
    signature = f"v{_VACATION_IMPORT_VERSION}:{stat.st_size}:{stat.st_mtime_ns}"
    source = str(VACATION_FILE.resolve())
    with connect() as conn:
        row = conn.execute(
            "SELECT signature FROM leave_source_sync WHERE source = ?", (source,)
        ).fetchone()
        if row and row["signature"] == signature:
            return

    imported, balances = _vacation_sheet_entries()
    if VACATION_FILE.stat().st_size != stat.st_size or VACATION_FILE.stat().st_mtime_ns != stat.st_mtime_ns:
        raise RuntimeError("تم تعديل ملف الإجازات أثناء قراءته؛ أعيدي المحاولة.")

    with connect() as conn:
        conn.execute(
            "DELETE FROM leave_entries WHERE manager_name = ? AND notes = ?",
            (_IMPORT_MANAGER, _IMPORT_NOTES),
        )
        conn.executemany(
            """INSERT INTO leave_entries
               (code, leave_code, leave_date, end_date, days, hours, manager_name,
                manager_approved, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(*entry, local_time.now_naive().isoformat(timespec="seconds")) for entry in imported],
        )
        conn.execute("DELETE FROM leave_source_balance")
        conn.executemany(
            """INSERT INTO leave_source_balance
               (code, year, annual_entitlement, annual_used, casual_entitlement, casual_used, extra_leave)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            balances,
        )
        conn.execute(
            """INSERT INTO leave_source_sync (source, signature, synced_at)
               VALUES (?, ?, ?)
               ON CONFLICT(source) DO UPDATE SET signature=excluded.signature,
               synced_at=excluded.synced_at""",
            (source, signature, local_time.now_naive().isoformat(timespec="seconds")),
        )


def _completed_months(start: dt.date | None, end: dt.date) -> int:
    if start is None or start > end:
        return 0
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day < start.day:
        months -= 1
    return max(0, months)


def _add_months(date: dt.date, months: int) -> dt.date:
    month_index = date.month - 1 + months
    year = date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(date.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def _age_on(birth_date: dt.date | None, on_date: dt.date) -> int | None:
    if birth_date is None:
        return None
    return on_date.year - birth_date.year - (
        (on_date.month, on_date.day) < (birth_date.month, birth_date.day)
    )


def balance(employee: dict, entries: list[dict], today: dt.date | None = None,
            source_balance: dict | None = None) -> dict:
    today = today or local_time.today()
    hire_date = _as_date(employee.get("hire_date"))
    birth_date = _as_date(employee.get("birth_date"))
    insurance_start = _as_date(employee.get("ins_start"))
    months = _completed_months(hire_date, today)
    years: dict[int, dict[str, float | int]] = {}
    first_year_earned = 0.0

    if hire_date is not None:
        for month_number in range(months):
            earning_date = _add_months(hire_date, month_number + 1)
            service_months = month_number + 1
            insured_months = _completed_months(insurance_start, earning_date)
            age = _age_on(birth_date, earning_date)
            total_days = 15 if service_months <= 12 else (
                30 if service_months > 120 or insured_months >= 120 or (age is not None and age > 50) else 21
            )
            bucket = years.setdefault(earning_date.year, {
                "year": earning_date.year, "casual_earned": 0.0, "annual_earned": 0.0,
                "casual_used": 0.0, "annual_used": 0.0, "extra_leave": 0.0,
            })
            casual_monthly = 7 / 12
            annual_monthly = (total_days - 7) / 12
            bucket["casual_earned"] += casual_monthly
            bucket["annual_earned"] += annual_monthly
            if service_months <= 12:
                first_year_earned += casual_monthly + annual_monthly

    sick_3y = 0.0
    permissions_month: dict[str, int] = {}
    for entry in entries:
        code = entry["leave_code"]
        date = dt.date.fromisoformat(entry["leave_date"])
        days = float(entry["days"])
        bucket = years.setdefault(date.year, {
            "year": date.year, "casual_earned": 0.0, "annual_earned": 0.0,
            "casual_used": 0.0, "annual_used": 0.0, "extra_leave": 0.0,
        })
        if code == "C":
            bucket["casual_used"] += days
        elif code == "A":
            bucket["annual_used"] += days
        elif code == "ADA":
            bucket["extra_leave"] += days
        elif code == "S" and _three_years_ago(today) <= date <= today:
            sick_3y += days
        elif code == "PERM" and date.year == today.year and date.month == today.month:
            permissions_month[entry["leave_date"][:7]] = permissions_month.get(entry["leave_date"][:7], 0) + 1

    available = months >= 3
    current_year = years.setdefault(today.year, {
        "year": today.year, "casual_earned": 0.0, "annual_earned": 0.0,
        "casual_used": 0.0, "annual_used": 0.0, "extra_leave": 0.0,
    })
    if source_balance and source_balance["year"] == today.year:
        manual = {"A": 0.0, "C": 0.0, "ADA": 0.0}
        imported_used = {"A": 0.0, "C": 0.0}
        for entry in entries:
            is_imported = (
                entry["manager_name"] == _IMPORT_MANAGER
                and entry["notes"] == _IMPORT_NOTES
            )
            if dt.date.fromisoformat(entry["leave_date"]).year != today.year:
                continue
            code = entry["leave_code"]
            if is_imported:
                if code in imported_used:
                    imported_used[code] += float(entry["days"])
            elif code in manual:
                manual[code] += float(entry["days"])
        if source_balance["annual_entitlement"] is not None:
            current_year["annual_earned"] = float(source_balance["annual_entitlement"])
        if source_balance["casual_entitlement"] is not None:
            current_year["casual_earned"] = float(source_balance["casual_entitlement"])
        if source_balance["annual_used"] is not None:
            current_year["annual_used"] = imported_used["A"] + manual["A"]
        if source_balance["casual_used"] is not None:
            current_year["casual_used"] = imported_used["C"] + manual["C"]
        if source_balance["extra_leave"] is not None:
            current_year["extra_leave"] = float(source_balance["extra_leave"]) + manual["ADA"]
    casual_earned = float(current_year["casual_earned"])
    annual_earned = float(current_year["annual_earned"])
    casual_used = float(current_year["casual_used"])
    annual_used = float(current_year["annual_used"])
    extra_leave = float(current_year["extra_leave"])
    casual_balance = max(0.0, casual_earned - casual_used) if available else 0.0
    annual_balance = max(0.0, annual_earned + extra_leave - annual_used) if available else 0.0
    eligibility_date = _add_months(hire_date, 3) if hire_date else today
    yearly_balances = []
    for year in sorted(years, reverse=True):
        bucket = years[year]
        year_casual_earned = float(bucket["casual_earned"])
        year_annual_earned = float(bucket["annual_earned"])
        year_casual_used = float(bucket["casual_used"])
        year_annual_used = float(bucket["annual_used"])
        year_extra_leave = float(bucket["extra_leave"])
        yearly_balances.append({
            "year": year,
            "casual_earned": round(year_casual_earned, 2),
            "annual_earned": round(year_annual_earned + year_extra_leave, 2),
            "entitlement_total": round(year_casual_earned + year_annual_earned + year_extra_leave, 2),
            "casual_used": round(year_casual_used, 2),
            "annual_used": round(year_annual_used, 2),
            "casual_balance": round(max(0.0, year_casual_earned - year_casual_used), 2),
            "annual_balance": round(max(0.0, year_annual_earned + year_extra_leave - year_annual_used), 2),
            "total_balance": round(
                max(0.0, year_casual_earned - year_casual_used)
                + max(0.0, year_annual_earned + year_extra_leave - year_annual_used), 2
            ),
            "current": year == today.year,
            "available": year == today.year and available,
            "expired": year < today.year,
        })
    return {
        "current_year": today.year,
        "yearly_balances": yearly_balances,
        "service_months": months,
        "entitlement_total": round(casual_earned + annual_earned + extra_leave, 2),
        "casual_earned": round(casual_earned, 2),
        "annual_earned": round(annual_earned, 2),
        "casual_used": round(casual_used, 2),
        "annual_used": round(annual_used, 2),
        "casual_balance": round(casual_balance, 2),
        "annual_balance": round(annual_balance, 2),
        "total_balance": round(casual_balance + annual_balance, 2),
        "available": available,
        "waiting_days": max(0, (eligibility_date - today).days) if hire_date and not available else 0,
        "first_year_remaining": round(max(0.0, 15 - first_year_earned), 2) if months < 12 else 0.0,
        "sick_used_3y": round(sick_3y, 2),
        "sick_remaining_3y": round(max(0.0, 90 - sick_3y), 2),
        "permissions_used": permissions_month.get(today.strftime("%Y-%m"), 0),
        "permissions_remaining": max(0, 2 - permissions_month.get(today.strftime("%Y-%m"), 0)),
    }


def _three_years_ago(date: dt.date) -> dt.date:
    try:
        return date.replace(year=date.year - 3)
    except ValueError:
        return date.replace(year=date.year - 3, day=28)


def entries_for(code: str) -> list[dict]:
    sync_vacation_sheet()
    with connect() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM leave_entries WHERE code = ? ORDER BY leave_date DESC, id DESC", (code,)
        )]


def all_entries() -> list[dict]:
    sync_vacation_sheet()
    with connect() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM leave_entries ORDER BY leave_date DESC, id DESC"
        )]


def source_balances() -> dict[str, dict]:
    sync_vacation_sheet()
    with connect() as conn:
        return {
            row["code"]: dict(row)
            for row in conn.execute("SELECT * FROM leave_source_balance")
        }


def requests_for(code: str) -> list[dict]:
    with connect() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM leave_requests WHERE code = ? ORDER BY created_at DESC, id DESC",
            (code,),
        )]


def request_by_id(request_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM leave_requests WHERE id = ?", (request_id,)).fetchone()
        return dict(row) if row else None


def request_by_token(token: str) -> dict | None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with connect() as conn:
        row = conn.execute(
            """SELECT * FROM leave_requests
               WHERE approval_token_hash = ? AND status = 'pending'""",
            (token_hash,),
        ).fetchone()
        return dict(row) if row else None


def policies() -> dict[str, dict]:
    with connect() as conn:
        return {row["code"]: dict(row) for row in conn.execute("SELECT * FROM employee_leave_policy")}


def save_policy(code: str, weekend_comp: str, season_comp: str) -> None:
    if weekend_comp not in ("money", "leave", "") or season_comp not in ("money", "leave", ""):
        raise ValueError("اختيار غير صالح لطريقة التعويض.")
    with connect() as conn:
        conn.execute(
            """INSERT INTO employee_leave_policy (code, weekend_comp, season_comp, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(code) DO UPDATE SET weekend_comp=excluded.weekend_comp,
               season_comp=excluded.season_comp, updated_at=excluded.updated_at""",
            (code, weekend_comp, season_comp, local_time.now_naive().isoformat(timespec="seconds")),
        )


def _entry_plan(conn: sqlite3.Connection, employee: dict, leave_code: str,
                leave_date: dt.date, end_date: dt.date, days: float, hours: float,
                manager_name: str, manager_approved: bool, notes: str,
                allow_pending: bool = False) -> list[tuple[str, float, str]]:
    code = str(employee["code"])
    if leave_code not in LEAVE_TYPES:
        raise ValueError("نوع الإجازة غير معروف.")
    if not math.isfinite(days) or not math.isfinite(hours) or days < 0 or hours < 0 or days == 0 and hours == 0:
        raise ValueError("أدخلي عدد أيام أو ساعات صحيحًا.")
    if end_date < leave_date:
        raise ValueError("تاريخ النهاية يجب أن يكون بعد تاريخ البداية أو مساويًا له.")
    if leave_code in ("A", "C", "ADA") and leave_date.year != end_date.year:
        raise ValueError("سجل الإجازات ذات الرصيد بشكل منفصل لكل سنة ميلادية.")
    if hours and leave_code not in ("M", "PERM"):
        raise ValueError("تُسجل الساعات للمأموريات والأذونات فقط.")
    if leave_code == "PERM" and (hours > 2 or days != 0):
        raise ValueError("الإذن لا يتجاوز ساعتين، ويسجل بالساعات فقط.")
    if leave_code == "PERM" and end_date != leave_date:
        raise ValueError("الإذن يُسجل في يوم واحد.")
    if leave_code == "M" and hours > 0:
        days = 0
    if leave_code in ("A", "C", "D", "DE", "W", "S", "MI") and days:
        calendar_days_in_range = (end_date - leave_date).days + 1
        if days > calendar_days_in_range:
            raise ValueError("عدد أيام الإجازة أكبر من الفترة المحددة.")
    limits = {"DE": 3, "W": 14, "MI": 120}
    if leave_code in limits and (hours != 0 or days > limits[leave_code]):
        raise ValueError(f"الحد الأقصى لهذا النوع هو {limits[leave_code]} يومًا.")
    employee_entries = [dict(row) for row in conn.execute(
        "SELECT * FROM leave_entries WHERE code = ?", (code,)
    )]
    balance_row = conn.execute(
        "SELECT * FROM leave_source_balance WHERE code = ?", (code,)
    ).fetchone()
    current_balance = balance(
        employee, employee_entries, today=leave_date,
        source_balance=dict(balance_row) if balance_row else None,
    )
    early_approved = leave_code in ("A", "C") and not current_balance["available"]
    if early_approved:
        if not manager_approved or not notes.strip():
            raise ValueError(
                "قبل إتمام 3 شهور، اكتبي سبب الإجازة في الملاحظات وحددي أن المدير وافق عليها."
            )
        notes = f"[اعتماد المدير: إجازة قبل إتمام 3 شهور] {notes.strip()}"
    if leave_code == "A" and not early_approved and days > current_balance["annual_balance"]:
        raise ValueError("رصيد الاعتيادي غير كافٍ.")
    if leave_code == "C":
        casual_left = current_balance["casual_balance"]
        if days > casual_left and not early_approved:
            overflow = days - casual_left
            if not allow_pending and (not manager_approved or not manager_name.strip()):
                raise ValueError("الرصيد العارض غير كافٍ؛ يلزم اعتماد المدير وتوقيعه لتحويل الزيادة إلى اعتيادي.")
            if overflow > current_balance["annual_balance"]:
                raise ValueError("الرصيد العارض غير كافٍ، ورصيد الاعتيادي لا يكفي لتغطية الزيادة.")
            if casual_left:
                return [
                    ("C", casual_left, notes.strip()),
                    ("A", overflow, f"تحويل من عارضة بموافقة المدير. {notes.strip()}".strip()),
                ]
            return [("A", overflow, f"تحويل من عارضة بموافقة المدير. {notes.strip()}".strip())]
    if leave_code == "PERM":
        daily_hours = sum(
            float(entry["hours"]) for entry in employee_entries
            if entry["leave_code"] == "PERM" and entry["leave_date"] == leave_date.isoformat()
        )
        if daily_hours + hours > 2:
            raise ValueError("إجمالي ساعات الأذونات في اليوم الواحد لا يتجاوز ساعتين.")
        permissions = sum(
            1 for entry in employee_entries
            if entry["leave_code"] == "PERM"
            and entry["leave_date"][:7] == leave_date.strftime("%Y-%m")
        )
        if permissions >= 2:
            raise ValueError("تم تسجيل الإذنين المسموح بهما لهذا الشهر.")
    if leave_code == "S" and days > current_balance["sick_remaining_3y"]:
        unpaid_days = days - current_balance["sick_remaining_3y"]
        notes = f"{notes.strip()} [تنبيه: {unpaid_days:g} يوم يتجاوز حد المرضي المدفوع ويُراجع للخصم من الراتب]".strip()
    return [(leave_code, days, notes.strip())]


def _insert_entry_plan(conn: sqlite3.Connection, code: str, leave_date: dt.date,
                       end_date: dt.date, hours: float, manager_name: str,
                       manager_approved: bool,
                       entries: list[tuple[str, float, str]]) -> None:
    created_at = local_time.now_naive().isoformat(timespec="seconds")
    for leave_code, days, notes in entries:
        conn.execute(
            """INSERT INTO leave_entries
               (code, leave_code, leave_date, end_date, days, hours, manager_name, manager_approved, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, leave_code, leave_date.isoformat(), end_date.isoformat(), days, hours, manager_name.strip(),
             int(manager_approved), notes, created_at),
        )


def add_entry(employee: dict, leave_code: str, leave_date: dt.date, end_date: dt.date,
              days: float, hours: float,
              manager_name: str = "", manager_approved: bool = False, notes: str = "") -> None:
    sync_vacation_sheet()
    end_date = _normalized_end_date(employee, leave_code, leave_date, end_date, days)
    with connect() as conn:
        plan = _entry_plan(conn, employee, leave_code, leave_date, end_date, days, hours,
                           manager_name, manager_approved, notes)
        _insert_entry_plan(conn, str(employee["code"]), leave_date, end_date, hours,
                           manager_name, manager_approved, plan)


def update_entry(entry_id: int, employee: dict, leave_code: str,
                 leave_date: dt.date, end_date: dt.date, days: float, hours: float,
                 manager_name: str = "", manager_approved: bool = False,
                 notes: str = "") -> None:
    sync_vacation_sheet()
    code = str(employee["code"])
    with connect() as conn:
        current = conn.execute(
            "SELECT * FROM leave_entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if current is None or current["code"] != code:
            raise ValueError("الحركة غير موجودة لهذا الموظف.")
        conn.execute("DELETE FROM leave_entries WHERE id = ?", (entry_id,))
        end_date = _normalized_end_date(employee, leave_code, leave_date, end_date, days)
        plan = _entry_plan(
            conn, employee, leave_code, leave_date, end_date, days, hours,
            manager_name, manager_approved, notes,
        )
        _insert_entry_plan(
            conn, code, leave_date, end_date, hours, manager_name, manager_approved, plan,
        )


def submit_request(employee: dict, leave_code: str, leave_date: dt.date, end_date: dt.date,
                   days: float, hours: float, manager_email: str, notes: str = "") -> tuple[int, str]:
    code = str(employee["code"])
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    end_date = _normalized_end_date(employee, leave_code, leave_date, end_date, days)
    with connect() as conn:
        _entry_plan(conn, employee, leave_code, leave_date, end_date, days, hours,
                    manager_email, True, notes, allow_pending=True)
        cur = conn.execute(
            """INSERT INTO leave_requests
               (code, leave_code, leave_date, end_date, days, hours, manager_email, notes,
                status, approval_token_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (code, leave_code, leave_date.isoformat(), end_date.isoformat(), days, hours,
             manager_email, notes.strip(), token_hash,
             local_time.now_naive().isoformat(timespec="seconds")),
        )
        return int(cur.lastrowid), token


def refresh_request_token(request_id: int) -> tuple[dict, str] | None:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with connect() as conn:
        cur = conn.execute(
            """UPDATE leave_requests SET approval_token_hash = ?
               WHERE id = ? AND status = 'pending'""",
            (token_hash, request_id),
        )
        if cur.rowcount != 1:
            return None
        row = conn.execute("SELECT * FROM leave_requests WHERE id = ?", (request_id,)).fetchone()
        return dict(row), token


def review_request(token: str, employee: dict, approved: bool) -> dict | None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with connect() as conn:
        row = conn.execute(
            """SELECT * FROM leave_requests
               WHERE approval_token_hash = ? AND status = 'pending'""",
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        request = dict(row)
        if approved:
            leave_date = dt.date.fromisoformat(request["leave_date"])
            end_date = _normalized_end_date(
                employee, request["leave_code"], leave_date,
                dt.date.fromisoformat(request["end_date"]), float(request["days"]),
            )
            days, hours = float(request["days"]), float(request["hours"])
            plan = _entry_plan(
                conn, employee, request["leave_code"], leave_date, end_date, days, hours,
                request["manager_email"], True, request["notes"],
            )
            _insert_entry_plan(
                conn, request["code"], leave_date, end_date, hours,
                request["manager_email"], True, plan,
            )
        status = "approved" if approved else "rejected"
        conn.execute(
            """UPDATE leave_requests SET status = ?, approval_token_hash = NULL, reviewed_at = ?
               WHERE id = ? AND status = 'pending'""",
            (status, local_time.now_naive().isoformat(timespec="seconds"), request["id"]),
        )
        request["status"] = status
        return request


def delete_entry(entry_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM leave_entries WHERE id = ?", (entry_id,))
        return cur.rowcount == 1
