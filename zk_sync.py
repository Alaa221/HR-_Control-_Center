"""سحب البصمات من أجهزة ZK مباشرة وحفظها في ATT2000.MDB (نفس قاعدة ZKTime 5.0).

- الأجهزة بتتقرا من جدول Machines في الـ MDB (نفس اللي ZKTime شغال بيه).
- محرك في الخلفية بيعدّي على كل الأجهزة كل `sync_seconds` ثانية (بالتوازي) ويضيف البصمات الجديدة بس.
- التكرار بيتمنع بمقارنة (الموظف + وقت البصمة) فمفيش تكرار مع اللي ZKTime نزّله.
- الأجهزة اللي مش بترد بيتأخر إعادة المحاولة معاها تدريجيًا علشان ما تعطّلش الباقي.
"""
from __future__ import annotations

import datetime as dt
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from att_config import SETTINGS as S, new_code
import local_time

try:                                   # بدون pooling: الاتصال بالقراءة فقط والكتابة بيتعارضوا على نفس ملف Access
    import pyodbc as _pyodbc
    _pyodbc.pooling = False
except Exception:                      # noqa: BLE001
    pass

_wlock = threading.Lock()          # كتابة واحدة في الوقت على الـ MDB
_slock = threading.Lock()          # حماية جدول الحالة
STATUS: dict[str, dict] = {}       # key -> حالة الجهاز
_state = {"machine_cols": [], "enabled": False, "running": False, "next_run": None, "last_sweep": None, "thread": None}
_wake = threading.Event()


class SyncError(Exception):
    pass


# ───────────────────────── الاتصال بالـ MDB (قراءة + كتابة) ─────────────────────────
def _connect_rw():
    import pyodbc  # type: ignore
    path = S["access_path"]
    if not os.path.exists(path):
        raise SyncError(f"ملف ZKTime مش موجود: {path}")
    drv = next((d for d in pyodbc.drivers() if "Microsoft Access Driver" in d), None)
    if not drv:
        raise SyncError("مفيش Microsoft Access ODBC Driver (نزّلي Access Database Engine بنفس نوع بايثون).")
    cs = f"DRIVER={{{drv}}};DBQ={path};ReadOnly=0;Exclusive=0;"
    if S.get("access_password"):
        cs += f"PWD={S['access_password']};"
    last = None
    for i in range(5):                 # Access ساعات بيرفض الاتصال لحظيًا (08004) لو الملف مشغول
        try:
            return pyodbc.connect(cs, timeout=15)
        except pyodbc.Error as e:
            last = e
            if not any(k in str(e) for k in ("08004", "already in use", "locked", "lock")):
                break
            time.sleep(0.4 * (i + 1))
    raise SyncError(f"ملف ZKTime مشغول أو مقفول: {str(last)[:120]}")


# ───────────────────────── الأجهزة ─────────────────────────
def _norm(name: str) -> str:
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def list_machines() -> list[dict]:
    """كل الأجهزة الفعلية، مع الاحتفاظ بكل New Code كسطر عرض مستقل."""
    cn = _connect_rw()
    try:
        cur = cn.cursor()
        cur.execute("SELECT * FROM Machines")
        raw_cols = [c[0] for c in cur.description]
        cols = [_norm(c) for c in raw_cols]          # "New Code" / "New_Code" / "NewCode" كلها بتتقرا "newcode"
        _state["machine_cols"] = raw_cols
        devices = {}
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            ip = str(d.get("ip") or "").strip()
            if not ip:
                continue
            num = d.get("machinenumber")
            sn = str(d.get("sn") or "").strip()
            key = sn or (f"#{num}" if num is not None else ip)
            machine = devices.get(key)
            alias = str(d.get("machinealias") or "").strip()
            if machine is not None:
                code = new_code(d.get("id"), d.get("newcode"))
                if code and code not in machine["names"]:
                    machine["names"].append(code)
                if code and alias:
                    machine["aliases"].setdefault(code, alias)
                continue
            pw = str(d.get("commpassword") or "").strip()
            machine = dict(key=key, sn=sn, number=num, ip=ip, port=int(d.get("port") or 4370),
                            password=int(pw) if pw.isdigit() else 0,
                            name=key, names=[], aliases={},
                            enabled=bool(d.get("enabled", True)))
            code = new_code(d.get("id"), d.get("newcode"))
            if code:
                machine["names"].append(code)
                if alias:
                    machine["aliases"][code] = alias
            devices[key] = machine
        out = []
        for machine in devices.values():
            machine["names"] = machine["names"] or [machine["key"]]
            machine["name"] = machine["names"][0]
            out.append(machine)
        return out
    finally:
        cn.close()


# ───────────────────────── سحب جهاز واحد ─────────────────────────
def _pull(ip: str, port: int, password: int = 0, alt: list | None = None, last_count: int | None = None):
    """بيرجّع (البصمات أو None لو مفيش جديد، عدد السجلات على الجهاز)."""
    try:
        from zk import ZK  # type: ignore
    except ImportError as e:
        raise SyncError("مكتبة pyzk مش متثبتة:  pip install pyzk") from e
    # كلمة سر الاتصال من ZKTime (CommPassword) الأول، وبعدها كلمات سر الأجهزة اللي على نفس الـ IP، وبعدها sync_passwords
    pws: list[int] = []
    for p in [password] + list(alt or []) + [int(x) for x in S.get("sync_passwords", []) if str(x).isdigit()]:
        if p not in pws:
            pws.append(p)
    timeout = int(S.get("sync_timeout", 20))
    auth_failed = False
    for pw in pws:
        for attempt in (1, 2):                    # محاولة تانية لو الجهاز بطيء (timed out)
            # ommit_ping=True: مفيش ICMP ping (كتير من الراوترات بتمنعه رغم إن بورت الجهاز شغال، وZKTime مش بيعتمد عليه)
            zk = ZK(ip, port=port, timeout=timeout, password=pw, force_udp=False,
                    ommit_ping=not S.get("sync_ping", False))
            try:
                conn = zk.connect()
            except Exception as e:  # noqa: BLE001
                if "uthenticat" in str(e):
                    auth_failed = True
                    break                         # كلمة السر غلط → جرّب اللي بعدها
                if attempt == 1 and "timed out" in str(e).lower():
                    continue
                raise
            try:
                try:                              # عدد السجلات على الجهاز (سريع) — لو ما اتغيرش مش بنحمّل حاجة
                    conn.read_sizes()
                    count = getattr(conn, "records", None)
                except Exception:  # noqa: BLE001
                    count = None
                if count is not None and last_count is not None and count == last_count:
                    return None, count
                logs = conn.get_attendance() or []
                return logs, (count if count is not None else len(logs))
            except Exception as e:  # noqa: BLE001
                if attempt == 1 and "timed out" in str(e).lower():
                    continue
                raise
            finally:
                try:
                    conn.disconnect()
                except Exception:
                    pass
    if auth_failed:
        raise SyncError("الجهاز رفض كلمة سر الاتصال (Unauthenticated) — راجعي Machines.CommPassword")
    raise SyncError("تعذر الاتصال بالجهاز")


def _save(m: dict, logs) -> tuple[int, int]:
    """بيضيف البصمات الجديدة. بيرجّع (الجديد، موظفين مش موجودين في USERINFO)."""
    limit = local_time.now_naive() + dt.timedelta(days=1)     # تجاهل بصمات بتاريخ مستقبلي (ساعة الجهاز غلط)
    days = int(S.get("sync_backfill_days", 31))               # الأقدم من كده ZKTime نزّله قبل كده (0 = كل التاريخ)
    floor = local_time.now_naive() - dt.timedelta(days=days) if days else dt.datetime.min
    logs = [l for l in logs if l.timestamp and floor <= l.timestamp <= limit]
    if not logs:
        return 0, 0
    sensor = str(m["number"]) if m["number"] is not None else "1"
    sn = m["sn"] or None
    min_ts = min(l.timestamp for l in logs).replace(microsecond=0)
    new = unknown = 0
    with _wlock:
        cn = _connect_rw()
        try:
            cur = cn.cursor()
            cur.execute("SELECT USERID, Badgenumber FROM USERINFO")
            badge = {str(r.Badgenumber).strip(): r.USERID for r in cur.fetchall()}
            cur.execute("SELECT USERID, CHECKTIME FROM CHECKINOUT WHERE CHECKTIME >= ?", min_ts)
            have = {(str(r.USERID), r.CHECKTIME) for r in cur.fetchall()}
            for l in logs:
                uid = badge.get(str(l.user_id).strip())
                if uid is None:
                    unknown += 1
                    continue
                ts = l.timestamp.replace(microsecond=0)
                if (str(uid), ts) in have:
                    continue
                typ = "I" if getattr(l, "punch", 0) == 0 else "O"
                cur.execute("INSERT INTO CHECKINOUT (USERID, CHECKTIME, CHECKTYPE, SENSORID, sn) VALUES (?,?,?,?,?)",
                            uid, ts, typ, sensor, sn)
                have.add((str(uid), ts))
                new += 1
            cn.commit()
        finally:
            cn.close()
    return new, unknown


def sync_one(m: dict) -> None:
    key = m["key"]
    with _slock:
        st = STATUS.setdefault(key, dict(key=key, fails=0, total_new=0, last_ok=None, next_try=0, new=0, error=None))
        st.update(name=m["name"], ip=m["ip"], port=m["port"], busy=True, last_try=_now())
    try:
        logs, count = _pull(m["ip"], m["port"], m.get("password", 0), m.get("alt_pw"), st.get("rec"))
        new, unknown = _save(m, logs) if logs else (0, 0)
        with _slock:
            st.update(state="ok", busy=False, error=None, fails=0, new=new, unknown=unknown, device_count=count,
                      rec=count, total_new=st["total_new"] + new, last_ok=_now(), next_try=0)
    except Exception as e:  # noqa: BLE001 — أي خطأ بيتسجّل في حالة الجهاز بس
        with _slock:
            fails = st["fails"] + 1
            wait = min(600, int(S.get("sync_seconds", 60)) * (2 ** min(fails, 4)))   # تأخير تدريجي لحد 10 دقايق
            st.update(state="err", busy=False, error=str(e).replace("\n", " ")[:200], fails=fails, new=0,
                      next_try=time.time() + wait)


def _now() -> str:
    return local_time.now_naive().strftime("%Y-%m-%d %H:%M:%S")


# ───────────────────────── المحرك ─────────────────────────
def sweep(force: bool = False) -> None:
    if _state["running"]:
        return
    _state["running"] = True
    try:
        ms = [m for m in list_machines() if m["enabled"]]
        now = time.time()
        todo = [m for m in ms if force or STATUS.get(m["key"], {}).get("next_try", 0) <= now]
        with _slock:                                   # الأجهزة الجديدة تظهر فورًا في الواجهة
            for m in ms:
                status = STATUS.setdefault(m["key"], dict(key=m["key"], state="wait", fails=0, total_new=0,
                                                         last_ok=None, next_try=0, new=0, error=None))
                status.update(name=m["name"], names=m["names"], aliases=m.get("aliases", {}), ip=m["ip"], port=m["port"])
        # الأجهزة اللي على نفس الـ IP:Port بتتسحب ورا بعض (الجهاز بيقبل اتصال واحد في الوقت)، وبتتبادل كلمات السر
        groups: dict[tuple, list] = {}
        for m in todo:
            groups.setdefault((m["ip"], m["port"]), []).append(m)
        for g in groups.values():
            for m in g:
                m["alt_pw"] = [x["password"] for x in g if x is not m]

        def run_group(g):
            for m in g:
                sync_one(m)

        with ThreadPoolExecutor(max_workers=int(S.get("sync_workers", 8))) as ex:
            list(ex.map(run_group, groups.values()))
        _state["last_sweep"] = _now()
    except Exception as e:  # noqa: BLE001
        _state["last_error"] = str(e)[:200]
    finally:
        _state["running"] = False


def _loop() -> None:
    while True:
        if _state["enabled"]:
            _state["last_error"] = None
            sweep(force=_wake.is_set())
        _wake.clear()
        every = int(S.get("sync_seconds", 60))
        _state["next_run"] = time.time() + every
        _wake.wait(every)


def start() -> None:
    if _state["thread"] or S.get("mode") == "demo" or S.get("source") != "access":
        return
    _state["enabled"] = bool(S.get("sync_enabled", True))
    t = threading.Thread(target=_loop, name="zk-sync", daemon=True)
    _state["thread"] = t
    t.start()


def run_now() -> None:
    _state["enabled"] = True
    _wake.set()


def set_enabled(on: bool) -> None:
    _state["enabled"] = bool(on)
    if on:
        _wake.set()


def snapshot() -> dict:
    with _slock:
        physical_ms = sorted((dict(v) for v in STATUS.values()),
                             key=lambda x: (x["state"] != "ok", x.get("name", "")))
    for m in physical_ms:
        m["next_try"] = max(0, int(m.get("next_try", 0) - time.time())) if m.get("next_try") else 0
    ms = [dict(m, name=name, alias=(m.get("aliases") or {}).get(name, "")) for m in physical_ms for name in m.get("names", [m["name"]])]
    return dict(
        available=_state["thread"] is not None, enabled=_state["enabled"], running=_state["running"],
        every=int(S.get("sync_seconds", 60)), last_sweep=_state["last_sweep"], error=_state.get("last_error"),
        next_in=max(0, int((_state["next_run"] or 0) - time.time())) if _state["enabled"] and _state["next_run"] else None,
        ok=sum(m["state"] == "ok" for m in physical_ms),
        err=sum(m["state"] == "err" for m in physical_ms), total=len(physical_ms),
        new=sum(m.get("new", 0) for m in physical_ms), machines=ms,
        no_code=bool(physical_ms) and not any(m.get("aliases") or (m.get("names") and m["names"] != [m["key"]]) for m in physical_ms),
        cols=_state.get("machine_cols") or [],
    )
