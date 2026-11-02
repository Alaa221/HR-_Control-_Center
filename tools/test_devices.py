"""اختبار الاتصال بكل ماكينة في ZKTime وتحديد سبب الفشل بدقة.

التشغيل (من مجلد hr_web):   python tools/test_devices.py
بيطبع جدول (وبيحفظه في test_devices.csv) فيه لكل جهاز:
  - TCP : هل بورت الجهاز مفتوح من جهازك؟
  - pyzk: هل نجح الاتصال بالبروتوكول (TCP أو UDP) وكام بصمة على الجهاز؟
ابعتي لي الجدول كله.
"""
import csv
import os
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import zk_sync as Z  # noqa: E402
from zk import ZK  # noqa: E402


def tcp(ip, port, t=6):
    t0 = time.time()
    try:
        with socket.create_connection((ip, port), timeout=t):
            return True, f"مفتوح ({int((time.time() - t0) * 1000)}ms)"
    except Exception as e:  # noqa: BLE001
        return False, f"مقفول: {type(e).__name__}"


def try_zk(ip, port, pw, udp):
    z = ZK(ip, port=port, timeout=15, password=pw, force_udp=udp, ommit_ping=True)
    c = z.connect()
    try:
        n = len(c.get_attendance() or [])
        return f"نجح ({'UDP' if udp else 'TCP'}) — {n} بصمة"
    finally:
        try:
            c.disconnect()
        except Exception:  # noqa: BLE001
            pass


def check(args):
    m, alts = args
    ok, t = tcp(m["ip"], m["port"])
    pws = []
    for p in [m["password"]] + alts:
        if p not in pws:
            pws.append(p)
    res = "—"
    for udp in ((False, True) if ok else (True,)):
        for pw in pws:
            try:
                res = try_zk(m["ip"], m["port"], pw, udp)
                return dict(name=m["name"], ip=m["ip"], tcp=t, pyzk=res + (f" [pw={pw}]" if pw else ""))
            except Exception as e:  # noqa: BLE001
                res = f"فشل ({'UDP' if udp else 'TCP'}): {str(e)[:70]}"
    return dict(name=m["name"], ip=m["ip"], tcp=t, pyzk=res)


if __name__ == "__main__":
    ms = Z.list_machines()
    jobs = [(m, [x["password"] for x in ms if x["ip"] == m["ip"] and x is not m]) for m in ms]
    print(f"بختبر {len(ms)} جهاز... (ممكن ياخد دقيقة أو اتنين)\n")
    with ThreadPoolExecutor(max_workers=10) as ex:
        rows = list(ex.map(check, jobs))
    rows.sort(key=lambda r: ("نجح" not in r["pyzk"], r["name"]))
    for r in rows:
        print(f'{r["name"]:<22} {r["ip"]:<17} TCP:{r["tcp"]:<24} {r["pyzk"]}')
    with open("test_devices.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["name", "ip", "tcp", "pyzk"])
        w.writeheader()
        w.writerows(rows)
    print(f'\nنجح {sum("نجح" in r["pyzk"] for r in rows)} من {len(rows)} — النتيجة محفوظة في test_devices.csv')
