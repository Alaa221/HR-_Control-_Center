"""تقرير الحضور والانصراف للموظف عن فترة محددة (نفس شكل شيت الإكسل).

- الحساب (build) بياخد كود موظف + فترة، ويرجّع صفوف اليوم + ملخص الفترة.
- التصدير (to_xlsx) بيرسم نفس الشيت: LTR، عنوان أحمر، مواعيد فعلية/رسمية، الجمعة والسبت أزرق، ولوحة الملخص على اليمين.
- كل الأرقام بالدقايق جوه الحساب، وبتتعرض H:MM.
"""
from __future__ import annotations

import calendar
import datetime as dt
import io
import re

import pandas as pd

import attendance as A
import data as D
import leave_tracker as LT
import local_time
from att_config import HOLIDAYS, SETTINGS as S

# معادلة الاتزان: الرسمي − (الفعلي + الصافي + الغياب + فقدان البصمة + الإجازات والأذونات)
RECON_INCLUDE_NET = True
REPORT_PUNCH_OFFSET = pd.Timedelta(hours=-1)
REPORT_ARRIVAL_ADJUSTMENT_DATE = dt.date(2026, 11, 1)
REPORT_ARRIVAL_ADJUSTMENT = pd.Timedelta(hours=-1)

EN_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_SCHED = re.compile(r"(\d{1,2}):(\d{2})\s*(AM|PM)\s*[:\-–]\s*(\d{1,2}):(\d{2})\s*(AM|PM)", re.I)


def _mins(h: int, m: int, ap: str) -> int:
    h = h % 12 + (12 if ap.upper() == "PM" else 0)
    return h * 60 + m


def parse_schedule(text) -> tuple[int, int] | None:
    """'09:00 AM : 05:00 PM' -> (540, 1020) بالدقايق من بداية اليوم. غير كده -> None (مفيش مواعيد ثابتة)."""
    m = _SCHED.search(str(text or ""))
    if not m:
        return None
    a, b = _mins(int(m[1]), int(m[2]), m[3]), _mins(int(m[4]), int(m[5]), m[6])
    return (a, b) if b > a else None


def parse_rest_days(work_group) -> set[int]:
    """مجموعة العمل -> أيام الراحة الأسبوعية. لو مفيش أيام مذكورة بنرجع الافتراضي (الجمعة + السبت)."""
    return LT.rest_days(work_group, S["weekend_default"])


def hm(minutes: float | int | None, blank_zero: bool = False) -> str:
    if minutes is None or (blank_zero and not minutes):
        return ""
    m = int(round(minutes))
    return f"{m // 60}:{m % 60:02d}"


def hm_signed(minutes: float | int) -> str:
    m = int(round(minutes))
    return ("-" if m < 0 else "") + hm(abs(m))


def _correct_report_punch_time(punch_time: pd.Timestamp) -> pd.Timestamp:
    local_punch = punch_time.to_pydatetime().replace(tzinfo=local_time.CAIRO)
    return punch_time + REPORT_PUNCH_OFFSET if local_punch.dst() else punch_time


def ampm(minutes: int | None) -> str:
    if minutes is None:
        return ""
    h, m = divmod(int(minutes), 60)
    return f"{(h % 12) or 12}:{m:02d} {'PM' if h >= 12 else 'AM'}"


def period_for(year: int, month: int, cycle_start: int | None = None) -> tuple[dt.date, dt.date]:
    """الفترة المالية: cycle_start=1 -> الشهر الميلادي. 26 -> من 26 الشهر اللي قبله لـ 25 من الشهر ده."""
    cs = int(cycle_start or S["report_cycle_start"] or 1)
    if cs <= 1:
        return dt.date(year, month, 1), dt.date(year, month, calendar.monthrange(year, month)[1])
    py, pm = (year - 1, 12) if month == 1 else (year, month - 1)
    cs = min(cs, calendar.monthrange(py, pm)[1])
    return dt.date(py, pm, cs), dt.date(year, month, cs - 1)


def find_employee(code: str) -> dict | None:
    hr = D.get_df()
    key = A._norm_code(pd.Series([str(code)], dtype="string")).iloc[0]
    hr_keys = A._norm_code(hr["code"].astype(str))
    r = hr[hr_keys == key]
    if r.empty:
        return None
    return _clean(r.iloc[0].to_dict())


def _clean(r: dict) -> dict:
    return {k: (None if (not isinstance(v, (list, tuple)) and pd.isna(v)) else v) for k, v in r.items()}


def department_employees(dept: str | None = None) -> list[dict]:
    """صفوف HR كاملة لموظفي قسم (أو كل الموظفين لو dept فاضي) — بتتبعت لـ build() عشان ما يدوّرش على الموظف كل مرة."""
    hr = D.get_df()
    if dept:
        hr = hr[hr["department"] == dept]
    return [_clean(r) for r in hr.to_dict("records")]


def employees_list() -> list[dict]:
    hr = D.get_df()
    return [
        dict(
            code=str(row["code"]),
            name=str(row["name"]),
            department=None if pd.isna(row["department"]) else str(row["department"]),
            management=None if pd.isna(row["management"]) else str(row["management"]),
            manager=None if pd.isna(row["manager"]) else str(row["manager"]),
            location=None if pd.isna(row["location"]) else str(row["location"]),
        )
        for _, row in hr.iterrows()
    ]


def resolve_employee(query: str) -> str:
    """Resolve an employee code or a unique full/partial name to the HR code."""
    hr = D.get_df()
    code_key = A._norm_code(pd.Series([query], dtype="string")).iloc[0]
    code_keys = A._norm_code(hr["code"].astype(str))
    matches = hr[code_keys == code_key]
    if not matches.empty:
        return str(matches.iloc[0]["code"])

    names = hr["name"].fillna("").astype(str).str.strip()
    normalized = names.str.casefold()
    needle = query.strip().casefold()
    matches = hr[normalized == needle]
    if matches.empty:
        matches = hr[normalized.str.contains(needle, regex=False)]
    matches = matches.drop_duplicates(subset=["code"])
    if len(matches) == 1:
        return str(matches.iloc[0]["code"])
    if len(matches) > 1:
        raise A.AttendanceError("الاسم يطابق أكثر من موظف. اختاري الاسم من القائمة أو اكتبي كود الموظف.")
    raise A.AttendanceError(f"مفيش موظف مطابق للاسم أو الكود: {query}")


# ───────────────────────── الحساب ─────────────────────────
def build(code: str, start: dt.date, end: dt.date, *, punches: pd.DataFrame | None = None,
          emp: dict | None = None, leave_entries: list[dict] | None = None) -> dict:
    emp = emp or find_employee(code)
    if emp is None:
        raise A.AttendanceError(f"الكود {code} مش موجود في ملف HR.")

    sched = parse_schedule(emp.get("schedule")) or parse_schedule(S.get("default_schedule"))
    department = str(emp.get("department") or "").strip()
    rest = {4} if department == "خدمة العملاء" else parse_rest_days(emp.get("work_group"))
    grace = int(S.get("grace_minutes") or 0)
    if sched and sched[0] // 60 in (9, 10):
        grace = max(grace, 15)
    today = local_time.today()

    if punches is None and S["mode"] == "demo":
        A.demo_pool([(str(emp["code"]), str(emp.get("location") or ""))])
    p = A.fetch(start, end, None, emp=str(emp["code"])) if punches is None else punches
    key = A._norm_code(pd.Series([str(emp["code"])], dtype="string")).iloc[0]
    p = p[p["key"] == key]
    # تصحيح التوقيت الصيفي بيتم الآن مركزيًا داخل attendance.fetch (A.dst_correct)
    by_day: dict[dt.date, list[pd.Timestamp]] = {}
    for t in sorted(p["punch_time"]):
        by_day.setdefault(t.date(), []).append(t)

    if leave_entries is None:
        leave_entries = LT.entries_for(str(emp["code"]))
    leave_by_day: dict[dt.date, list[dict]] = {}
    for entry in leave_entries:
        if entry["leave_code"] == "ADA":
            continue
        entry_start = dt.date.fromisoformat(entry["leave_date"])
        entry_end = dt.date.fromisoformat(entry.get("end_date") or entry["leave_date"])
        span = []
        check = entry_start
        while check <= entry_end:
            if check.weekday() not in rest and not HOLIDAYS.get(check.isoformat()):
                span.append(check)
            check += dt.timedelta(days=1)
        if not span:
            span = [entry_start]
        remaining_days = float(entry["days"])
        hour_value = float(entry["hours"])
        daily_hours = hour_value / len(span) if hour_value else 0.0
        for day in span:
            day_days = min(1.0, remaining_days)
            if day_days > 0 or daily_hours > 0:
                leave_by_day.setdefault(day, []).append(
                    dict(entry, day_days=day_days, day_hours=daily_hours))
                remaining_days = max(0.0, remaining_days - day_days)
            if remaining_days == 0 and daily_hours == 0:
                break

    rows, tot = [], dict(off=0, act=0, holiday_act=0, rest_act=0, unscheduled_act=0,
                         late=0, early=0, adv=0, ot_before=0, ot=0, grace_used=0, inside=0,
                         hol_days=0, rest_days=0, missing=0, missing_hours=0,
                         absent=0, absent_hours=0, pending_hours=0, days_present=0,
                         workdays=0, worked_days=0, leave_days=0, leave_min=0,
                         paid_leave_days=0, annual_leave_days=0, casual_leave_days=0, sick_leave_days=0,
                         permission_minutes=0, mission_minutes=0)
    d = start
    while d <= end:
        iso = d.isoformat()
        punches = by_day.get(d, [])
        day_leaves = leave_by_day.get(d, [])
        is_rest, hol = d.weekday() in rest, HOLIDAYS.get(iso)
        off_day = is_rest or bool(hol)
        deductible_leave = sum(x["day_days"] for x in day_leaves if x["leave_code"] == "D")
        paid_leave = sum(x["day_days"] for x in day_leaves
                         if x["leave_code"] in ("A", "C", "DE", "W", "S", "P", "MI"))
        covered_leave = paid_leave + deductible_leave
        day_mission = [x for x in day_leaves if x["leave_code"] == "M"]
        day_permissions = [x for x in day_leaves if x["leave_code"] == "PERM"]
        mission_minutes = sum(
            x["day_hours"] * 60 if x["day_hours"] else x["day_days"] * (sched[1] - sched[0] if sched else 0)
            for x in day_mission)
        permission_minutes = sum(x["day_hours"] * 60 for x in day_permissions)
        tot["leave_days"] += deductible_leave
        tot["leave_min"] += covered_leave * (sched[1] - sched[0] if sched else 0)
        tot["leave_min"] += permission_minutes
        tot["paid_leave_days"] += paid_leave
        tot["annual_leave_days"] += sum(x["day_days"] for x in day_leaves if x["leave_code"] == "A")
        tot["casual_leave_days"] += sum(x["day_days"] for x in day_leaves if x["leave_code"] == "C")
        tot["sick_leave_days"] += sum(x["day_days"] for x in day_leaves if x["leave_code"] == "S")
        tot["permission_minutes"] += permission_minutes
        tot["mission_minutes"] += mission_minutes
        r = dict(date=d, iso=iso, dow=EN_DAYS[d.weekday()], rest=is_rest, holiday=hol or "",
                 off_in=None if off_day or not sched else sched[0],
                 off_out=None if off_day or not sched else sched[1],
                 act_in=None, act_out=None, act=0, inside=0, ot_before=0, ot=0, late=0, early=0, adv=0,
                 grace_used=0, status="", n=len(punches))
        r["off"] = (r["off_out"] - r["off_in"]) if r["off_in"] is not None else 0
        if not off_day:                       # يوم عمل رسمي (مش راحة ولا عطلة)
            tot["workdays"] += 1
            if punches:                       # حضر فعلًا (حتى لو بصمة ناقصة — بتتخصم ربع يوم لوحدها)
                tot["worked_days"] += 1

        if punches:
            first, last = punches[0], punches[-1]
            m_in = first.hour * 60 + first.minute
            m_out = last.hour * 60 + last.minute
            single = len(punches) == 1 or (last - first) < pd.Timedelta(minutes=1)
            if d == REPORT_ARRIVAL_ADJUSTMENT_DATE:
                mid = (sched[0] + sched[1]) // 2 if sched else 13 * 60
                if not single or m_in <= mid:
                    first += REPORT_ARRIVAL_ADJUSTMENT
                    m_in = first.hour * 60 + first.minute
            if off_day:
                tot["hol_days" if hol else "rest_days"] += 1
            if single:
                # بصمة واحدة بس: نحسبها حضور لو قبل منتصف الدوام، انصراف لو بعده
                mid = (sched[0] + sched[1]) // 2 if sched else 13 * 60
                if m_in <= mid:
                    r["act_in"] = m_in
                else:
                    r["act_out"] = m_in
                if d >= today:
                    r["status"] = "بانتظار اكتمال البصمات"
                    tot["pending_hours"] += r["off"]
                else:
                    r["status"] = "فقدان بصمة"
                    tot["missing"] += 1
                    if not off_day:
                        tot["missing_hours"] += r["off"]
            else:
                r["act_in"], r["act_out"] = m_in, m_out
                r["act"] = m_out - m_in
                if off_day:
                    r["status"] = "عمل في العطلة الرسمية" if hol else "عمل في الراحة الأسبوعية"
                else:
                    r["status"] = "حضور"
            if r["off_in"] is not None and not single:
                a, b = r["off_in"], r["off_out"]
                raw_late = max(0, m_in - a)
                r["late"] = max(0, raw_late - grace)
                r["grace_used"] = min(raw_late, grace)
                r["early"] = max(0, b - m_out)
                r["adv"] = max(0, a - m_in)
                r["ot_before"] = r["adv"]
                r["inside"] = max(0, min(m_out, b) - max(m_in, a))
                r["ot"] = max(0, m_out - b)
            elif r["off_in"] is not None and single:
                pass   # فقدان بصمة: مفيش حساب تأخير/انصراف مبكر لأن نص البيانات ناقص
            elif not off_day and not single:
                r["inside"] = r["act"]       # مفيش مواعيد رسمية: كل الساعات داخل الدوام
            if not single:
                if hol:
                    tot["holiday_act"] += r["act"]
                elif is_rest:
                    tot["rest_act"] += r["act"]
                elif sched:
                    tot["act"] += r["act"]
                else:
                    tot["unscheduled_act"] += r["act"]
            if day_mission:
                r["act"] += mission_minutes
                r["inside"] += min(mission_minutes, max(0, r["off"] - r["inside"]))
                if hol:
                    tot["holiday_act"] += mission_minutes
                elif is_rest:
                    tot["rest_act"] += mission_minutes
                elif sched:
                    tot["act"] += mission_minutes
                else:
                    tot["unscheduled_act"] += mission_minutes
            tot["days_present"] += 1
        elif day_mission:
            r["status"] = "مأمورية"
            r["act"] = mission_minutes
            r["inside"] = min(mission_minutes, r["off"]) if r["off"] else mission_minutes
            if sched:
                tot["act"] += mission_minutes
            else:
                tot["unscheduled_act"] += mission_minutes
            tot["days_present"] += 1
            if not off_day:
                tot["worked_days"] += 1
                uncovered = max(0, r["off"] - mission_minutes)
                if uncovered and d < today:
                    tot["absent"] += uncovered / r["off"]
                    tot["absent_hours"] += uncovered
        elif day_leaves and any(x["leave_code"] in ("V", "AD") for x in day_leaves):
            codes = {x["leave_code"] for x in day_leaves}
            if "V" in codes:
                r["status"] = "حضور بدون بصمة"
            else:
                r["status"] = "يوم إضافي بالمرتب"
            if not off_day:
                r["act"] = r["off"]
                r["inside"] = r["off"]
                if sched:
                    tot["act"] += r["act"]
                else:
                    tot["unscheduled_act"] += r["act"]
                tot["worked_days"] += 1
            tot["days_present"] += 1
        elif day_leaves and any(x["leave_code"] in ("A", "C", "DE", "W", "S", "P", "OFF", "MI", "D") for x in day_leaves):
            if off_day:
                r["status"] = hol or "راحة أسبوعية"
            else:
                priorities = ("D", "A", "C", "S", "MI", "W", "DE", "P", "OFF")
                code = next((c for c in priorities if any(x["leave_code"] == c for x in day_leaves)), "")
                r["status"] = {
                    "D": "إجازة بالخصم", "A": "إجازة اعتيادية", "C": "إجازة عارضة",
                    "DE": "وفاة", "W": "إجازة زواج", "S": "إجازة مرضي",
                    "P": "إجازة رسمية", "OFF": "راحة أسبوعية", "MI": "إجازة وضع",
                }.get(code, "إجازة")
                if r["off"] and d < today:
                    uncovered = max(0, r["off"] * (1 - min(1.0, covered_leave)))
                    if uncovered:
                        tot["absent"] += uncovered / r["off"]
                        tot["absent_hours"] += uncovered
        else:
            if off_day:
                r["status"] = hol or "راحة أسبوعية"
            elif d < today and (d - start).days >= 0:
                uncovered = max(0, r["off"] - min(r["off"], permission_minutes))
                r["status"] = "إذن / غياب جزئي" if permission_minutes else "غياب"
                if r["off"]:
                    tot["absent"] += uncovered / r["off"]
                    tot["absent_hours"] += uncovered
                elif not permission_minutes:
                    tot["absent"] += 1
            else:
                tot["pending_hours"] += r["off"]

        if day_permissions and "إذن" not in r["status"]:
            r["status"] = f"{r['status']} / إذن" if r["status"] else "إذن"

        for k_src, k_tot in (("off", "off"), ("late", "late"), ("early", "early"),
                             ("adv", "adv"), ("ot_before", "ot_before"), ("ot", "ot"), ("inside", "inside"),
                             ("grace_used", "grace_used")):
            tot[k_tot] += r[k_src]
        rows.append(r)
        d += dt.timedelta(days=1)

    actual_hours = tot["act"] + tot["holiday_act"] + tot["rest_act"] + tot["unscheduled_act"]
    net = max(0, tot["late"] + tot["early"] - tot["adv"])
    day_len = (sched[1] - sched[0]) if sched else 0
    official_counted = tot["off"]
    missing_ded = int(round(tot["missing"] * 0.25 * day_len))
    absent_min = tot["absent_hours"]
    late_early_total = tot["late"] + tot["early"]
    leave_covered_days = tot["leave_days"] + tot["paid_leave_days"]
    recon_actual = actual_hours
    summary = [
        ("عدد ساعات العمل الرسمية (ثابتة حسب جدول الدوام)", hm(tot["off"])),
        ("عدد ساعات العمل الفعلية", hm(recon_actual)),
        ("عدد ساعات الإضافي", hm(tot["ot_before"] + tot["ot"])),
        ("أيام إضافية في عطلات رسمية", str(tot["hol_days"])),
        ("أيام إضافية في راحة أسبوعية", str(tot["rest_days"])),
        ("الأذونات المقدمة", hm(tot["permission_minutes"])),
        ("التأخيرات والانصراف المبكر", hm(late_early_total)),
        ("صافي التأخيرات والانصراف المبكر", hm(net)),
        ("فقدان بصمة (خصم ربع يوم لكل مرة)",
         f"{tot['missing'] * 0.25:g} يوم ({tot['missing']} مرة) = {hm(missing_ded) or '0:00'} ساعة"),
        ("أيام غياب", f"{tot['absent']} يوم = {hm(absent_min) or '0:00'} ساعة"),
        ("إجازة بالخصم", f"{tot['leave_days']:g} يوم"),
        ("إجازة اعتيادية", f"{tot['annual_leave_days']:g} يوم"),
        ("إجازة عارضة", f"{tot['casual_leave_days']:g} يوم"),
    ]
    # ───── الملخص 1: معادلة الاتزان (لازم تطلع صفر) ─────
    deducted = [
        ("actual", recon_actual),
        ("late_early", late_early_total),
        ("net", net if RECON_INCLUDE_NET else 0),
        ("absent", absent_min),
        ("missing", missing_ded),
        ("leave", tot["leave_min"]),
    ]
    diff = int(round(official_counted - sum(v for _, v in deducted)))
    recon = dict(
        official=tot["off"], official_counted=official_counted, actual=recon_actual, late_early=late_early_total, net=net,
        absent_min=absent_min, absent_days=tot["absent"], missing_min=missing_ded, missing_count=tot["missing"],
        missing_days=tot["missing"] * 0.25, leave_min=tot["leave_min"],
        leave_days=leave_covered_days, pending=tot["pending_hours"], diff=diff, ok=(diff == 0),
        include_net=RECON_INCLUDE_NET, has_schedule=sched is not None,
    )
    s1 = [
        ("official", "عدد ساعات العمل الرسمية", hm(official_counted), "ثابتة حسب جدول الدوام"),
        ("actual", "عدد ساعات العمل الفعلية", hm(actual_hours), "إجمالي ساعات الحضور"),
        ("late_early", "التأخيرات والانصراف المبكر", hm(late_early_total), "بعد فترة السماح"),
        ("net", "صافي التأخيرات والانصراف المبكر", hm(net), "للعرض فقط" if not RECON_INCLUDE_NET else ""),
        ("absent", "أيام غياب", str(tot["absent"]), f"= {hm(absent_min) or '0:00'} ساعة"),
        ("missing", "فقدان بصمة (خصم ربع يوم لكل مرة)", f"{tot['missing'] * 0.25:g}", f"يوم ({tot['missing']} مرة) = {hm(missing_ded) or '0:00'} ساعة"),
    ]
    # ───── الملخص 2: جدولين ─────
    s2a = [
        ("عدد ساعات الإضافي", hm(tot["ot_before"] + tot["ot"]) or "0:00", "ساعة"),
        ("أيام إضافية", str(tot["hol_days"] + tot["rest_days"]), f"عطلات رسمية {tot['hol_days']} · راحة أسبوعية {tot['rest_days']}"),
        ("الأذونات بالساعات", hm(tot["permission_minutes"]) or "0:00", "ساعة"),
        ("ساعات المأمورية", hm(tot["mission_minutes"]) or "0:00", "ساعة"),
    ]
    s2b = [
        ("إجازة بالخصم", f"{tot['leave_days']:g}", "يوم"),
        ("عارضة", f"{tot['casual_leave_days']:g}", "يوم"),
        ("اعتيادي", f"{tot['annual_leave_days']:g}", "يوم"),
        ("مرضي", f"{tot['sick_leave_days']:g}", "يوم"),
    ]

    n_days, n_sum = len(rows), len(summary)
    layout_rows = max(n_days, n_sum)
    base, extra = divmod(layout_rows, n_sum)
    spans, at = {}, 0
    for i in range(n_sum):
        height = base + (1 if i < extra else 0)
        spans[at] = (i, height)
        at += height

    title = f"تقرير الحضور و الانصراف عن الفترة من {start:%d-%m-%Y} إلى {end:%d-%m-%Y}"
    return dict(emp=dict(code=str(emp["code"]), name=str(emp["name"]), job=emp.get("job"),
                         dept=emp.get("department"), management=emp.get("management"),
                         manager=emp.get("manager"),
                         schedule=emp.get("schedule"), work_group=emp.get("work_group"), overtime=emp.get("overtime")),
                start=start, end=end, title=title, rows=rows, summary=summary, totals=tot,
                recon=recon, s1=s1, s2a=s2a, s2b=s2b,
                has_schedule=sched is not None, sum_spans=spans, layout_rows=layout_rows,
                rest_days=sorted(rest), punches=int(len(p)))


# ───────────────────────── ملخص القسم (All Summary) ─────────────────────────
# نفس أعمدة شيت Summary بالظبط. كل الساعات بالدقايق جوه الحساب وبتتعرض H:MM، والجمع بيتم على الدقايق
# (مش على النصوص) عشان إجمالي الساعات يطلع صح حتى لو عدّى 24 ساعة.
#   إجمالي الخصم (ساعات)  = إجمالي التأخير والانصراف المبكر           (الشيت: N = J)
#   إجمالي الخصم (أيام)   = أيام الإجازة بالخصم + أيام الغياب + فقدان البصمة × 0.25   (الشيت: O = H + G + I × 0.25)
MISSING_PUNCH_DAYS = 0.25

SUM_MINUTES = ("official", "actual", "late_hours", "overtime", "deduction_hours")
SUM_COUNTS = ("official_days", "actual_days", "absent_days", "leave_days", "missing_count", "rest_days", "holiday_days")


def summary_row(rep: dict) -> dict:
    t, rc, e = rep["totals"], rep["recon"], rep["emp"]
    leave_days = t["leave_days"]
    late_hours = t["late"] + t["early"]
    return dict(
        code=e["code"], name=e["name"], job=e.get("job"), dept=e.get("dept"),
        has_schedule=rc["has_schedule"],
        official=t["off"] if rc["has_schedule"] else None,
        actual=rc["actual"],
        official_days=t["workdays"], actual_days=t["worked_days"],
        absent_days=t["absent"], leave_days=leave_days, missing_count=t["missing"],
        late_hours=late_hours,
        overtime=t["ot_before"] + t["ot"], rest_days=t["rest_days"], holiday_days=t["hol_days"],
        deduction_hours=late_hours,
        deduction_days=(leave_days or 0) + t["absent"] + t["missing"] * MISSING_PUNCH_DAYS,
    )


def summarize(reports: list[dict]) -> dict:
    rows = [summary_row(r) for r in reports]
    from collections import Counter
    seen = Counter(str(r["code"]).strip() for r in rows)
    for r in rows:                       # زي التنسيق الشرطي في الشيت: الكود المكرر يتظلل
        r["dup"] = seen[str(r["code"]).strip()] > 1
    tot = {k: sum(r[k] or 0 for r in rows) for k in SUM_MINUTES + SUM_COUNTS}
    tot["official"] = sum(r["official"] for r in rows if r["official"] is not None)
    tot["deduction_days"] = sum(r["deduction_days"] for r in rows)
    return dict(rows=rows, totals=tot, employees=len(rows),
                scheduled=sum(r["has_schedule"] for r in rows),
                with_deduction=sum(1 for r in rows if r["deduction_days"] or r["deduction_hours"]))


# ───────────────────────── Excel ─────────────────────────
HEAD = ["الكود", "اسم الموظف", "التاريخ", "اليوم", "ملاحظات اليوم",
        "الحضور", "الانصراف", "ساعات العمل",            # فعلي
        "الإضافي قبل بداية الدوام",
        "الحضور", "الانصراف", "ساعات العمل",            # رسمي
        "الإجمالي في مواعيد العمل", "الإضافي بعد مواعيد العمل", "التأخير عن الحضور", "الخروج قبل الانصراف",
        "حالة اليوم"]


def to_xlsx(rep: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter as L

    wb = Workbook()
    ws = wb.active
    ws.title = "تقرير الحضور"
    ws.sheet_view.rightToLeft = False
    ws.sheet_view.showGridLines = False

    thin = Side(style="thin", color="000000")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    F = lambda **k: Font(name="Arial", **k)
    fill = lambda c: PatternFill("solid", start_color=c, end_color=c)
    BLUE, LBLUE, GRAY, DGRAY, RED = "2F5597", "DDE6F5", "E7E6E6", "BFBFBF", "C00000"
    ctr = Alignment(horizontal="center", vertical="center", wrap_text=True)

    n_cols = len(HEAD) + 2
    first_data = 4
    rows = rep["rows"]
    last_data = first_data + rep["layout_rows"] - 1

    # عنوان
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    c = ws.cell(1, 1, rep["title"])
    c.font, c.alignment, c.fill = F(bold=True, size=12, color=RED), ctr, fill(GRAY)
    ws.row_dimensions[1].height = 24

    # رؤوس (صفين)
    def head(r1, r2, col, text, fillc=GRAY, c2=None):
        ws.merge_cells(start_row=r1, start_column=col, end_row=r2, end_column=c2 or col)
        x = ws.cell(r1, col, text)
        x.font, x.alignment, x.fill = F(bold=True, size=9), ctr, fill(fillc)
        for cc in range(col, (c2 or col) + 1):
            for rr in range(r1, r2 + 1):
                ws.cell(rr, cc).border = box
                ws.cell(rr, cc).fill = fill(fillc)

    for i in (1, 2, 3, 4, 5):
        head(2, 3, i, HEAD[i - 1])
    head(2, 2, 6, "مواعيد العمل الفعلية", GRAY, 8)
    head(2, 3, 9, HEAD[8])
    head(2, 2, 10, "مواعيد العمل الرسمية", LBLUE, 12)
    for i in (6, 7, 8):
        head(3, 3, i, HEAD[i - 1])
    for i in (10, 11, 12):
        head(3, 3, i, HEAD[i - 1], LBLUE)
    for i in range(13, 18):
        head(2, 3, i, HEAD[i - 1])
    head(2, 3, 18, "الملاحظات", GRAY, 19)
    ws.row_dimensions[2].height = 22
    ws.row_dimensions[3].height = 22

    # الأعمدة: العرض
    widths = [9, 30, 10, 7, 16, 10, 10, 10, 13, 10, 10, 10, 13, 13, 12, 12, 24, 36, 10]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[L(i)].width = w

    day = lambda m: (m / 1440) if m is not None else None
    TF = "h:mm AM/PM"
    HF = "[h]:mm"

    for i, r in enumerate(rows):
        rr = first_data + i
        off = r["rest"] or bool(r["holiday"])
        worked = bool(r["act"]) or r["act_in"] is not None or r["act_out"] is not None
        vals = [
            None, None, r["date"], r["dow"], r["holiday"] or None,
            day(r["act_in"]), day(r["act_out"]), day(r["act"]) if (worked or off) else None,
            day(r["ot_before"]) if r["ot_before"] else None,
            day(r["off_in"]), day(r["off_out"]), day(r["off"]) if r["off_in"] is not None else None,
            day(r["inside"]) if r["inside"] else None, day(r["ot"]) if r["ot"] else None,
            day(r["late"]) if r["late"] else None, day(r["early"]) if r["early"] else None,
            r["status"] or None,
        ]
        fmts = [None, None, "d-mmm", None, None, TF, TF, HF, HF, TF, TF, HF, HF, HF, HF, HF, None]
        for col, (v, nf) in enumerate(zip(vals, fmts), 1):
            x = ws.cell(rr, col, v)
            x.border, x.alignment = box, ctr
            x.font = F(size=9, bold=col in (3, 4))
            if nf:
                x.number_format = nf
            if col in (10, 11, 12) and not off:
                x.fill = fill(LBLUE)
            if off:
                x.fill = fill(BLUE)
                x.font = F(size=9, bold=True, color="FFFFFF")
        if r["holiday"]:
            ws.cell(rr, 5).font = F(size=9, bold=True, color="FFFFFF" if off else RED)
        if r["status"] in ("غياب", "فقدان بصمة"):
            ws.cell(rr, 17).font = F(size=9, bold=True, color=RED if not off else "FFFFFF")
        # أعمدة الحضور والانصراف الإضافية ممنوعة من الأخطاء: الفاضي يفضل فاضي
        ws.row_dimensions[rr].height = 17

    for rr in range(first_data + len(rows), last_data + 1):
        for col in range(3, 18):
            ws.cell(rr, col).border = box

    # الكود + الاسم: خلية واحدة مدموجة طول الشيت
    for col, text, fc in ((1, rep["emp"]["code"], "FFFFFF"), (2, rep["emp"]["name"], DGRAY)):
        ws.merge_cells(start_row=first_data, start_column=col, end_row=last_data, end_column=col)
        x = ws.cell(first_data, col, text)
        x.font, x.alignment = F(bold=True, size=11), Alignment(horizontal="center", vertical="center", wrap_text=True, text_rotation=0)
        for rr in range(first_data, last_data + 1):
            ws.cell(rr, col).fill, ws.cell(rr, col).border = fill(fc), box

    r0 = first_data
    for at in sorted(rep["sum_spans"]):
        i, height = rep["sum_spans"][at]
        label, value = rep["summary"][i]
        r1 = r0 + height - 1
        for col, text in ((18, label), (19, value)):
            ws.merge_cells(start_row=r0, start_column=col, end_row=r1, end_column=col)
            x = ws.cell(r0, col, text)
            x.font, x.alignment = F(bold=True, size=9 if col == 17 else 11), ctr
            for rr in range(r0, r1 + 1):
                ws.cell(rr, col).border = box
        r0 = r1 + 1

    # شريط أحمر في الآخر
    fr = last_data + 1
    ws.merge_cells(start_row=fr, start_column=1, end_row=fr, end_column=n_cols)
    ws.cell(fr, 1).fill = fill(RED)
    ws.row_dimensions[fr].height = 10

    # بيانات إضافية تحت الجدول (مواعيد الموظف وراحته) — خارج التصميم الأصلي، بسطر صغير
    note = f"مواعيد الموظف: {rep['emp'].get('schedule') or 'غير معروفة'}   |   مجموعة العمل: {rep['emp'].get('work_group') or 'غير معروفة'}"
    ws.merge_cells(start_row=fr + 1, start_column=1, end_row=fr + 1, end_column=n_cols)
    x = ws.cell(fr + 1, 1, note)
    x.font, x.alignment = F(size=8, color="595959"), Alignment(horizontal="right")

    ws.freeze_panes = ws.cell(first_data, 6)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 1
    from openpyxl.worksheet.properties import PageSetupProperties
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_title_rows = "1:3"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


SUM_HEAD = {
    "code": "الكود", "name": "الاسم",
    "work": "ساعات العمل", "att": "ملاحظات تقارير الحضور و الانصراف", "ot": "الاضافى", "ded": "اجمالى الخصم",
    "title": "ملاحظات ادارة الموارد البشرية", "admin": "ملاحظات الادارة",
    "official": "عدد ساعات العمل الرسمية", "actual": "عدد ساعات العمل الفعلية",
    "official_days": "عدد ايام العمل الرسميه", "actual_days": "عدد ايام العمل الفعلية",
    "absent": "عدد ايام الغياب", "leave": "عدد ايام الاجازات بالخصم", "missing": "فقدان البصمة",
    "late": "اجمالى ساعات التأخير والانصراف المبكر",
    "ot_hours": "ساعات", "rest": "راحة اسبوعية", "hol": "عطلات رسمية",
    "ded_hours": "ساعات", "ded_days": "ايام",
}


def summary_to_xlsx(summary: dict, subtitle: str = "") -> bytes:
    """نسخة طبق الأصل من شيت Summary: RTL، Calibri، حدود مزدوجة، نفس الألوان وارتفاعات الصفوف، فلتر،
    والخصم بنفس المعادلات (N = J ، O = H + G + I*0.25)."""
    from openpyxl import Workbook
    from openpyxl.formatting.rule import CellIsRule, Rule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.styles.differential import DifferentialStyle
    from openpyxl.utils import get_column_letter as L
    from openpyxl.worksheet.properties import PageSetupProperties

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.sheet_view.rightToLeft = True
    ws.sheet_view.showGridLines = False

    dbl, med = Side(style="double", color="000000"), Side(style="medium", color="000000")
    F = lambda **k: Font(name="Calibri", **k)
    fill = lambda c: PatternFill("solid", start_color=c, end_color=c)
    ctr = Alignment(horizontal="center", vertical="center", wrap_text=True)
    NAVY, GOLD, BLUE, GREEN, RED, ADMIN = "203864", "BF9000", "2F5597", "00B050", "FF0000", "0070C0"
    HF = "[h]:mm"
    NCOL = 16

    H = SUM_HEAD
    rows = summary["rows"]
    first = 4
    last = first + max(len(rows), 1) - 1
    tr_ = last + 1

    # حدود: مزدوجة جوه الجدول، وmedium على الإطار الخارجي (زي الأصل)
    def edge(r, c, bottom_row=None):
        bottom_row = bottom_row or tr_
        return Border(left=med if c == NCOL else dbl, right=med if c == 1 else dbl,
                      top=med if r == 1 else dbl, bottom=med if r == bottom_row else dbl)
    for r in range(1, tr_ + 1):
        for c in range(1, NCOL + 1):
            ws.cell(r, c).border = edge(r, c)

    def head(r1, c1, r2, c2, text, color, size):
        ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)
        for rr in range(r1, r2 + 1):
            for cc in range(c1, c2 + 1):
                ws.cell(rr, cc).fill = fill(color)
        x = ws.cell(r1, c1, text)
        x.font, x.alignment = F(bold=True, size=size, color="FFFFFF"), ctr

    head(1, 1, 3, 1, H["code"], NAVY, 16)
    head(1, 2, 3, 2, H["name"], NAVY, 16)
    head(1, 3, 1, 15, H["title"], NAVY, 16)
    head(2, 3, 2, 6, H["work"], GOLD, 14)
    head(2, 7, 2, 10, H["att"], BLUE, 14)
    head(2, 11, 2, 13, H["ot"], GREEN, 14)
    head(2, 14, 2, 15, H["ded"], RED, 14)
    head(1, 16, 3, 16, H["admin"], ADMIN, 14)
    for col, key, color in ((3, "official", GOLD), (4, "actual", GOLD), (5, "official_days", GOLD), (6, "actual_days", GOLD),
                            (7, "absent", BLUE), (8, "leave", BLUE), (9, "missing", BLUE), (10, "late", BLUE),
                            (11, "ot_hours", GREEN), (12, "rest", GREEN), (13, "hol", GREEN),
                            (14, "ded_hours", RED), (15, "ded_days", RED)):
        head(3, col, 3, col, H[key], color, 11)
    ws.row_dimensions[1].height = 29.25
    ws.row_dimensions[2].height = 34.5
    ws.row_dimensions[3].height = 69

    # عرض الأعمدة زي الأصل (مع توسيع بسيط للأرقام الكبيرة)
    widths = [14.7, 24.1, 12.1, 12.1, 12.1, 12.1, 9.5, 14, 9.5, 14, 11, 9, 9, 9, 9, 18.3]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[L(i)].width = w

    day = lambda m: None if m is None else m / 1440
    fmts = {3: HF, 4: HF, 5: "0", 6: "0", 7: "0", 8: "0", 9: "0", 10: HF, 11: HF, 12: "0", 13: "0", 14: HF, 15: "0.00"}
    redcols, greencols = (7, 8, 9, 10, 14, 15), (11, 12, 13)
    for i, r in enumerate(rows):
        rr = first + i
        vals = {1: r["code"], 2: r["name"], 3: day(r["official"]), 4: day(r["actual"]),
                5: r["official_days"], 6: r["actual_days"],                 7: r["absent_days"], 8: r["leave_days"], 9: r["missing_count"],
                10: day(r["late_hours"]), 11: day(r["overtime"]), 12: r["rest_days"], 13: r["holiday_days"],
                14: f"=J{rr}", 15: f"=H{rr}+G{rr}+(I{rr}*0.25)", 16: None}
        for col in range(1, NCOL + 1):
            x = ws.cell(rr, col, vals[col])
            x.alignment = ctr
            color = "C00000" if col in redcols else ("00B050" if col in greencols else "000000")
            x.font = F(bold=True, size=12 if col <= 2 else (12 if col in redcols + greencols else 11), color=color)
            if col in fmts:
                x.number_format = fmts[col]
        ws.row_dimensions[rr].height = 44.25

    # صف الإجماليات (إضافة فوق الأصل)
    ws.merge_cells(start_row=tr_, start_column=1, end_row=tr_, end_column=2)
    for col in range(1, NCOL + 1):
        x = ws.cell(tr_, col)
        x.fill, x.alignment, x.font = fill("D9E2F3"), ctr, F(bold=True, size=12)
    ws.cell(tr_, 1, "الإجمالي")
    for col, nf in fmts.items():
        x = ws.cell(tr_, col, f"=SUM({L(col)}{first}:{L(col)}{last})" if rows else None)
        x.number_format = nf
    ws.row_dimensions[tr_].height = 30

    # التنسيق الشرطي زي الأصل: أكبر من صفر أحمر، صفر رمادي، كود مكرر وردي
    red_dx = DifferentialStyle(font=Font(color="FF0000", bold=True))
    for rng in (f"G{first}:J{last}", f"N{first}:O{last}"):
        ws.conditional_formatting.add(rng, CellIsRule(operator="greaterThan", formula=["0"], font=Font(color="FF0000", bold=True)))
        ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=["0"], font=Font(color="A6A6A6")))
    ws.conditional_formatting.add(f"K{first}:M{last}", CellIsRule(operator="equal", formula=["0"], font=Font(color="A6A6A6")))
    ws.conditional_formatting.add(f"A{first}:A{last}", Rule(type="duplicateValues",
        dxf=DifferentialStyle(font=Font(color="9C0006"), fill=PatternFill(bgColor="FFC7CE"))))

    ws.auto_filter.ref = f"A3:P{last}"

    notes = [subtitle,
             "إجمالي الخصم (ساعات) = إجمالي التأخير والانصراف المبكر (N = J).  إجمالي الخصم (أيام) = أيام الإجازات بالخصم + أيام الغياب + (فقدان البصمة × 0.25) (O = H + G + I×0.25).",
             "عدد أيام الإجازات بالخصم يُقرأ تلقائيًا من الحركات المسجلة بكود D في سجل الإجازات.",
             "عدد أيام العمل الفعلية تشمل الأيام اللي فيها بصمة ناقصة (بتتخصم ربع يوم في عمود الخصم)."]
    for k, text in enumerate(n for n in notes if n):
        rr = tr_ + 2 + k
        ws.merge_cells(start_row=rr, start_column=1, end_row=rr, end_column=NCOL)
        x = ws.cell(rr, 1, text)
        x.font, x.alignment = F(size=10, color="595959", bold=(k == 0)), Alignment(horizontal="right", wrap_text=True)

    ws.freeze_panes = "C4"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_title_rows = "1:3"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()