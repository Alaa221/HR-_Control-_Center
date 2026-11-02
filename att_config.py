"""إعدادات الاتصال بقاعدة بيانات المكن (ZK) على SQL Server.

اضبطي القيم عبر متغيرات البيئة بدل تخزين المسارات أو كلمات المرور في ملفات المشروع.
"""
import os

SETTINGS = {
    # ───── مصدر البيانات ─────
    # access    : ملف ZKTime / ATT2000.MDB مباشرة (الافتراضي)
    # sqlserver : قاعدة SQL Server (LocalDB) — الإعدادات تحت
    "source": os.getenv("ATT_SOURCE", "access"),
    "access_path": os.getenv("ATT_MDB", ""),
    "access_password": os.getenv("ATT_MDB_PWD", ""),   # لو الملف عليه باسورد

    # ───── اتصال SQL Server (لو source = sqlserver) ─────
    "server":   os.getenv("ATT_SERVER", r"(localdb)\MSSQLLocalDB"),
    "database": os.getenv("ATT_DB", ""),            # ← اسم قاعدة بيانات المكن (شغّلي tools/discover_db.py لو مش فاكراه)
    "user":     os.getenv("ATT_USER", "sa"),
    "password": os.getenv("ATT_PASSWORD", ""),
    # لو الدخول بـ sa فشل، جرّب Windows Authentication تلقائيًا
    "try_windows_auth_fallback": True,

    # ───── شكل الجداول ─────
    # auto      : (الافتراضي) يكتشف الجداول لوحده بين zkbiotime و zktime
    # zkbiotime : ZKBioTime / BioTime  (جدول iclock_transaction)
    # zktime    : ZKTime / ZKAccess    (جداول CHECKINOUT + USERINFO + Machines)
    # custom    : استعلامك الخاص (CUSTOM_SQL تحت)
    "preset": os.getenv("ATT_PRESET", "auto"),

    # الاستعلام الخاص: لازم يرجّع الأعمدة دي بالظبط (الأسماء مهمة):
    #   emp_code   رقم/كود الموظف (نفس "الكود" في ملف الإكسل)
    #   punch_time تاريخ ووقت البصمة
    #   machine    اسم أو رقم المكنة
    #   state      (اختياري) نوع البصمة: 0/I = حضور ، 1/O = انصراف
    # ما تحطيش WHERE على التاريخ هنا؛ الصفحة بتضيفه لوحدها.
    "custom_sql": """
        SELECT CAST(c.EmployeeCode AS NVARCHAR(50)) AS emp_code,
               c.PunchTime                          AS punch_time,
               c.DeviceName                         AS machine,
               c.PunchType                          AS state
        FROM   dbo.Punches c
    """,

    # ───── سلوك الصفحة ─────
    "refresh_seconds": 15,        # كل قد إيه الصفحة تحدّث نفسها
    "max_rows": 50000,            # أقصى عدد بصمات يتسحب في الطلب الواحد
    "max_days": 31,               # أقصى مدى تواريخ
    "cache_seconds": 5,           # كاش قصير عشان كتر الفتح ما يضغطش على القاعدة
    "active_minutes": 30,         # المكنة تعتبر "شغالة" لو آخر بصمة فيها خلال المدة دي
    "strip_leading_zeros": True,  # 00123 = 123 عند مطابقة كود المكن مع كود الإكسل

    # ───── سحب البصمات من الأجهزة (بيكتب في ATT2000.MDB) ─────
    "sync_enabled": True,          # يبدأ السحب تلقائيًا مع تشغيل الموقع
    "sync_seconds": 60,           # كل قد إيه يمر على كل الأجهزة
    "sync_workers": 8,            # عدد الأجهزة اللي بتتسحب في نفس الوقت
    "sync_timeout": 20,           # ثواني انتظار الجهاز (الأجهزة البعيدة بطيئة في تنزيل السجلات)
    "sync_backfill_days": 31,     # بنسحب بصمات آخر كام يوم بس (الأقدم نزّلها ZKTime قبل كده). 0 = كل التاريخ (أبطأ بكتير)
    "sync_ping": False,           # True = اعمل ICMP ping قبل الاتصال (غالبًا سيبيه False)
    "sync_passwords": [],         # كلمات سر اتصال إضافية تتجرّب لو الجهاز رفض (مثال: [123456, 888888])

    # ───── تقرير الموظف الشهري (/attendance/report) ─────
    "weekend_default": [4, 5],    # أيام الراحة الافتراضية (الاثنين=0 ... الجمعة=4، السبت=5، الأحد=6)
    "grace_minutes": 0,           # سماحية افتراضية بالدقايق؛ شفتات 9 و10 لها 15 دقيقة على الأقل
    "default_schedule": "",       # لو الموظف مواعيده مش معروفة في الإكسل، مثال: "09:00 AM : 05:00 PM" (فاضي = بدون مواعيد رسمية)
    "report_cycle_start": 1,      # يوم بداية الشهر المالي (1 = الشهر الميلادي، 26 = من 26 الشهر اللي فات لـ 25)

    # ───── تصحيح التوقيت الصيفي/الشتوي (بيتطبق مركزيًا في attendance.fetch فيشمل الحضور اللحظي والتقرير والملخص) ─────
    # القاعدة: أي بصمة وقتها الأصلي واقع في فترة التوقيت الصيفي (Africa/Cairo) بيتضاف عليه dst_offset_minutes.
    # -60 = ساعة المصدر متقدمة ساعة في الصيف (السلوك اللي كان في التقرير). لو الأجهزة واقفة على الشتوي ومتأخرة ساعة خليها +60.
    # في الشتوي مفيش أي تعديل. dst_fix=False يوقف التصحيح خالص.
    "dst_fix": os.getenv("ATT_DST_FIX", "0") == "1",   # مقفول افتراضيًا: وقت الجهاز زي ما هو بالظبط (زي ZKTime)
    "dst_offset_minutes": int(os.getenv("ATT_DST_OFFSET", "-60")),

    # ───── وضع تجريبي (بيانات وهمية للمعاينة بس) ─────
    # شغّليه بـ  set ATT_MODE=demo   قبل تشغيل التطبيق
    "mode": os.getenv("ATT_MODE", "sql"),
}

# استعلامات الـ presets الجاهزة (بتتغلّف تلقائيًا بفلتر التاريخ والمكنة)
# ───── أكواد الأجهزة (New Code) — للعرض فقط داخل البرنامج، مش بتتكتب في قاعدة البيانات ─────
# المفتاح = عمود ID في جدول Machines (مش الـ SN لأن فيه أجهزة بنفس الـ SN أو من غير SN).
# جهاز جديد؟ ضيفي سطر هنا (ID: "الكود") وأعيدي تشغيل البرنامج. اسم الماكينة القديم بيتقرا لوحده من MachineAlias.
MACHINE_CODES = {
    4: "CND4", 9: "CND9", 11: "CND11", 13: "CND13",
    16: "HQ4", 17: "HQ5", 18: "HQ6", 19: "HQ7", 20: "HQ8", 21: "HQ9", 22: "HQ10", 23: "HQ11",
    27: "MNS", 29: "ALEX", 30: "TLB1", 31: "TLB2", 32: "CND32", 33: "SHRB", 34: "STUDIO", 35: "CND35",
    14: "CND14", 15: "DAW", 25: "HORY", 28: "MENIA", 12: "HQ12", 10: "MOST", 8: "CND8",
}


def new_code(machine_id, db_value=None) -> str:
    """كود العرض للجهاز: من MACHINE_CODES بالـ ID، وإلا من عمود New Code في الجدول (لو موجود)."""
    try:
        code = MACHINE_CODES.get(int(machine_id))
    except (TypeError, ValueError):
        code = None
    return str(code or db_value or "").strip()


# استعلام ملف ZKTime (Access SQL). الفلتر بالتاريخ بيتضاف تلقائيًا.
ACCESS_SQL = """
    SELECT TOP {top} (u.Badgenumber & '') AS emp_code,
           c.CHECKTIME AS punch_time,
           (c.sn & '') AS sn,
           (c.sensorid & '') AS sensor,
           (c.CHECKTYPE & '') AS state
    FROM CHECKINOUT AS c INNER JOIN USERINFO AS u ON u.USERID = c.USERID
    WHERE c.CHECKTIME >= {start} AND c.CHECKTIME < {end}{extra}
    ORDER BY c.CHECKTIME DESC
"""

PRESETS = {
    "zkbiotime": """
        SELECT CAST(t.emp_code AS NVARCHAR(50))                       AS emp_code,
               t.punch_time                                           AS punch_time,
               COALESCE(NULLIF(t.terminal_alias, ''), t.terminal_sn)  AS machine,
               CAST(t.punch_state AS NVARCHAR(10))                    AS state
        FROM   dbo.iclock_transaction t
    """,
    "zktime": """
        SELECT CAST(u.Badgenumber AS NVARCHAR(50))                    AS emp_code,
               c.CHECKTIME                                            AS punch_time,
               COALESCE(NULLIF(m.[New Code], ''), CAST(c.sensorid AS NVARCHAR(20))) AS machine,
               CAST(c.CHECKTYPE AS NVARCHAR(10))                      AS state
        FROM   dbo.CHECKINOUT c
        JOIN   dbo.USERINFO   u ON u.USERID = c.USERID
        LEFT JOIN dbo.Machines m ON CAST(m.sn AS NVARCHAR(100)) = CAST(c.sn AS NVARCHAR(100))
    """,
}


# الإجازات الرسمية اللي بتظهر في عمود "ملاحظات اليوم" (التاريخ: الاسم).
# الثابتة متحطوطة تحت. الأعياد الهجرية (مولد النبي، العيدين، رأس السنة الهجرية) بتتغير كل سنة — ضيفيها بإيديكي.
HOLIDAYS = {
    "2026-01-07": "عيد الميلاد المجيد",
    "2026-01-25": "عيد الثورة / عيد الشرطة",
    "2026-04-25": "عيد تحرير سيناء",
    "2026-05-01": "عيد العمال",
    "2026-06-30": "ثورة 30 يونيو",
    "2026-07-23": "ثورة 23 يوليو",
    "2026-10-08": "عيد القوات المسلحة",
    # "2026-08-25": "المولد النبوي",   ← مثال للإضافة
}