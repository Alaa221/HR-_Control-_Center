"""HR Control Center - Flask web app.

تشغيل:  python app.py   ثم افتحي  http://127.0.0.1:5000
"""
from __future__ import annotations

import datetime as dt
import io
import html
import json
import math
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from urllib import request as url_request

import pandas as pd
from flask import (Flask, Response, abort, make_response, redirect, render_template,
                   request, url_for)

import attendance as A
import report as R
import data as D
import leave_tracker as LT
import zk_sync as ZS
import local_time
from att_config import SETTINGS as AS
from i18n import tr, tv

app = Flask(__name__)
PER_PAGE = 20

# ───────────────────────── تعريف الكروت ─────────────────────────
# key, section, label, color, icon, value-fn, mask-fn, breakdown columns, sort
def _kpis(df):
    a = df
    return [
        # ---- Employees
        dict(key="total", sec="employees", color="#6B6B72", icon="users", value=len(a),
             mask=lambda d: d.index == d.index, bd=["sector", "location", "gender"]),
        dict(key="active", sec="employees", color="#2E7D32", icon="user-check", value=int(a.active.sum()),
             mask=lambda d: d.active, bd=["sector", "location", "gender"]),
        dict(key="inactive", sec="employees", color="#C62828", icon="user-x", value=int((~a.active).sum()),
             mask=lambda d: ~d.active, bd=["sector", "location"]),
        dict(key="probation", sec="employees", color="#EF6C00", icon="hourglass",
             value=int((a.prob_days >= 0).sum()),
             mask=lambda d: d.prob_days >= 0, bd=["prob_status", "sector", "location"], sort=("prob_days", True)),
        dict(key="male", sec="employees", color="#1E5BD8", icon="user", value=int((a.gender == "ذكر").sum()),
             mask=lambda d: d.gender == "ذكر", bd=["sector", "location", "religion"]),
        dict(key="female", sec="employees", color="#D81B60", icon="user", value=int((a.gender == "أنثى").sum()),
             mask=lambda d: d.gender == "أنثى", bd=["sector", "location", "religion"]),
        dict(key="muslim", sec="employees", color="#EF6C00", icon="moon", value=int((a.religion == "مسلم").sum()),
             mask=lambda d: d.religion == "مسلم", bd=["sector", "location", "gender"]),
        dict(key="christian", sec="employees", color="#EF6C00", icon="cross", value=int((a.religion == "مسيحى").sum()),
             mask=lambda d: d.religion == "مسيحى", bd=["sector", "location", "gender"]),
        dict(key="age", sec="employees", color="#1E5BD8", icon="calendar", value=round(float(a.age.mean()), 1), dec=1,
             mask=lambda d: d.age.notna(), bd=["age_band", "sector", "gender"], sort=("age", False)),
        dict(key="turnover", sec="employees", color="#C62828", icon="refresh", value=None),
        dict(key="tenure", sec="employees", color="#6D3FD1", icon="clock", value=round(float(a.tenure.mean()), 1), dec=1,
             mask=lambda d: d.tenure.notna(), bd=["tenure_band", "sector", "location"], sort=("tenure", False)),
        dict(key="vacancies", sec="employees", color="#6B6B72", icon="plus-square", value=None),
        dict(key="leadtime", sec="employees", color="#6B6B72", icon="timer", value=None),
        dict(key="files", sec="employees", color="#2E7D32", icon="folder-check", value=int(a.file_complete.sum()),
             mask=lambda d: d.file_complete, bd=["sector", "location"]),
        # ---- Organization
        dict(key="divisions", sec="org", color="#6D3FD1", icon="building", value=int(a.sector.nunique()), org="sector"),
        dict(key="departments", sec="org", color="#6D3FD1", icon="grid", value=int(a.management.nunique()), org="management"),
        dict(key="sections", sec="org", color="#6D3FD1", icon="layers", value=int(a.department.nunique()), org="department"),
        dict(key="jobs", sec="org", color="#6D3FD1", icon="briefcase", value=int(a.job.nunique()), org="job"),
        # ---- Insurance
        dict(key="insured", sec="ins", color="#2E7D32", icon="shield-check", value=int(a.insured.sum()),
             mask=lambda d: d.insured, bd=["ins_branch", "sector", "location"]),
        dict(key="uninsured", sec="ins", color="#C62828", icon="shield-alert", value=int((~a.insured).sum()),
             mask=lambda d: ~d.insured, bd=["ins_reason", "sector", "location"]),
        dict(key="md_insured", sec="ins", color="#6B6B72", icon="heart", value=None),
        dict(key="md_uninsured", sec="ins", color="#6B6B72", icon="heart", value=None),
    ]


ORG_LEVELS = {"sector": "k_divisions", "management": "k_departments",
              "department": "k_sections", "job": "k_jobs", "location": "by_location"}


# ───────────────────────── مساعدات ─────────────────────────
def lang() -> str:
    return "ar" if request.cookies.get("lang") == "ar" else "en"


@app.context_processor
def inject():
    L = lang()
    al = D.get_alerts()
    badge = int(al.severity.isin(["Critical", "Warning"]).sum())
    top = al[al.severity.isin(["Critical", "Warning"])].head(8)

    def _n(mask):
        return int(mask.sum())

    _prob, _con = al.type == "Probation", al.type == "Contract"
    # ملخص التنبيهات مجمّع حسب النوع (للبوب أب): (مفتاح النص، العدد، الخطورة، الأيقونة، رابط التصفية)
    _groups = [
        ("g_contract_expired", _n((al.msg == "contract_expired")), "c", "file-x",
         dict(type="Contract", severity="Critical")),
        ("g_prob_7", _n(_prob & (al.severity == "Critical")), "c", "hourglass",
         dict(type="Probation", severity="Critical")),
        ("g_prob_30", _n(_prob & (al.severity == "Warning")), "w", "clock",
         dict(type="Probation", severity="Warning")),
        ("g_contract_soon", _n(al.msg == "contract_soon"), "w", "calendar",
         dict(type="Contract", severity="Warning")),
        ("g_docs", _n(al.type == "Documents"), "i", "folder-check", dict(type="Documents")),
        ("g_no_contract", _n(al.msg == "no_contract"), "i", "file", dict(type="Contract", severity="Info")),
    ]
    alert_groups = [dict(key=k, n=n, sev=sv, icon=ic, href=url_for("alerts", **q))
                    for k, n, sv, ic, q in _groups if n]
    return dict(
        alert_groups=alert_groups,
        asset=lambda f: url_for("static", filename=f, v=int((Path(app.static_folder) / f).stat().st_mtime)),
        top_alerts=top.to_dict("records"),
        n_critical=int((al.severity == "Critical").sum()),
        n_warning=int((al.severity == "Warning").sum()),
        L=L, DIR="rtl" if L == "ar" else "ltr", t=lambda k, **kw: tr(k, L, **kw),
        badge=badge, today=D.today().strftime("%Y-%m-%d"),
        nav=[("dashboard", "dashboard", "home"), ("employees", "employees", "users"),
             ("profile_search", "profile", "user"), ("contracts", "contracts", "file"),
             ("probation", "probation", "hourglass"), ("documents", "documents", "folder-check"),
             ("attendance", "attendance", "fingerprint"), ("leaves", "leaves", "calendar"),
             ("alerts", "alerts", "bell")],
        args_without=lambda *drop, **add: {**{k: v for k, v in request.args.items()
                                              if k not in drop and k != "page"}, **add},
    )


@app.template_filter("tv")
def _tv(value, kind):
    return tv(kind, value, lang())


@app.template_filter("fdate")
def _fdate(v):
    return "—" if pd.isna(v) else pd.Timestamp(v).strftime("%Y-%m-%d")


_MON_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MON_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


@app.template_filter("pdate")
def _pdate(v):
    """تاريخ بنفس صيغة الـ DAX: dd MMM yyyy (بالإنجليزي أو العربي)."""
    if v is None or pd.isna(v):
        return None
    v = pd.Timestamp(v)
    mon = (_MON_AR if lang() == "ar" else _MON_EN)[v.month - 1]
    return f"{v.day:02d} {mon} {v.year}"


@app.template_filter("gnum")
def _gnum(v):
    """General Number: 12 أو 12.5 بدون أصفار زيادة."""
    if v is None or pd.isna(v):
        return None
    return str(int(v)) if float(v).is_integer() else f"{float(v):g}"


@app.template_global()
def days_txt(n):
    n = int(n)
    return f"{n} يوم" if lang() == "ar" else f"{n}d"


@app.template_filter("num")
def _num(v, dec=0):
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:,.{dec}f}"


FILTER_COLS = ["sector", "management", "department", "job", "location", "gender", "religion",
               "age_band", "tenure_band", "ins_branch", "ins_reason"]


def apply_filters(df: pd.DataFrame, args) -> pd.DataFrame:
    q = (args.get("q") or "").strip()
    if q:
        m = df["name"].fillna("").str.contains(q, case=False, regex=False) | df["code"].str.contains(q, regex=False)
        df = df[m]
    for c in FILTER_COLS:
        v = args.get(c)
        if v:
            df = df[df[c].astype("string") == v]
    if args.get("prob"):
        df = df[df.prob_status == args["prob"]]
    if args.get("contract"):
        df = df[df.contract_status == args["contract"]]
    if args.get("insured") in ("yes", "no"):
        df = df[df.insured == (args["insured"] == "yes")]
    if args.get("complete") in ("yes", "no"):
        df = df[df.file_complete == (args["complete"] == "yes")]
    if args.get("missing"):
        df = df[df.missing_docs.apply(lambda m: args["missing"] in m)]
    return df


def paginate(df: pd.DataFrame):
    page = max(1, request.args.get("page", 1, type=int))
    pages = max(1, math.ceil(len(df) / PER_PAGE))
    page = min(page, pages)
    return df.iloc[(page - 1) * PER_PAGE: page * PER_PAGE], page, pages


def bars(df, col, top=None, kind=None):
    items = D.breakdown(df, col, top)
    mx = max([c for _, c in items], default=1)
    param = col if col in FILTER_COLS else {"prob_status": "prob"}.get(col)
    return [dict(label=k, count=c, pct=round(c / mx * 100, 1), kind=kind or col, param=param)
            for k, c in items]


@app.template_global()
def alert_msg(a, missing=None):
    L = lang()
    m, n = a["msg"], a["metric"]
    if m == "prob":
        return tr("m_prob_today", L) if n == 0 else tr("m_prob", L, n=n)
    if m == "contract_expired":
        return tr("m_contract_expired", L, n=abs(n))
    if m == "contract_soon":
        return tr("m_contract_soon", L, n=n)
    if m == "no_contract":
        return tr("m_no_contract", L)
    sep = "، " if L == "ar" else ", "
    return tr("m_docs", L, list=sep.join(tv("doc", k, L) for k in (missing or [])))


def csv_response(df: pd.DataFrame, name: str):
    cols = ["code", "name", "job", "department", "management", "sector", "location", "hire_date",
            "prob_status", "contract_status", "contract_end", "insurance_label", "file_pct"]
    out = df[cols].copy()
    for c in ["hire_date", "contract_end"]:
        out[c] = out[c].dt.strftime("%Y-%m-%d")
    buf = io.StringIO()
    out.to_csv(buf, index=False)
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}.csv"})


def list_page(df, *, title, subtitle="", back=None, summary=None, breakdowns=None, filters=True,
              sort=None, csv_name="employees", extra=None, cols=None):
    df = apply_filters(df, request.args)
    if sort:
        df = df.sort_values(sort[0], ascending=sort[1], na_position="last")
    if request.args.get("export") == "csv":
        return csv_response(df, csv_name)
    rows, page, pages = paginate(df)
    full = D.get_df()
    opts = {c: [(v, v) for v in sorted(full[c].dropna().astype(str).unique())] for c in ("sector", "location")}
    return render_template("list.html", title=title, subtitle=subtitle, back=back, summary=summary or [],
                           breakdowns=breakdowns or [], rows=rows.to_dict("records"), total=len(df),
                           page=page, pages=pages, filters=filters, opts=opts, extra=extra or [],
                           cols=cols or ["code", "name", "job", "management", "location", "hire_date",
                                         "prob_status", "contract_status", "file_pct"])


# ───────────────────────── الصفحات ─────────────────────────
@app.route("/lang/<code>")
def set_lang(code):
    resp = make_response(redirect(request.args.get("next") or url_for("dashboard")))
    resp.set_cookie("lang", "ar" if code == "ar" else "en", max_age=60 * 60 * 24 * 365)
    return resp


@app.route("/")
def dashboard():
    df = D.get_df()
    kp = _kpis(df)
    groups = {s: [k for k in kp if k["sec"] == s] for s in ("employees", "org", "ins")}
    active = df[df.active].sort_values("name", na_position="last")
    all_entries = LT.all_entries()
    source_balances = LT.source_balances()
    entries_by_code: dict[str, list[dict]] = {}
    for entry in all_entries:
        entries_by_code.setdefault(str(entry["code"]), []).append(entry)
    leave_employees = []
    for row in active.to_dict("records"):
        code = str(row["code"])
        entries = entries_by_code.get(code, [])
        leave_balance = LT.balance(row, entries, source_balance=source_balances.get(code))
        leave_employees.append({
            "code": code,
            "name": str(row.get("name") or ""),
            "management": str(row.get("management") or "—"),
            "department": str(row.get("department") or "—"),
            "balance": {
                "total": round(float(leave_balance["total_balance"]), 2),
                "casual": round(float(leave_balance["casual_balance"]), 2),
                "annual": round(float(leave_balance["annual_balance"]), 2),
                "sick": round(float(leave_balance["sick_remaining_3y"]), 2),
                "permissions": int(leave_balance["permissions_remaining"]),
                "available": bool(leave_balance["available"]),
                "waiting_days": int(leave_balance["waiting_days"]),
            },
            "rest": sorted(LT.rest_days(row.get("work_group"))),
            "history": [
                {
                    "code": str(entry["leave_code"]),
                    "start": str(entry["leave_date"]),
                    "end": str(entry.get("end_date") or entry["leave_date"]),
                    "days": float(entry["days"]),
                    "hours": float(entry["hours"]),
                    "approved": bool(entry["manager_approved"]),
                }
                for entry in entries[:50]
            ],
        })
    panels = [
        ("by_division", bars(df, "sector"), "sector"),
        ("by_dept", bars(df, "management"), "management"),
        ("by_location", bars(df, "location"), "location"),
    ]
    return render_template("dashboard.html", groups=groups, panels=panels,
                           leave_employees=leave_employees,
                           leave_types=LT.LEAVE_TYPES)


@app.route("/kpi/<key>")
def kpi(key):
    df = D.get_df()
    spec = next((k for k in _kpis(df) if k["key"] == key), None)
    if not spec or spec.get("value") is None:
        abort(404)
    if spec.get("org"):
        return redirect(url_for("org", level=spec["org"]))
    sub = df[spec["mask"](df)]
    bds = [dict(title=c if c not in ("age_band", "tenure_band", "prob_status") else c,
                items=bars(sub, c, top=8)) for c in spec["bd"]]
    summary = [dict(label="employees_count", value=len(sub))]
    if spec.get("dec") is not None:
        col = "age" if key == "age" else "tenure"
        summary.append(dict(label="k_" + key, value=spec["value"], dec=1))
        summary.append(dict(label="min", raw="min", value=float(sub[col].min())))
        summary.append(dict(label="max", raw="max", value=float(sub[col].max())))
    return list_page(sub, title=f"k_{key}", subtitle="details", back=url_for("dashboard"),
                     summary=summary, breakdowns=bds, sort=spec.get("sort"), csv_name=f"hr_{key}",
                     cols=["code", "name", "job", "management", "location", "age" if key == "age" else
                           ("tenure" if key == "tenure" else "hire_date"), "prob_status", "contract_status"])


@app.route("/org/<level>")
def org(level):
    if level not in ORG_LEVELS:
        abort(404)
    df = D.get_df()
    items = bars(df, level)
    return render_template("org.html", level=level, title=ORG_LEVELS[level], items=items,
                           total=len(items))


@app.route("/employees")
def employees():
    return list_page(D.get_df(), title="employees", subtitle="employees_sub", back=None)


@app.route("/profile")
def profile_search():
    df = D.get_df()
    q = (request.args.get("q") or "").strip()
    res = apply_filters(df, {"q": q}).head(30) if q else df.sort_values("hire_date", ascending=False).head(12)
    return render_template("profile_search.html", rows=res.to_dict("records"), q=q)


def _txt(v):
    """رقم/نص من الإكسل -> نص نظيف (بدون .0)."""
    if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA:
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


@app.route("/employee/<code>")
def employee(code):
    df = D.get_df()
    r = df[df.code == code]
    if r.empty:
        abort(404)
    r = r.iloc[0].to_dict()
    # أي قيمة فاضية (NaN / NA / NaT) تتحول لـ None عشان القالب يعرضها "—"
    for k, v in list(r.items()):
        if not isinstance(v, (list, tuple)) and pd.isna(v):
            r[k] = None
    for k in ("ins_no", "phone", "nid", "business_no", "employer_no"):
        r[k] = _txt(r.get(k))
    L = lang()
    # مدة الخدمة بالسنة والشهر
    hd = r.get("hire_date")
    tenure_txt = None
    if hd is not None:
        months = max(0, (D.today().year - hd.year) * 12 + D.today().month - hd.month)
        y, m = divmod(months, 12)
        tenure_txt = f"{y} {tr('y', L)} {m} {tr('mo', L)}" if y else f"{m} {tr('mo', L)}"
    # المستندات: الناقص أولًا ثم الموجود (زي Documents_Long في الـ DAX)
    docs = sorted([(k, bool(r["doc_" + k])) for k in D.DOC_KEYS], key=lambda x: x[1])
    pr = sum(1 for _, ok in docs if ok)
    al = D.get_alerts()
    mine = al[al.code == code].to_dict("records")
    leave_entries = LT.entries_for(code)
    leave_balance = LT.balance(
        r, leave_entries, source_balance=LT.source_balances().get(code)
    )
    leave_policy = LT.policies().get(code, {})
    return render_template(
        "employee.html", e=r, docs=docs, pr=pr, tt=len(docs), tenure_txt=tenure_txt,
        alerts_=mine, n_crit=sum(a["severity"] == "Critical" for a in mine),
        leave_balance=leave_balance, leave_policy=leave_policy,
        has_pen=bool({"investigations", "penalties_n"} & D.AVAILABLE),
        has_obl=bool({"has_line", "has_set", "has_desktop", "has_laptop"} & D.AVAILABLE))


def _leave_page_context(selected_code: str = "", error: str | None = None,
                        saved: bool = False, notice: str | None = None,
                        employee_data: pd.DataFrame | None = None):
    df = employee_data if employee_data is not None else D.get_df()
    active = df[df.active].sort_values("name", na_position="last")
    employees = []
    employee_by_code = {}
    for row in active.to_dict("records"):
        row["code"] = str(row["code"])
        employees.append(row)
        employee_by_code[row["code"]] = row
    if selected_code not in employee_by_code:
        selected_code = employees[0]["code"] if employees else ""

    selected = employee_by_code.get(selected_code)
    selected_entries = LT.entries_for(selected_code) if selected else []
    source_balance = LT.source_balances().get(selected_code) if selected else None
    selected_policy = LT.policies().get(selected_code, {}) if selected else {}
    return render_template(
        "leaves.html", employees=employees, selected=selected,
        selected_code=selected_code,
        selected_balance=LT.balance(
            selected, selected_entries, source_balance=source_balance
        ) if selected else None,
        selected_policy=selected_policy,
        sick_rest_days=sorted(LT.sick_rest_days(selected)) if selected else [4, 5],
        sick_holidays=sorted(LT.HOLIDAYS),
        entries=selected_entries[:100], entry_total=len(selected_entries), leave_labels=LT.LEAVE_TYPES,
        leave_requests=LT.requests_for(selected_code),
        manager_email=os.getenv("HR_LEAVE_MANAGER_EMAIL", "").strip(),
        error=error, notice=notice, saved=saved, today=local_time.today().isoformat())


def _send_leave_approval_email(leave_request: dict, token: str) -> None:
    power_automate_url = os.getenv("HR_POWER_AUTOMATE_URL", "").strip()
    recipient = str(leave_request["manager_email"]).strip()
    link = url_for("leave_approval", token=token, _external=True)
    subject = f"Leave approval request — {leave_request['code']}"
    body_html = (
        "<p>A leave request is waiting for your review.</p>"
        "<ul>"
        f"<li>Employee code: {html.escape(str(leave_request['code']))}</li>"
        f"<li>Leave type: {html.escape(str(leave_request['leave_code']))}</li>"
        f"<li>Dates: {html.escape(str(leave_request['leave_date']))} to "
        f"{html.escape(str(leave_request['end_date']))}</li>"
        f"<li>Days: {html.escape(str(leave_request['days']))} | "
        f"Hours: {html.escape(str(leave_request['hours']))}</li>"
        f"<li>Notes: {html.escape(str(leave_request['notes']) or '-')}</li>"
        "</ul>"
        f'<p><a href="{html.escape(link, quote=True)}">Review and approve or reject</a></p>'
    )
    if power_automate_url:
        payload = json.dumps({
            "recipient": recipient,
            "subject": subject,
            "body_html": body_html,
            "approval_url": link,
            "employee_code": str(leave_request["code"]),
            "leave_type": str(leave_request["leave_code"]),
            "start_date": str(leave_request["leave_date"]),
            "end_date": str(leave_request["end_date"]),
            "days": leave_request["days"],
            "hours": leave_request["hours"],
            "notes": str(leave_request["notes"]),
        }).encode("utf-8")
        flow_request = url_request.Request(
            power_automate_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with url_request.urlopen(flow_request, timeout=20) as response:
                if not 200 <= response.status < 300:
                    raise ValueError(f"Power Automate returned HTTP {response.status}.")
        except url_request.HTTPError as exc:
            raise ValueError(f"Power Automate returned HTTP {exc.code}.") from exc
        except url_request.URLError as exc:
            raise ValueError(f"تعذر الاتصال بتدفق Power Automate: {exc.reason}") from exc
        return

    host = os.getenv("HR_SMTP_HOST", "").strip()
    username = os.getenv("HR_SMTP_USER", "").strip()
    password = os.getenv("HR_SMTP_PASSWORD", "")
    if not host or not username or not password:
        raise ValueError(
            "طلب الاعتماد محفوظ كـ Pending، لكن إرسال البريد غير مُعدّ. "
            "اضبطي HR_POWER_AUTOMATE_URL أو إعدادات SMTP ثم أعيدي إرسال الطلب."
        )
    try:
        port = int(os.getenv("HR_SMTP_PORT", "587"))
    except ValueError as exc:
        raise ValueError("قيمة HR_SMTP_PORT غير صحيحة.") from exc
    sender = os.getenv("HR_SMTP_FROM", username).strip()
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        f"A leave request is waiting for your review.\n\n"
        f"Employee code: {leave_request['code']}\n"
        f"Leave type: {leave_request['leave_code']}\n"
        f"Dates: {leave_request['leave_date']} to {leave_request['end_date']}\n"
        f"Days: {leave_request['days']} | Hours: {leave_request['hours']}\n"
        f"Notes: {leave_request['notes'] or '-'}\n\n"
        f"Review and approve or reject: {link}"
    )
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context()) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(username, password)
            smtp.send_message(message)


@app.route("/leaves", methods=["GET", "POST"])
def leaves():
    df = D.get_df()
    selected_code = (request.form.get("employee_code") or request.args.get("code") or "").strip()
    error = None
    saved = False
    if request.method == "POST":
        employees = {str(row.code): row.to_dict() for _, row in df[df.active].iterrows()}
        employee = employees.get(selected_code)
        if not employee:
            error = "اختاري موظفًا فعّالًا من القائمة."
        else:
            try:
                action = request.form.get("action")
                if action == "save_policy":
                    LT.save_policy(
                        selected_code, request.form.get("weekend_comp", ""),
                        request.form.get("season_comp", ""))
                elif action == "save_entry":
                    leave_date = dt.date.fromisoformat(request.form.get("leave_date", ""))
                    end_date = dt.date.fromisoformat(request.form.get("end_date", ""))
                    days = float(request.form.get("days") or 0)
                    hours = float(request.form.get("hours") or 0)
                    LT.add_entry(
                        employee, request.form.get("leave_code", ""), leave_date, end_date, days, hours,
                        request.form.get("manager_name", ""),
                        request.form.get("manager_approved") == "on",
                        request.form.get("notes", ""))
                    return redirect(url_for("leaves", code=selected_code, saved=1))
                else:
                    raise ValueError("نوع العملية غير صالح.")
                return redirect(url_for("leaves", code=selected_code, saved=1))
            except (ValueError, TypeError) as exc:
                error = str(exc) or "راجعي البيانات المدخلة."
    notice = None
    if request.args.get("submitted") == "1":
        notice = "تم إرسال طلب الإجازة للمدير، وسيظهر في الرصيد وتقارير الحضور بعد اعتماده."
    elif request.args.get("pending") == "1":
        notice = "تم حفظ الطلب كمعلق، لكن البريد لم يُرسل. اضبطي إعدادات SMTP ثم استخدمي زر إعادة إرسال البريد."
    elif request.args.get("mail_sent") == "1":
        notice = "تمت إعادة إرسال طلب الاعتماد إلى المدير."
    return _leave_page_context(
        selected_code, error, saved or request.args.get("saved") == "1", notice,
        employee_data=df,
    )


@app.post("/leaves/requests/<int:request_id>/resend")
def resend_leave_approval(request_id: int):
    code = (request.form.get("code") or "").strip()
    leave_request = LT.request_by_id(request_id)
    if not leave_request or leave_request["status"] != "pending" or leave_request["code"] != code:
        abort(404)
    refreshed = LT.refresh_request_token(request_id)
    if not refreshed:
        abort(404)
    leave_request, token = refreshed
    try:
        _send_leave_approval_email(leave_request, token)
    except (ValueError, OSError, smtplib.SMTPException) as exc:
        return _leave_page_context(code, str(exc))
    return redirect(url_for("leaves", code=code, mail_sent=1))


@app.route("/leaves/approval/<token>", methods=["GET", "POST"])
def leave_approval(token: str):
    def approval_page(leave_request, employee_name=None, error=None, result=None, status=200):
        response = make_response(render_template(
            "leave_approval.html", leave_request=leave_request, employee_name=employee_name,
            error=error, result=result))
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response, status

    leave_request = LT.request_by_token(token)
    if not leave_request:
        return approval_page(None, status=404)
    employee_rows = D.get_df()
    matches = employee_rows[employee_rows.code.astype(str) == leave_request["code"]]
    if matches.empty:
        return approval_page(leave_request, error="تعذر العثور على بيانات الموظف.", status=404)
    employee = matches.iloc[0].to_dict()
    error = None
    if request.method == "POST":
        action = request.form.get("decision")
        if action not in ("approve", "reject"):
            abort(400)
        try:
            result = LT.review_request(token, employee, action == "approve")
            if result is None:
                return approval_page(None, status=404)
            return approval_page(result, employee.get("name"), result=result["status"])
        except ValueError as exc:
            error = str(exc)
    return approval_page(leave_request, employee.get("name"), error=error)


@app.post("/leaves/api/save")
def leaves_api_save():
    """حفظ صف من جدول الإجازات (إضافة لو مفيش id، وتعديل لو فيه) — بيرجّع JSON."""
    data = request.get_json(silent=True) or {}
    code = str(data.get("employee_code") or "").strip()
    df = D.get_df()
    found = df[(df.code == code) & df.active]
    if found.empty:
        return {"ok": False, "error": "اختاري موظفًا فعّالًا من القائمة."}, 400
    employee = found.iloc[0].to_dict()
    try:
        leave_date = dt.date.fromisoformat(str(data.get("leave_date") or ""))
        end_date = dt.date.fromisoformat(str(data.get("end_date") or data.get("leave_date") or ""))
        args = (str(data.get("leave_code") or ""), leave_date, end_date,
                float(data.get("days") or 0), float(data.get("hours") or 0),
                str(data.get("manager_name") or ""), False,
                str(data.get("notes") or ""))
        if data.get("id"):
            LT.update_entry(int(data["id"]), employee, *args)
        else:
            LT.add_entry(
                employee, args[0], leave_date, end_date, args[3], args[4],
                args[5], False, args[7])
    except (ValueError, TypeError) as exc:
        return {"ok": False, "error": str(exc) or "راجعي البيانات المدخلة."}, 400
    return {"ok": True}


@app.post("/leaves/<int:entry_id>/delete")
def delete_leave_entry(entry_id: int):
    code = (request.form.get("code") or "").strip()
    if not LT.delete_entry(entry_id):
        abort(404)
    return redirect(url_for("leaves", code=code, deleted=1))


@app.route("/contracts")
def contracts():
    df = D.get_df()
    order = ["Expired", "Expiring Soon", "Active", "Open-ended", "No Contract"]
    colors = {"Expired": "#C62828", "Expiring Soon": "#EF6C00", "Active": "#2E7D32",
              "Open-ended": "#6B6B72", "No Contract": "#C62828"}
    cards = [dict(label=s, kind="contract", value=int((df.contract_status == s).sum()), color=colors[s],
                  href=url_for("contracts", contract=s)) for s in order]
    sub = df
    if not request.args.get("contract"):
        sub = df[df.contract_status.isin(["Expired", "Expiring Soon"])]
    # الشارت بيتفلتر حسب الكارد المضغوط، ولو مفيش كارد مضغوط بيعرض التوتال
    cdf = df[df.contract_status == request.args["contract"]] if request.args.get("contract") else df
    types = bars(cdf, "contract_cur", kind="contract_type")
    return list_page(sub, title="contracts", subtitle="contracts_sub", summary=None, filters=True,
                     sort=("contract_days", True), csv_name="hr_contracts",
                     breakdowns=[dict(title="contract_type", items=types)], extra=cards,
                     cols=["code", "name", "job", "management", "contract_type", "contract_end", "contract_status"])


@app.route("/probation")
def probation():
    df = D.get_df()
    cards = []
    for s, c in (("Ending Soon", "#EF6C00"), ("On Probation", "#6B6B72"), ("Completed", "#2E7D32")):
        cards.append(dict(label=s, kind="prob", value=int((df.prob_status == s).sum()), color=c,
                          href=url_for("probation", prob=s)))
    sub = df
    if not request.args.get("prob"):
        sub = df[df.prob_days >= 0]
    # الشارت: حسب الكارد المضغوط، أو التوتال لو مفيش كارد مضغوط
    pdf = df[df.prob_status == request.args["prob"]] if request.args.get("prob") else df
    return list_page(sub, title="probation", subtitle="probation_sub", sort=("prob_days", True),
                     csv_name="hr_probation", extra=cards,
                     breakdowns=[dict(title="sector", items=bars(pdf, "sector", top=8))],
                     cols=["code", "name", "job", "management", "hire_date", "prob_end", "prob_status"])


@app.route("/documents")
def documents():
    df = D.get_df()
    # الشارت: حسب الكارد المضغوط (مكتمل/ناقص)، أو التوتال لو مفيش كارد مضغوط
    cplt = request.args.get("complete")
    mdf = df[df.file_complete == (cplt == "yes")] if cplt in ("yes", "no") else df
    miss = [dict(label=k, kind="doc", count=int(sum(k in m for m in mdf.missing_docs)))
            for k in D.DOC_KEYS]
    mx = max(m["count"] for m in miss) or 1
    for m in miss:
        m["pct"] = round(m["count"] / mx * 100, 1)
        m["href"] = url_for("documents", missing=m["label"])
    miss.sort(key=lambda m: -m["count"])
    cards = [dict(label="k_files", kind="raw", value=int(df.file_complete.sum()), color="#2E7D32",
                  href=url_for("documents", complete="yes")),
             dict(label="incomplete_files", kind="raw", value=int((~df.file_complete).sum()), color="#C62828",
                  href=url_for("documents", complete="no")),
             dict(label="avg_completion", kind="raw", value=f"{df.file_pct.mean() * 100:.0f}%", color="#6D3FD1",
                  href=None)]
    sub = df
    if not request.args.get("complete") and not request.args.get("missing"):
        sub = df[~df.file_complete]
    sub = sub.assign(missing_txt=sub.missing_docs)
    return list_page(sub, title="documents", subtitle="documents_sub", sort=("file_pct", True),
                     csv_name="hr_documents", extra=cards,
                     breakdowns=[dict(title="missing_by_doc", items=miss, linked=True)],
                     cols=["code", "name", "job", "management", "file_pct", "missing_txt"])


@app.route("/alerts")
def alerts():
    al = D.get_alerts()
    sev = request.args.get("severity")
    typ = request.args.get("type")
    q = (request.args.get("q") or "").strip()
    view = al
    if sev:
        view = view[view.severity == sev]
    elif not typ:
        view = view[view.severity != "Info"]
    if typ:
        view = view[view.type == typ]
    if q:
        view = view[view.name.fillna("").str.contains(q, regex=False) | view.code.str.contains(q, regex=False)]
    cards = [dict(label=s, value=int((al.severity == s).sum()), href=url_for("alerts", severity=s),
                  color={"Critical": "#C62828", "Warning": "#EF6C00", "Info": "#6B6B72"}[s])
             for s in ("Critical", "Warning", "Info")]
    page = max(1, request.args.get("page", 1, type=int))
    pages = max(1, math.ceil(len(view) / PER_PAGE))
    page = min(page, pages)
    rows = view.iloc[(page - 1) * PER_PAGE: page * PER_PAGE].to_dict("records")
    miss = D.get_df().set_index("code")["missing_docs"].to_dict()
    for r in rows:
        r["missing"] = miss.get(r["code"], [])
    return render_template("alerts.html", rows=rows, cards=cards, total=len(view), page=page, pages=pages,
                           sev=sev, typ=typ, q=q)



# ───────────────────────── الحضور اللحظي (من قاعدة بيانات المكن) ─────────────────────────
def _att_dates():
    today = local_time.today()
    def parse(v, default):
        try:
            return pd.Timestamp(v).date() if v else default
        except Exception:
            return default
    s, e = parse(request.args.get("start"), today), parse(request.args.get("end"), today)
    if e < s:
        s, e = e, s
    if (e - s).days >= AS["max_days"]:
        s = (pd.Timestamp(e) - pd.Timedelta(days=AS["max_days"] - 1)).date()
    return s, e


def _att_query():
    """بيرجّع البصمات مدمجة مع HR وبعد تطبيق فلاتر الموظف والإدارة والقسم والوظيفة والموقع."""
    start, end = _att_dates()
    hr = D.get_df()
    dept, manager, job = (
        request.args.get("dept") or "",
        request.args.get("manager") or "",
        request.args.get("job") or "",
    )
    location = request.args.get("location") or ""
    q = (request.args.get("q") or "").strip().lower()
    employee_pool = hr[hr.active].copy() if "active" in hr else hr.copy()
    if dept:
        employee_pool = employee_pool[employee_pool.department == dept]
    if manager:
        employee_pool = employee_pool[employee_pool.manager == manager]
    if job:
        employee_pool = employee_pool[employee_pool.job == job]
    if location:
        employee_pool = employee_pool[employee_pool.location == location]
    if q:
        qn = q.lstrip("0") or q
        code = employee_pool.code.astype(str).str.lower()
        key = A._norm_code(employee_pool.code.astype(str)).astype(str).str.lower()
        name = employee_pool.name.fillna("").astype(str).str.lower()
        employee_pool = employee_pool[
            code.str.contains(q, regex=False)
            | key.str.contains(qn, regex=False)
            | name.str.contains(q, regex=False)
        ]
    employee_total = int(A._norm_code(employee_pool.code.astype(str)).nunique())
    if AS["mode"] == "demo":
        A.demo_pool([(c, l) for c, l in zip(hr.code, hr.location)][::2])
    p = A.fetch(start, end, request.args.get("machine") or None)
    emp = hr[["code", "name", "job", "department", "manager", "location"]].copy()
    emp["key"] = A._norm_code(emp["code"])
    emp = emp.drop_duplicates("key").rename(columns={"code": "hr_code"})
    m = p.merge(emp, on="key", how="left")
    m["known"] = m["name"].notna()
    m["name"] = m["name"].fillna("—")
    for c in ("job", "department", "manager", "location"):
        m[c] = m[c].fillna("—")
    if dept:
        m = m[m.department == dept]
    if manager:
        m = m[m.manager == manager]
    if job:
        m = m[m.job == job]
    if location:
        m = m[m.location == location]
    if q:
        qn = q.lstrip("0") or q            # 00123 = 123
        m = m[m.emp_code.astype(str).str.lower().str.contains(q, regex=False)
              | m.key.astype(str).str.lower().str.contains(qn, regex=False)
              | m.hr_code.fillna('').astype(str).str.lower().str.contains(q, regex=False)
              | m.name.astype(str).str.lower().str.contains(q, regex=False)]
    return m, start, end, employee_total


@app.route("/attendance")
def attendance():
    hr = D.get_df()
    ctx = dict(
        departments=sorted(hr.department.dropna().unique().tolist()),
        managers=sorted(hr.manager.dropna().unique().tolist()),
        jobs=sorted(hr.job.dropna().unique().tolist()),
        locations=sorted(hr.location.dropna().unique().tolist()),
        refresh=AS["refresh_seconds"], demo=AS["mode"] == "demo",
    )
    return render_template("attendance.html", **ctx)


@app.route("/attendance/schema")
def attendance_schema():
    """بيعرض جداول قاعدة المكن وأعمدتها (لمساعدة ضبط الـ preset)."""
    try:
        tables, err = A.discover(), None
    except A.AttendanceError as e:
        tables, err = [], str(e)
    return render_template("attendance_schema.html", tables=tables, err=err, db=("" if AS.get("source") == "access" else AS["database"]), server=AS["access_path"] if AS.get("source") == "access" else AS["server"])


@app.route("/api/attendance")
def api_attendance():
    try:
        m, start, end, employee_total = _att_query()
        machines = A.machines()
    except A.AttendanceError as e:
        return {"ok": False, "error": str(e)}
    now = pd.Timestamp(local_time.now_naive())
    page = max(1, request.args.get("page", 1, type=int))
    per = 50
    pages = max(1, math.ceil(len(m) / per))
    page = min(page, pages)
    include_today = end >= now.date()
    ms = []
    for name, g in m.groupby("machine"):
        last = g.punch_time.max()
        ms.append(dict(name=name, n=int(len(g)), people=int(g.key.nunique()), last=last.strftime("%Y-%m-%d %H:%M:%S"),
                       active=bool(include_today and (now - last).total_seconds() <= AS["active_minutes"] * 60)))
    if not (request.args.get("machine") or request.args.get("q") or request.args.get("dept")
            or request.args.get("manager") or request.args.get("job") or request.args.get("location")):
        have = {x["name"] for x in ms}          # الأجهزة المسجلة اللي معليهاش بصمات في الفترة تظهر برضه (خاملة)
        ms += [dict(name=n, n=0, people=0, last="", active=False) for n in A.registered_machines() if n not in have]
    ms.sort(key=lambda x: x["last"], reverse=True)
    last = m.iloc[0] if len(m) else None
    rows = m.iloc[(page - 1) * per: page * per]
    return {
        "ok": True, "source": "demo" if AS["mode"] == "demo" else AS.get("source", "sql"),
        "now": now.strftime("%Y-%m-%d %H:%M:%S"), "start": str(start), "end": str(end),
        "kpi": dict(employees_total=employee_total,
                    punches=int(len(m)),
                    machines=int(sum(x["active"] for x in ms)), machines_total=len(ms),
                    unmatched=int(m[~m.known].key.nunique()) if len(m) else 0,
                    last_time=last.punch_time.strftime("%Y-%m-%d %H:%M:%S") if last is not None else None,
                    last_name=last["name"] if last is not None else None,
                    last_machine=last["machine"] if last is not None else None),
        "machines": ms, "all_machines": machines, "page": page, "pages": pages, "total": int(len(m)),
        "rows": [
            dict(t=r["punch_time"].strftime("%Y-%m-%d %H:%M:%S"), code=r["emp_code"], name=r["name"], job=r["job"],
                 dept=r["department"], machine=r["machine"], dir=r["dir"] if isinstance(r["dir"], str) else None, known=bool(r["known"]),
                 hr=r["hr_code"] if r["known"] else None)
            for r in rows.to_dict("records")],
    }


# ── تقرير الحضور الشهري للموظف (نفس شكل شيت الإكسل) ──
def _rep_args():
    code = (request.args.get("code") or "").strip()
    if " — " in code:                       # من الـ datalist: "123 — الاسم"
        code = code.split(" — ")[0].strip()
    today = local_time.today()
    default_start = today.replace(day=1)
    _, default_end = R.period_for(today.year, today.month, 1)
    start_raw = request.args.get("start")
    end_raw = request.args.get("end")
    start, end, err = default_start, default_end, None
    try:
        if start_raw:
            start = dt.date.fromisoformat(start_raw)
        if end_raw:
            end = dt.date.fromisoformat(end_raw)
        if start > end:
            err = tr("rep_range_error", lang())
    except ValueError:
        err = tr("rep_invalid_dates", lang())
    return code, start, end, err


def _dept_reports(dept: str, start: dt.date, end: dt.date,
                  location: str = "", manager: str = "") -> list[dict]:
    """تقارير مفصلة لموظفي القسم والمدير المباشر والموقع المحددين."""
    emps = R.department_employees(dept)
    if manager:
        emps = [employee for employee in emps if employee.get("manager") == manager]
    if location:
        emps = [employee for employee in emps if employee.get("location") == location]
    if not emps:
        raise A.AttendanceError("لا يوجد موظفون للمدير المباشر والقسم واللوكيشن المحددين.")
    if AS["mode"] == "demo":
        A.demo_pool([(str(e["code"]), "") for e in emps])
    punches = A.fetch_range(start, end)
    return [R.build(str(e["code"]), start, end, punches=punches, emp=e) for e in emps]


@app.route("/attendance/report")
def attendance_report():
    code, start, end, err = _rep_args()
    location = (request.args.get("location") or "").strip()
    manager = (request.args.get("manager") or "").strip()
    rep, reports = None, []
    emps = R.employees_list()
    departments = sorted({e["department"] for e in emps if e["department"]})
    managers = sorted({e["manager"] for e in emps if e["manager"]})
    locations = sorted({e["location"] for e in emps if e["location"]})
    if code and not err:
        try:
            code = R.resolve_employee(code)
            employee = next((e for e in emps if e["code"] == code), None)
            if manager and employee and employee["manager"] != manager:
                err = "الموظف المختار لا يتبع المدير المباشر المحدد."
            elif location and employee and employee["location"] != location:
                err = "الموظف المختار لا يتبع اللوكيشن المحدد."
            else:
                rep = R.build(code, start, end)
                reports = [rep]
        except A.AttendanceError as e:
            err = str(e)
    elif (request.args.get("dept") or manager or location) and not err:
        try:
            reports = _dept_reports(request.args.get("dept", ""), start, end, location, manager)
        except A.AttendanceError as e:
            err = str(e)
    selected_dept = request.args.get("dept", "") if not code else ""
    return render_template("attendance_report.html", rep=rep, err=err, code=code,
                           reports=reports, start=start, end=end, emps=emps, departments=departments,
                           selected_dept=selected_dept, managers=managers,
                           selected_manager=manager, locations=locations,
                           selected_location=location,
                           demo=AS["mode"] == "demo", hm=R.hm, hs=R.hm_signed, ampm=R.ampm)


# ── All Summary: صفحة مستقلة بنفس شيت Summary (موظف في كل صف + إجماليات) ──
def _summary_data():
    _, start, end, err = _rep_args()
    dept = (request.args.get("dept") or "").strip()
    manager = (request.args.get("manager") or "").strip()
    summary = None
    if not err:
        try:
            summary = R.summarize(_dept_reports(dept, start, end, manager=manager))
        except A.AttendanceError as e:
            err = str(e)
    return dept, manager, start, end, err, summary


@app.route("/attendance/summary")
def attendance_summary():
    dept, manager, start, end, err, summary = _summary_data()
    employees = R.employees_list()
    departments = sorted({e["department"] for e in employees if e["department"]})
    managers = sorted({e["manager"] for e in employees if e["manager"]})
    return render_template("attendance_summary.html", dept=dept, start=start, end=end, err=err,
                           manager=manager, summary=summary, departments=departments,
                           managers=managers,
                           demo=AS["mode"] == "demo", hm=R.hm)


@app.route("/attendance/summary.xlsx")
def attendance_summary_xlsx():
    dept, manager, start, end, err, summary = _summary_data()
    if err or summary is None:
        abort(400)
    selected_group = " / ".join(value for value in (manager, dept) if value)
    sub = f"{selected_group or tr('rep_all_depts', lang())} · {start:%d-%m-%Y} → {end:%d-%m-%Y} · {summary['employees']} {tr('rep_emp_count_short', lang())}"
    return Response(R.summary_to_xlsx(summary, sub),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=all_summary_{start}_{end}.xlsx"})


@app.route("/attendance/report.xlsx")
def attendance_report_xlsx():
    code, start, end, err = _rep_args()
    if not code or err:
        abort(400)
    try:
        rep = R.build(code, start, end)
    except A.AttendanceError as e:
        abort(503, str(e))
    return Response(R.to_xlsx(rep), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=attendance_{rep['emp']['code']}_{start}_{end}.xlsx"})


# ── سحب البصمات من الأجهزة ──
@app.route("/api/sync")
def api_sync():
    return ZS.snapshot()


@app.route("/api/sync/run", methods=["POST"])
def api_sync_run():
    ZS.run_now()
    return {"ok": True}


@app.route("/api/sync/toggle", methods=["POST"])
def api_sync_toggle():
    ZS.set_enabled(not ZS.snapshot()["enabled"])
    return {"ok": True}


@app.route("/attendance.csv")
def attendance_csv():
    try:
        m, _, _, _ = _att_query()
    except A.AttendanceError as e:
        abort(503, str(e))
    out = m[["punch_time", "emp_code", "name", "job", "department", "machine", "dir"]].rename(columns={
        "punch_time": "time", "emp_code": "code", "department": "department", "dir": "type"})
    buf = io.StringIO()
    out.to_csv(buf, index=False)
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=attendance.csv"})


@app.errorhandler(404)
def nf(_):
    return render_template("404.html"), 404


if __name__ == "__main__":
    D.get_df()  # تسخين الكاش
    # في وضع debug فلاسك بيشغّل البرنامج مرتين؛ نبدأ السحب في العملية الأساسية بس
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        ZS.start()
    app.run(debug=True, port=int(os.environ.get("PORT", 5001)))