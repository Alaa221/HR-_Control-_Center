"""طبقة البيانات: قراءة ملف الإكسل وحساب كل المؤشرات والحالات والتنبيهات."""
from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd

import local_time

warnings.filterwarnings("ignore")

DATA_FILE = Path(__file__).parent / "data" / "GPS - HQ Data Base - Active.xlsx"

# الأعمدة العربية في الإكسل  ->  أسماء إنجليزية نستخدمها في الكود
COLS = {
    "حالة الموظف": "status",
    "الكود": "code",
    "الاسم": "name",
    "الوظيفة": "job",
    "القسم": "department",
    "الإدارة": "management",
    "القطاع": "sector",
    "التبعية الإدارية": "manager",
    "الموقع": "location",
    "التعيين": "hire_date",
    "الحالة": "insurance_status",
    "الرقم التأميني": "ins_no",
    "بداية التأمينات": "ins_start",
    "فرع التأمينات": "ins_branch",
    "سبب عدم التأمين": "ins_reason",
    "أول عقد": "contract_first",
    "العقد الحالي": "contract_cur",
    "تاريخ إنتهاء العقد": "contract_end",
    "الأرشيف": "archive",
    "يوجد ملف؟": "doc_file",
    "يوجد عقد؟": "doc_contract",
    "البطاقة": "doc_id",
    "الميلاد": "doc_birth",
    "المؤهل": "doc_edu",
    "الجيش": "doc_military",
    "الفيش": "doc_police",
    "كعب العمل": "doc_workcard",
    "بيان السرية": "doc_conf",
    "%": "file_pct",
    "الرقم القومى": "nid",
    "تاريخ الميلاد": "birth_date",
    "رقم الموبايل": "phone",
    "العنوان": "address",
    "المنطقة السكنية": "area",
    "النوع": "gender",
    "الديانة": "religion",
    "مجموعة العمل": "work_group",
    "ساعات العمل": "hours",
    "مواعيد العمل": "schedule",
    "الاضافى": "overtime",
    "الإستقالة": "resign_date",
    "نهاية التأمينات": "ins_end",
    "عنوان مكتب التأمينات": "ins_office",
    "التفتيش": "inspector",
    "درجة التقييم": "eval_grade",
    "تقييم الملف": "file_score",
    "ملاحظات": "notes",
    "تقفيل المرتبات": "payroll",
    "وجود بصمة حضور و إنصراف للموظف": "fingerprint",
    "الاجراء للحضور و انصراف": "att_proc",
    "ملاحظات الحضور و الانصراف": "att_notes",
    "إرسال نتيجة للموظف": "send_result",
    "س1": "doc_s1",
}

# حقول موجودة في Power BI مش في ملف الإكسل الحالي. لو أضفتي عمود بأي اسم من القايمة هيظهر تلقائيًا.
OPTIONAL = {
    "archive_code": ["كود الأرشيف", "ArchiveCode"],
    "hire_type": ["نوع التعيين", "HireType"],
    "nid_date": ["تاريخ إصدار الرقم القومي", "NationalIDDate"],
    "marital": ["الحالة الاجتماعية", "MaritalStatus"],
    "military_status": ["الموقف من التجنيد", "MilitaryStatus"],
    "military_end": ["تاريخ انتهاء التجنيد", "MilitaryEndDate"],
    "business_no": ["رقم البيزنس", "BusinessNumber"],
    "email": ["البريد الإلكتروني", "Email"],
    "government": ["المحافظة", "Government"],
    "employer_no": ["رقم المنشأة", "EmployerNumber"],
    "leave_total": ["إجمالي رصيد الإجازات", "LeaveTotal"],
    "leave_due": ["تاريخ الاستحقاق", "LeaveDueDate"],
    "leave_ai": ["باقي A.I", "LeaveRemainingAI"],
    "leave_cur": ["الرصيد الحالي", "LeaveCurrent"],
    "investigations": ["عدد التحقيقات", "InvestigationsCount"],
    "penalties_n": ["عدد الجزاءات", "PenaltiesCount"],
    "has_line": ["خط موبايل", "HasMobileLine"],
    "has_set": ["جهاز موبايل", "HasMobileSet"],
    "has_desktop": ["ديسك توب", "HasDesktop"],
    "has_laptop": ["لاب توب", "HasLaptop"],
}
OPT_DATES = ["nid_date", "military_end", "leave_due"]
OPT_NUMS = ["leave_total", "leave_ai", "leave_cur", "investigations", "penalties_n",
            "has_line", "has_set", "has_desktop", "has_laptop"]
AVAILABLE: set = set()   # الحقول الاختيارية اللي لقيناها فعلًا في الإكسل

DOCS = [  # (key, عمود)
    "doc_file", "doc_contract", "doc_id", "doc_birth", "doc_edu",
    "doc_military", "doc_police", "doc_workcard", "doc_conf",
]
DOC_KEYS = [d.replace("doc_", "") for d in DOCS]

PROB_DAYS = 90          # مدة فترة الاختبار
PROB_SOON = 30          # "تنتهي قريبًا"
CONTRACT_SOON = 60      # "قارب على الانتهاء"

_cache: dict = {"key": None, "df": None, "alerts": None}


def today() -> pd.Timestamp:
    return pd.Timestamp(local_time.today())


def _clean_text(s: pd.Series) -> pd.Series:
    return s.astype("string").str.strip().replace({"": pd.NA})


def _load() -> pd.DataFrame:
    raw = pd.read_excel(DATA_FILE)
    raw.columns = [str(c).strip() for c in raw.columns]
    raw = raw[raw["الكود"].notna() & raw["الاسم"].notna()]  # تجاهل الصفوف الفارغة
    df = pd.DataFrame({en: raw[ar] for ar, en in COLS.items() if ar in raw.columns})
    now = today()

    AVAILABLE.clear()
    for key, aliases in OPTIONAL.items():
        col = next((a for a in aliases if a in raw.columns and raw[a].notna().any()), None)
        if col:
            df[key] = raw[col]
            AVAILABLE.add(key)
        else:
            df[key] = pd.NA
    for c in OPT_DATES:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    for c in OPT_NUMS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["archive_code", "hire_type", "marital", "military_status", "business_no", "email",
              "government", "employer_no"]:
        df[c] = _clean_text(df[c].astype("string"))

    df["code"] = df["code"].astype(int).astype(str)
    for c in ["name", "job", "department", "management", "sector", "manager", "location",
              "gender", "religion", "contract_cur", "contract_first", "ins_branch",
              "ins_reason", "archive", "area", "address", "work_group", "hours",
              "schedule", "overtime", "ins_office", "inspector", "notes", "payroll",
              "fingerprint", "att_proc", "att_notes", "send_result"]:
        df[c] = _clean_text(df[c]).replace({"0": pd.NA})

    for c in ["hire_date", "contract_end", "birth_date", "ins_start", "ins_end", "resign_date"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")

    # فترة الاختبار
    df["prob_end"] = df["hire_date"] + pd.Timedelta(days=PROB_DAYS)
    df["prob_days"] = (df["prob_end"] - now).dt.days
    df["prob_status"] = "Unknown"
    has = df["prob_days"].notna()
    df.loc[has & (df["prob_days"] < 0), "prob_status"] = "Completed"
    df.loc[has & (df["prob_days"] >= 0), "prob_status"] = "On Probation"
    df.loc[has & (df["prob_days"] >= 0) & (df["prob_days"] <= PROB_SOON), "prob_status"] = "Ending Soon"

    # العقود
    df["contract_days"] = (df["contract_end"] - now).dt.days
    cs = pd.Series("Active", index=df.index)
    cs[df["contract_cur"] == "غير محدد المدة"] = "Open-ended"
    cs[df["contract_cur"].isna() | (df["contract_cur"] == "بدون عقد")] = "No Contract"
    timed = ~cs.isin(["Open-ended", "No Contract"]) & df["contract_days"].notna()
    cs[timed & (df["contract_days"] < 0)] = "Expired"
    cs[timed & (df["contract_days"] >= 0) & (df["contract_days"] <= CONTRACT_SOON)] = "Expiring Soon"
    df["contract_status"] = cs

    # سن + مدة خدمة
    df["age"] = ((now - df["birth_date"]).dt.days / 365.25).round(1)
    df["tenure"] = ((now - df["hire_date"]).dt.days / 365.25).round(1)
    df["age_band"] = pd.cut(df["age"], [0, 25, 35, 45, 55, 120], right=False,
                            labels=["<25", "25-34", "35-44", "45-54", "55+"]).astype("string")
    df["tenure_band"] = pd.cut(df["tenure"], [-1, 1, 3, 5, 10, 100], right=False,
                               labels=["<1", "1-3", "3-5", "5-10", "10+"]).astype("string")

    # التأمين
    ins_to = df["ins_end"].fillna(now)
    df["ins_years"] = ((ins_to - df["ins_start"]).dt.days / 365.25).round(1)
    df["insured"] = df["insurance_status"].eq("مؤمن")
    df["insurance_label"] = df["insured"].map({True: "Insured", False: "Uninsured"})

    # المستندات
    for d in DOCS:
        df[d] = pd.to_numeric(df[d], errors="coerce").fillna(0).astype(int)
    df["file_pct"] = pd.to_numeric(df["file_pct"], errors="coerce").fillna(0)
    df["doc_s1"] = pd.to_numeric(df["doc_s1"], errors="coerce").fillna(0).astype(int)
    for c in ["eval_grade", "file_score"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["missing_docs"] = df.apply(
        lambda r: [k for k, d in zip(DOC_KEYS, DOCS) if r[d] == 0], axis=1)
    df["file_complete"] = df["file_pct"] >= 0.999
    df["active"] = df["status"].astype("string").str.lower().eq("active")
    return df.reset_index(drop=True)


def _build_alerts(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    def add(r, typ, sev, metric, msg):
        rows.append({"code": r.code, "name": r["name"], "type": typ, "severity": sev,
                     "metric": metric, "msg": msg, "sector": r.sector})

    for _, r in df.iterrows():
        pd_ = r.prob_days
        if pd.notna(pd_) and 0 <= pd_ <= PROB_SOON:
            add(r, "Probation", "Critical" if pd_ <= 7 else "Warning", int(pd_), "prob")
        cs = r.contract_status
        if cs == "Expired":
            add(r, "Contract", "Critical", int(r.contract_days), "contract_expired")
        elif cs == "Expiring Soon":
            add(r, "Contract", "Warning", int(r.contract_days), "contract_soon")
        elif cs == "No Contract":
            add(r, "Contract", "Info", 0, "no_contract")
        if r.missing_docs:
            add(r, "Documents", "Info", len(r.missing_docs), "docs")
    out = pd.DataFrame(rows, columns=["code", "name", "type", "severity", "metric", "msg", "sector"])
    order = {"Critical": 0, "Warning": 1, "Info": 2}
    out["_o"] = out["severity"].map(order)
    return out.sort_values(["_o", "metric"]).drop(columns="_o").reset_index(drop=True)


def get_df() -> pd.DataFrame:
    key = (DATA_FILE.stat().st_mtime, local_time.today())
    if _cache["key"] != key:
        df = _load()
        _cache.update(key=key, df=df, alerts=_build_alerts(df))
    return _cache["df"]


def get_alerts() -> pd.DataFrame:
    get_df()
    return _cache["alerts"]


def breakdown(df: pd.DataFrame, col: str, top: int | None = None) -> list[tuple[str, int]]:
    s = df[col].dropna().astype(str).value_counts()
    if top:
        s = s.head(top)
    return [(k, int(v)) for k, v in s.items()]
