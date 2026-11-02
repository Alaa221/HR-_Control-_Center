"""سحب بصمات الحضور مباشرة (Live) من قاعدة SQL Server اللي عليها داتا مكن ZK.

- بيقرأ من القاعدة وقت الطلب، فمفيش داعي تنزّلي ملفات من الـ ZK كل شوية.
- ملف att_config.py فيه بيانات الاتصال وشكل الجداول.
- وضع ATT_MODE=demo بيولّد بصمات وهمية للمعاينة فقط.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import random
import threading
import time

import pandas as pd

from att_config import ACCESS_SQL, PRESETS, SETTINGS as S, new_code
import local_time

COLS = ["emp_code", "punch_time", "machine", "state"]


class AttendanceError(Exception):
    """رسالة واضحة تتعرض للمستخدم بدل الـ stack trace."""


# ───────────────────────── الاتصال ─────────────────────────
def _pyodbc():
    try:
        import pyodbc  # type: ignore
        return pyodbc
    except ImportError as e:  # pragma: no cover
        raise AttendanceError("مكتبة pyodbc غير مثبتة.:  pip install pyodbc") from e


def _driver(pyodbc) -> str:
    have = pyodbc.drivers()
    for pref in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server",
                 "ODBC Driver 13.1 for SQL Server", "ODBC Driver 13 for SQL Server",
                 "SQL Server Native Client 11.0"):
        if pref in have:
            return pref
    raise AttendanceError(
        "مفيش ODBC Driver لـ SQL Server على الجهاز. نزّلي 'ODBC Driver 17 for SQL Server' من موقع مايكروسوفت.")


def _conn_str(pyodbc, trusted: bool) -> str:
    parts = [f"DRIVER={{{_driver(pyodbc)}}}", f"SERVER={S['server']}"]
    if S["database"]:
        parts.append(f"DATABASE={S['database']}")
    parts += ["Trusted_Connection=yes"] if trusted else [f"UID={S['user']}", f"PWD={S['password']}"]
    parts += ["TrustServerCertificate=yes", "Encrypt=no", "Connection Timeout=8"]
    return ";".join(parts)


def _is_access() -> bool:
    return S.get("source", "sqlserver") == "access"


def _connect_access():
    import os
    import platform
    pyodbc = _pyodbc()
    path = S["access_path"]
    if not os.path.exists(path):
        raise AttendanceError(f"ملف ZKTime مش موجود في المسار: {path}")
    drv = next((d for d in pyodbc.drivers() if "Microsoft Access Driver" in d), None)
    if not drv:
        raise AttendanceError(
            "مفيش Microsoft Access ODBC Driver على الجهاز. نزّلي 'Microsoft Access Database Engine 2016 Redistributable' "
            f"بنفس نوع بايثون ({platform.architecture()[0]}) — لو Office 32-bit ونسخة بايثون 64-bit ثبّتيه بـ /quiet.")
    cs = f"DRIVER={{{drv}}};DBQ={path};ReadOnly=1;Exclusive=0;"
    if S.get("access_password"):
        cs += f"PWD={S['access_password']};"
    try:
        return pyodbc.connect(cs, timeout=10, autocommit=True)
    except pyodbc.Error as e:
        raise AttendanceError(f"تعذر فتح ملف ZKTime: {_short(e)}") from e


def connect():
    if _is_access():
        return _connect_access()
    pyodbc = _pyodbc()
    if not S["database"]:
        raise AttendanceError("اسم قاعدة البيانات فاضي. اكتبيه في att_config.py (database) — "
                              "ولو مش فاكراه شغّلي:  python tools/discover_db.py")
    try:
        return pyodbc.connect(_conn_str(pyodbc, False), timeout=8)
    except pyodbc.Error as e1:
        if S.get("try_windows_auth_fallback"):
            try:
                return pyodbc.connect(_conn_str(pyodbc, True), timeout=8)
            except pyodbc.Error:
                pass
        raise AttendanceError(f"تعذر الاتصال بالقاعدة ({S['server']}): {_short(e1)}") from e1


def _short(e: Exception) -> str:
    s = str(e).replace("\n", " ")
    return s[:260]


def _discover_access(sample: int) -> list[dict]:
    out = []
    with connect() as cn:
        cur = cn.cursor()
        for t in [r.table_name for r in cur.tables(tableType="TABLE")]:
            cols = [f"{c.column_name} ({c.type_name})" for c in cn.cursor().columns(table=t)]
            row = {"table": t, "rows": None, "cols": cols, "hit": any(k in t.lower() for k in KEYS), "sample": []}
            try:
                row["rows"] = int(cn.cursor().execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0])
                if row["hit"] and row["rows"]:
                    row["sample"] = [[str(v)[:28] for v in r][:14]
                                     for r in cn.cursor().execute(f"SELECT TOP {sample} * FROM [{t}]").fetchall()]
            except Exception:
                pass
            out.append(row)
    out.sort(key=lambda r: (not r["hit"], -(r["rows"] or 0)))
    return out


def _code_variants(code: str) -> list[str]:
    """00123 / 0123 / 123 كلها نفس الموظف — بنبعت كل الأشكال المحتملة للاستعلام (أحرف وأرقام بس، للأمان)."""
    import re
    c = re.sub(r"[^0-9A-Za-z]", "", str(code))
    base = c.lstrip("0") or c
    return [base] + ["0" * k + base for k in range(1, 9)] if base else []


def _query_access(start, end, machine, emp=None) -> pd.DataFrame:
    f = "#%m/%d/%Y %H:%M:%S#"
    extra = ""
    if emp:
        extra = " AND (u.Badgenumber & '') IN (%s)" % ", ".join("'%s'" % v for v in _code_variants(emp))
    sql = ACCESS_SQL.format(top=int(S["max_rows"]), start=dt.datetime.combine(start, dt.time.min).strftime(f),
                            end=dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min).strftime(f), extra=extra)
    try:
        with connect() as cn:
            cur = cn.cursor()
            cur.execute(sql)
            rows = [tuple(r) for r in cur.fetchall()]
    except AttendanceError:
        raise
    except Exception as e:
        raise AttendanceError(f"فشل قراءة بصمات ZKTime ({_short(e)}) — افتحي صفحة /attendance/schema وابعتيلي الجداول.") from e
    df = pd.DataFrame(rows, columns=["emp_code", "punch_time", "sn", "sensor", "state"])
    names_sn, names_num = _machine_names()
    df["machine"] = [names_sn.get(sn) or names_num.get(sen) or (sen or "—")
                     for sn, sen in zip(df["sn"].astype(str).str.strip(), df["sensor"].astype(str).str.strip())]
    df = df[COLS]
    if machine:
        df = df[df["machine"].astype("string") == machine]
    return df


def _machines_rows(cn, wanted: tuple[str, ...]) -> list[tuple]:
    """بيقرا جدول Machines ويرجّع الأعمدة المطلوبة بغض النظر عن شكل اسم العمود (New Code / New_Code / NewCode)."""
    cur = cn.cursor()
    cur.execute("SELECT * FROM Machines")
    idx = {"".join(ch for ch in c[0].lower() if ch.isalnum()): i for i, c in enumerate(cur.description)}
    out = []
    for r in cur.fetchall():
        row = {w: (r[idx[w]] if w in idx else None) for w in set(wanted) | {"id", "newcode"}}
        row["newcode"] = new_code(row["id"], row["newcode"])      # الكود من إعدادات البرنامج (MACHINE_CODES) بالـ ID
        out.append(tuple(row[w] for w in wanted))
    return out


def registered_machines() -> list[str]:
    """أكواد New Code للأجهزة المسجلة حتى لو معليهاش بصمات في الفترة."""
    if S["mode"] == "demo" or not _is_access():
        return []
    key = ("registered", S["mode"])
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < 120:
            return hit[1]
    try:
        with connect() as cn:
            rows = _machines_rows(cn, ("sn", "machinenumber", "newcode", "ip"))
    except Exception:
        return []
    codes_by_sn: dict[str, set[str]] = {}
    standalone_codes = set()
    for sn, num, nc, ip in rows:
        if not str(ip or "").strip():
            continue
        serial = str(sn or "").strip()
        code = str(nc or "").strip()
        if serial:
            codes_by_sn.setdefault(serial, set())
            if code:
                codes_by_sn[serial].add(code)
        elif code:
            standalone_codes.add(code)
        else:
            standalone_codes.add(f"#{num}")
    out = set(standalone_codes)
    for serial, codes in codes_by_sn.items():
        out.add(" / ".join(sorted(codes)) if codes else serial)
    out = sorted(out)
    with _lock:
        _cache[key] = (now, out)
    return out


def _machine_names() -> tuple[dict, dict]:
    """أكواد New Code حسب الرقم التسلسلي، وبحسب MachineNumber لو كان فريدًا."""
    key = ("machine_names", S.get("mode"), S.get("source"), S.get("access_path"))
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < 120:
            return hit[1], hit[2]
    try:
        with connect() as cn:
            rows = _machines_rows(cn, ("sn", "machinenumber", "newcode"))
    except Exception:
        return {}, {}
    codes_by_sn: dict[str, set[str]] = {}
    codes_by_num: dict[str, set[str]] = {}
    for sn, num, nc in rows:
        code = str(nc or "").strip()
        if not code:
            continue
        serial = str(sn or "").strip()
        if serial:
            codes_by_sn.setdefault(serial, set()).add(code)
        n = str(num).strip() if num is not None else ""
        if n:
            codes_by_num.setdefault(n, set()).add(code)
    by_sn = {sn: " / ".join(sorted(codes)) for sn, codes in codes_by_sn.items()}
    by_num = {num: next(iter(codes)) for num, codes in codes_by_num.items() if len(codes) == 1}
    with _lock:
        _cache[key] = (now, by_sn, by_num)
    return by_sn, by_num


# ───────────────────────── الاستعلام ─────────────────────────
KEYS = ("checkinout", "transaction", "punch", "userinfo", "machine", "iclock", "terminal", "attlog", "device", "att_")


def _tables() -> list[tuple[str, str]]:
    if _is_access():
        with connect() as cn:
            return [("", r.table_name) for r in cn.cursor().tables(tableType="TABLE")]
    with connect() as cn:
        cur = cn.cursor()
        cur.execute("SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'")
        return [(r[0], r[1]) for r in cur.fetchall()]


def _resolve(tabs: list[tuple[str, str]]) -> tuple[str, str]:
    """بيدوّر على جداول ZK المعروفة ويرجّع (اسم الـ preset, الـ schema)."""
    low = {n.lower(): (sch, n) for sch, n in tabs}
    if "iclock_transaction" in low:
        return "zkbiotime", low["iclock_transaction"][0]
    if "checkinout" in low and "userinfo" in low:
        return "zktime", low["checkinout"][0]
    raise AttendanceError(
        "الجداول المعروفة (iclock_transaction أو CHECKINOUT+USERINFO) مش موجودة في القاعدة '%s'. "
        "افتحي صفحة /attendance/schema عشان تشوفي الجداول الموجودة وتختاري منها." % S["database"])


_preset_cache: dict = {}


def _base_sql() -> str:
    preset = S["preset"]
    if preset == "custom":
        return S["custom_sql"].strip().rstrip(";")
    schema = "dbo"
    if preset == "auto":
        hit = _preset_cache.get("v")
        if not hit or time.time() - hit[0] > 120:
            hit = (time.time(), _resolve(_tables()))
            _preset_cache["v"] = hit
        preset, schema = hit[1]
    sql = PRESETS.get(preset)
    if not sql:
        raise AttendanceError(f"preset غير معروف: {preset}")
    return sql.replace("dbo.", f"[{schema}].").strip().rstrip(";")


def discover(sample: int = 2) -> list[dict]:
    """قايمة الجداول (المرشّحة للمكن أولًا) بأعمدتها وكام صف عينة — لصفحة /attendance/schema."""
    if _is_access():
        return _discover_access(sample)
    with connect() as cn:
        cur = cn.cursor()
        cur.execute("SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
                    "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION")
        cols: dict = {}
        for sch, tb, c, ty in cur.fetchall():
            cols.setdefault((sch, tb), []).append(f"{c} ({ty})")
        counts = {}
        try:
            cur.execute("SELECT s.name, t.name, SUM(p.row_count) FROM sys.dm_db_partition_stats p "
                        "JOIN sys.tables t ON t.object_id=p.object_id JOIN sys.schemas s ON s.schema_id=t.schema_id "
                        "WHERE p.index_id IN (0,1) GROUP BY s.name, t.name")
            counts = {(a, b): int(n) for a, b, n in cur.fetchall()}
        except Exception:
            pass
        out = []
        for (sch, tb), cs in cols.items():
            hit = any(k in tb.lower() for k in KEYS)
            row = {"table": f"{sch}.{tb}", "rows": counts.get((sch, tb)), "cols": cs, "hit": hit, "sample": []}
            if hit and (row["rows"] or 0) > 0:
                try:
                    cur.execute(f"SELECT TOP ({sample}) * FROM [{sch}].[{tb}]")
                    row["sample"] = [[str(v)[:28] for v in r][:14] for r in cur.fetchall()]
                except Exception:
                    pass
            out.append(row)
    out.sort(key=lambda r: (not r["hit"], -(r["rows"] or 0)))
    return out


_cache: dict = {}
_lock = threading.Lock()


def _norm_code(s: pd.Series) -> pd.Series:
    s = s.astype("string").str.strip()
    return s.str.lstrip("0") if S["strip_leading_zeros"] else s


def _state(v) -> str | None:
    v = str(v).strip().upper() if v is not None and not pd.isna(v) else ""
    if v in ("0", "I", "IN", "4"):     # 4 = Overtime In في بعض الأجهزة
        return "in"
    if v in ("1", "O", "OUT", "5"):
        return "out"
    return None


def dst_correct(ts: pd.Series) -> pd.Series:
    """تصحيح التوقيت الصيفي: بصمات فترة الصيف (حسب توقيت القاهرة) بيتضاف عليها dst_offset_minutes، والشتوي زي ما هو.

    التحول بيحصل عند منتصف الليل (آخر جمعة أبريل ← آخر خميس أكتوبر)، فالقرار بيتاخد باليوم (الساعة 12 ظهرًا)؛
    وده بيتفادى مشكلة الساعة المكررة/المفقودة ليلة التحول.
    """
    off = int(S.get("dst_offset_minutes", -60))
    if not off or ts.empty:
        return ts
    days = ts.dt.normalize()
    summer = {d: bool(pd.Timestamp(d).to_pydatetime().replace(hour=12, tzinfo=local_time.CAIRO).dst())
              for d in days.unique()}
    return ts + days.map(summer).astype(bool).map({True: pd.Timedelta(minutes=off), False: pd.Timedelta(0)})


def _dst_active() -> bool:
    return S["mode"] != "demo" and bool(S.get("dst_fix", True)) and bool(int(S.get("dst_offset_minutes", -60)))


def fetch(start: dt.date, end: dt.date, machine: str | None = None, emp: str | None = None) -> pd.DataFrame:
    """بصمات من start لحد end (شامل) — مرتبة من الأحدث للأقدم. emp = كود موظف واحد (للتقرير الشهري)."""
    key = (start, end, machine or "", S["mode"], emp or "")
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < S["cache_seconds"]:
            return hit[1]
    fix = _dst_active()
    if S["mode"] == "demo":
        df = _demo(start, end, machine)
    else:    # بنوسّع الاستعلام يوم من كل ناحية لأن التصحيح بيحرّك البصمات عبر منتصف الليل، وبعدين نقص على المدى المطلوب
        pad = dt.timedelta(days=1) if fix else dt.timedelta(0)
        df = _query(start - pad, end + pad, machine, emp)
    df = df.dropna(subset=["punch_time"]).copy()
    df["punch_time"] = pd.to_datetime(df["punch_time"])
    if fix:
        df["punch_time"] = dst_correct(df["punch_time"])
        d = df["punch_time"].dt.date
        df = df[(d >= start) & (d <= end)].copy()
    df["emp_code"] = df["emp_code"].astype("string").str.strip()
    df["key"] = _norm_code(df["emp_code"])
    df["machine"] = df["machine"].astype("string").fillna("—").str.strip()
    df["dir"] = df["state"].map(_state)
    df = df.sort_values("punch_time", ascending=False).reset_index(drop=True)
    with _lock:
        _cache[key] = (now, df)
        if len(_cache) > 40:
            _cache.pop(next(iter(_cache)))
    return df


def fetch_range(start: dt.date, end: dt.date) -> pd.DataFrame:
    """بصمات كل الموظفين من start لحد end بدون ما الحد الأقصى (max_rows) يقص بصمات بصمت.

    الاستعلام الواحد ليه سقف (max_rows). لو سحبنا شهر كامل لكل الشركة مرة واحدة ممكن السقف يتعدّى
    فتضيع أقدم البصمات وتظهر غيابات وهمية. هنا بنسحب على دفعات صغيرة، ولو دفعة لمست السقف بنقسمها
    نصفين لحد يوم واحد؛ ولو يوم واحد لمس السقف بنرفع خطأ صريح بدل ما نرجّع أرقام ناقصة.
    """
    cap = int(S["max_rows"])
    if S["mode"] == "demo":
        return fetch(start, end)

    def part(a: dt.date, b: dt.date) -> list[pd.DataFrame]:
        df = fetch(a, b)
        if len(df) < cap:
            return [df]
        if a == b:
            raise AttendanceError(
                f"عدد البصمات يوم {a} وصل لسقف القراءة ({cap}). ارفعي max_rows في att_config.py عشان الأرقام تبقى دقيقة.")
        mid = a + (b - a) // 2
        return part(a, mid) + part(mid + dt.timedelta(days=1), b)

    parts: list[pd.DataFrame] = []
    d = start
    while d <= end:
        e = min(d + dt.timedelta(days=6), end)
        parts += part(d, e)
        d = e + dt.timedelta(days=1)
    parts = [x for x in parts if len(x)]
    if not parts:
        return fetch(start, start)
    return pd.concat(parts, ignore_index=True).sort_values("punch_time", ascending=False).reset_index(drop=True)


def _query(start, end, machine, emp=None) -> pd.DataFrame:
    if _is_access():
        return _query_access(start, end, machine, emp)
    sql = (f"SELECT TOP ({int(S['max_rows'])}) x.emp_code, x.punch_time, x.machine, "
           f"{'x.state' if _has_state() else 'CAST(NULL AS NVARCHAR(10))'} AS state "
           f"FROM ({_base_sql()}) x WHERE x.punch_time >= ? AND x.punch_time < ?")
    args: list = [dt.datetime.combine(start, dt.time.min), dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min)]
    if machine:
        sql += " AND x.machine = ?"
        args.append(machine)
    if emp:
        vs = _code_variants(emp)
        sql += " AND x.emp_code IN (%s)" % ", ".join("?" * len(vs))
        args += vs
    sql += " ORDER BY x.punch_time DESC"
    try:
        with connect() as cn:
            cur = cn.cursor()
            cur.execute(sql, args)
            rows = cur.fetchall()
            cols = [c[0] for c in cur.description]
    except AttendanceError:
        raise
    except Exception as e:
        raise AttendanceError(f"فشل تنفيذ الاستعلام: {_short(e)}") from e
    df = pd.DataFrame([tuple(r) for r in rows], columns=cols)
    for c in COLS:
        if c not in df:
            df[c] = None
    return df[COLS]


def _has_state() -> bool:
    return S["preset"] != "custom" or "state" in S["custom_sql"].lower()


def machines(days: int = 60) -> list[str]:
    key = ("machines", S["mode"])
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < 300:
            return hit[1]
    today = local_time.today()
    df = fetch(today - dt.timedelta(days=days if S["mode"] != "demo" else 2), today)
    out = sorted(set(df["machine"].dropna().unique().tolist()) | set(registered_machines()))
    with _lock:
        _cache[key] = (now, out)
    return out


def ping() -> tuple[bool, str]:
    """هل الاتصال شغال؟ (للشارة الخضرا/الحمرا)."""
    if S["mode"] == "demo":
        return True, "demo"
    try:
        with connect() as cn:
            if not _is_access():
                cn.cursor().execute("SELECT 1").fetchone()
        return True, "access" if _is_access() else "sql"
    except AttendanceError as e:
        return False, str(e)


# ───────────────────────── بيانات تجريبية ─────────────────────────
_DEMO_MACHINES = {
    "الفجالة": "ZK-Fagalah-01", "مصر الجديدة": "ZK-Heliopolis-01", "القاهرة": "ZK-Main-Gate",
    "مدينة نصر": "ZK-NasrCity-01", "الدقهلية": "ZK-Mansoura-01",
}


def demo_pool(codes_locs: list[tuple[str, str]]):
    _demo.pool = codes_locs  # type: ignore[attr-defined]


def _demo(start: dt.date, end: dt.date, machine) -> pd.DataFrame:
    pool = getattr(_demo, "pool", [])
    now = local_time.now_naive()
    rows = []
    d = start
    while d <= end:
        if d.weekday() != 4:  # الجمعة إجازة
            for code, loc in pool:
                seed = int(hashlib.md5(f"{d}{code}".encode()).hexdigest()[:8], 16)
                r = random.Random(seed)
                if r.random() > .78:      # غياب
                    continue
                mach = _DEMO_MACHINES.get(loc, "ZK-Main-Gate")
                tin = dt.datetime.combine(d, dt.time(7, 40)) + dt.timedelta(minutes=r.randint(0, 150), seconds=r.randint(0, 59))
                tout = dt.datetime.combine(d, dt.time(15, 50)) + dt.timedelta(minutes=r.randint(0, 150), seconds=r.randint(0, 59))
                for t, st in ((tin, "0"), (tout, "1")):
                    if t <= now:
                        rows.append((code, t, mach, st))
                lunch = tin + dt.timedelta(hours=4, minutes=r.randint(0, 40))
                if r.random() < .12 and lunch <= now:     # خروج الغدا
                    rows.append((code, lunch, mach, "1"))
        d += dt.timedelta(days=1)
    df = pd.DataFrame(rows, columns=COLS)
    if machine:
        df = df[df.machine == machine]
    return df