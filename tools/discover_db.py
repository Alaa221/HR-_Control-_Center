"""يعرض قواعد البيانات والجداول اللي شكلها بتاع مكن بصمة، عشان نعرف الـ preset الصح.

التشغيل (من فولدر hr_web):
    python tools/discover_db.py              # يعرض كل القواعد + الجداول المحتملة
    python tools/discover_db.py MyZKDatabase # يركّز على قاعدة معينة
ابعتيلي الناتج لو محتاجة نظبط الأعمدة.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pyodbc  # noqa: E402

from att_config import SETTINGS as S  # noqa: E402
from attendance import _conn_str  # noqa: E402

KEYS = ("checkinout", "transaction", "punch", "userinfo", "machine", "iclock", "terminal", "attlog", "employee", "device")


def connect(db=None):
    S["database"] = db or "master"
    for trusted in (False, True):
        try:
            return pyodbc.connect(_conn_str(pyodbc, trusted), timeout=8)
        except pyodbc.Error as e:
            err = e
    sys.exit(f"تعذر الاتصال: {err}")


cn = connect()
dbs = [r[0] for r in cn.cursor().execute(
    "SELECT name FROM sys.databases WHERE database_id > 4 ORDER BY name")]
print("قواعد البيانات:", dbs or "— مفيش —")
for db in ([sys.argv[1]] if len(sys.argv) > 1 else dbs):
    try:
        c = connect(db).cursor()
    except SystemExit:
        continue
    tabs = [r[0] + "." + r[1] for r in c.execute(
        "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'")]
    hits = [t for t in tabs if any(k in t.lower() for k in KEYS)]
    print(f"\n=== {db}  ({len(tabs)} جدول، منهم {len(hits)} محتمل) ===")
    for t in hits:
        sch, name = t.split(".")
        cols = [r[0] + " " + r[1] for r in c.execute(
            "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=? AND TABLE_NAME=?", sch, name)]
        try:
            n = c.execute(f"SELECT COUNT(*) FROM [{sch}].[{name}]").fetchone()[0]
        except Exception:
            n = "?"
        print(f"\n[{t}]  rows={n}\n  cols: {', '.join(cols)}")
        try:
            for r in c.execute(f"SELECT TOP 2 * FROM [{sch}].[{name}]").fetchall():
                print("  e.g.", [str(v)[:24] for v in r][:12])
        except Exception:
            pass
