{% extends "base.html" %}
{% block content %}
{% macro tx(en, ar) %}{{ ar if L == 'ar' else en }}{% endmacro %}
{% macro ico(n) -%}
<svg class="lv-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
{%- if n == 'calendar' %}<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>
{%- elif n == 'user' %}<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>
{%- elif n == 'plus' %}<path d="M12 5v14M5 12h14"/>
{%- elif n == 'trash' %}<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/>
{%- elif n == 'check' %}<path d="M20 6 9 17l-5-5"/>
{%- elif n == 'alert' %}<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>
{%- elif n == 'clock' %}<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>
{%- elif n == 'search' %}<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>
{%- elif n == 'lock' %}<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>
{%- elif n == 'chev-l' %}<path d="m15 18-6-6 6-6"/>
{%- elif n == 'chev-r' %}<path d="m9 18 6-6-6-6"/>
{%- elif n == 'info' %}<circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v5h1"/>
{%- elif n == 'users' %}<circle cx="9" cy="8" r="3.5"/><path d="M2 21c0-3.5 3-5.5 7-5.5s7 2 7 5.5"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M22 21c0-3-2-4.7-4.5-5.3"/>
{%- elif n == 'download' %}<path d="M12 3v12M7 10l5 5 5-5M4 21h16"/>
{%- elif n == 'shield' %}<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>
{%- endif -%}
</svg>
{%- endmacro %}

{% set CODE_GROUPS = [
  (tx('Balance-based leave', 'إجازات من الرصيد'), ['A', 'C', 'ADA']),
  (tx('Other leave', 'إجازات أخرى'), ['S', 'MI', 'W', 'DE', 'D', 'P', 'OFF']),
  (tx('Attendance entries', 'حركات الحضور'), ['M', 'PERM', 'V', 'AD']),
] %}
{% macro type_opts(sel) %}{% for gname, codes in CODE_GROUPS %}<optgroup label="{{ gname }}">{% for c in codes if c in leave_labels %}<option value="{{ c }}" {{ 'selected' if c == sel }}>{{ c }} — {{ t('leave_type_' ~ c) }}</option>{% endfor %}</optgroup>{% endfor %}{% endmacro %}
{% set b = selected_balance %}
{% set emp_codes = employees | map(attribute='code') | list %}
{% set rest = rest_days if rest_days is defined else [4, 5] %}
<div class="lv" dir="{{ DIR }}">
<style>
.lv{--ink:#1c1a2e;--muted:#6a6880;--line:#e9e7f2;--soft:#f6f5fb;--card:#fff;--brand:#5b3fd0;--brand2:#1e5bd8;
  --ok:#2e7d32;--ok-bg:#e8f5e9;--warn:#e65100;--warn-bg:#fff3e0;--bad:#c62828;--bad-bg:#fdecea;--info:#1565c0;--info-bg:#e3f0fd;
  color:var(--ink);font-size:14px;line-height:1.55;max-width:1280px;margin:0 auto;padding-bottom:48px}
.lv *{box-sizing:border-box}
.lv-ico{width:18px;height:18px;flex:none}
.lv-card{background:var(--card);border:1px solid var(--line);border-radius:16px;box-shadow:0 1px 2px rgba(28,26,46,.04),0 6px 20px rgba(28,26,46,.04)}
.lv-card-h{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:18px 22px 0;flex-wrap:wrap}
.lv-card-h h2{margin:0;font-size:16px;font-weight:700;display:flex;align-items:center;gap:8px}
.lv-card-h h2 .lv-ico{color:var(--brand)}
.lv-card-h p{margin:2px 0 0;color:var(--muted);font-size:12.5px}
.lv-card-b{padding:16px 22px 22px}
.lv-grid{display:grid;gap:18px}
.lv-sec{margin-top:22px}

/* hero */
.lv-hero{position:relative;overflow:hidden;border-radius:20px;padding:28px 30px;color:#fff;
  background:linear-gradient(120deg,#1b1a4b 0%,#3b2fa8 52%,#1e5bd8 100%)}
.lv-hero:before,.lv-hero:after{content:"";position:absolute;border-radius:50%;background:rgba(255,255,255,.07)}
.lv-hero:before{width:280px;height:280px;inset-inline-end:-70px;top:-120px}
.lv-hero:after{width:180px;height:180px;inset-inline-end:160px;bottom:-110px}
.lv-hero-in{position:relative;display:flex;gap:24px;align-items:flex-end;justify-content:space-between;flex-wrap:wrap}
.lv-eyebrow{font-size:11.5px;letter-spacing:.14em;font-weight:700;opacity:.75;text-transform:uppercase}
.lv-hero h1{margin:6px 0 6px;font-size:26px;line-height:1.25;font-weight:800}
.lv-hero p{margin:0;max-width:560px;opacity:.85}
.lv-chips{display:flex;gap:10px;flex-wrap:wrap}
.lv-chip{background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.22);backdrop-filter:blur(4px);border-radius:14px;padding:10px 16px;min-width:108px}
.lv-chip b{display:block;font-size:22px;font-weight:800;line-height:1.15}
.lv-chip span{font-size:12px;opacity:.8}

/* toasts */
.lv-note{display:flex;gap:10px;align-items:flex-start;padding:12px 16px;border-radius:12px;margin-top:16px;font-weight:600;border:1px solid transparent}
.lv-note.ok{background:var(--ok-bg);color:var(--ok);border-color:#c8e6c9}
.lv-note.bad{background:var(--bad-bg);color:var(--bad);border-color:#f5c6c2}
.lv-note.info{background:var(--info-bg);color:var(--info);border-color:#c5defa}
.lv-note.warn{background:var(--warn-bg);color:var(--warn);border-color:#ffd9b0}
.lv-note .lv-ico{margin-top:2px}

/* picker */
.lv-pick{display:grid;grid-template-columns:minmax(260px,420px) 1fr;gap:22px;align-items:center}
.lv-pick-ctrl{display:flex;gap:8px;align-items:center}
.lv-field{position:relative;flex:1}
.lv-field .lv-ico{position:absolute;inset-inline-start:12px;top:50%;transform:translateY(-50%);color:var(--muted);pointer-events:none}
.lv input,.lv select,.lv textarea{width:100%;font:inherit;color:var(--ink);background:#fff;border:1.5px solid var(--line);border-radius:10px;padding:10px 12px;transition:border-color .15s,box-shadow .15s}
.lv input:focus,.lv select:focus,.lv textarea:focus{outline:none;border-color:var(--brand);box-shadow:0 0 0 3px rgba(91,63,208,.14)}
.lv-field input{padding-inline-start:38px}
.lv input[readonly]{background:var(--soft);color:var(--muted)}
.lv label{display:block;font-size:12.5px;font-weight:700;margin-bottom:5px;color:#3a3852}
.lv-btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;font:inherit;font-weight:700;border:0;border-radius:10px;padding:10px 18px;cursor:pointer;transition:transform .1s,box-shadow .15s,background .15s}
.lv-btn:active{transform:translateY(1px)}
.lv-btn.pri{background:linear-gradient(135deg,var(--brand),var(--brand2));color:#fff;box-shadow:0 4px 14px rgba(59,47,168,.28)}
.lv-btn.pri:hover{box-shadow:0 6px 18px rgba(59,47,168,.38)}
.lv-btn.ghost{background:var(--soft);color:var(--ink);border:1px solid var(--line)}
.lv-btn.ghost:hover{background:#eeecf7}
.lv-btn.sq{padding:10px;width:42px}
.lv-btn.del{background:transparent;color:var(--bad);padding:6px 8px;border-radius:8px}
.lv-btn.del:hover{background:var(--bad-bg)}
.lv-btn.block{width:100%}
.lv-emp{display:flex;gap:14px;align-items:center;min-width:0}
.lv-av{width:52px;height:52px;border-radius:16px;flex:none;display:grid;place-items:center;font-weight:800;font-size:19px;color:#fff;background:linear-gradient(135deg,var(--brand),var(--brand2))}
.lv-emp h3{margin:0;font-size:17px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lv-meta{display:flex;flex-wrap:wrap;gap:6px 14px;color:var(--muted);font-size:12.5px;margin-top:3px}
.lv-meta span{display:inline-flex;gap:5px;align-items:center}
.lv-meta b{color:var(--ink);font-weight:700}

/* kpis */
.lv-kpis{display:grid;grid-template-columns:1.25fr repeat(4,1fr);gap:16px}
.lv-kpi{padding:18px 20px;position:relative;overflow:hidden}
.lv-kpi:before{content:"";position:absolute;inset-inline-start:0;top:0;bottom:0;width:4px;background:var(--c,var(--brand))}
.lv-kpi small{display:block;color:var(--muted);font-weight:700;font-size:12px}
.lv-kpi .v{font-size:30px;font-weight:800;line-height:1.15;margin:4px 0 2px;color:var(--c,var(--ink))}
.lv-kpi .v i{font-style:normal;font-size:13px;color:var(--muted);font-weight:600;margin-inline-start:4px}
.lv-kpi .s{font-size:12px;color:var(--muted)}
.lv-bar{height:7px;background:#edebf6;border-radius:99px;overflow:hidden;margin:9px 0 5px}
.lv-bar i{display:block;height:100%;border-radius:99px;background:var(--c,var(--brand));width:var(--w,0%);transition:width .6s}
.lv-kpi.main{display:flex;gap:16px;align-items:center;background:linear-gradient(135deg,#faf9ff,#f1f4ff)}
.lv-ring{width:92px;height:92px;flex:none;position:relative}
.lv-ring svg{transform:rotate(-90deg)}
.lv-ring b{position:absolute;inset:0;display:grid;place-items:center;font-size:22px;font-weight:800}
.lv-lock{display:inline-flex;gap:5px;align-items:center;font-size:11.5px;font-weight:700;color:var(--warn);background:var(--warn-bg);padding:3px 9px;border-radius:99px;margin-top:4px}

/* two columns */
.lv-two{display:grid;grid-template-columns:1.1fr .9fr;gap:18px;align-items:start}

/* tables */
.lv-tw{overflow-x:auto}
.lv table{width:100%;border-collapse:collapse}
.lv th{font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:700;text-align:start;padding:10px 12px;border-bottom:1.5px solid var(--line);white-space:nowrap;background:var(--soft)}
.lv td{padding:12px;border-bottom:1px solid var(--line);vertical-align:middle}
.lv tbody tr:last-child td{border-bottom:0}
.lv tbody tr:hover td{background:#fbfaff}
.lv th:first-child{border-start-start-radius:10px}.lv th:last-child{border-start-end-radius:10px}
.lv .num{font-variant-numeric:tabular-nums;font-weight:700;white-space:nowrap}
.lv .dim{color:var(--muted);font-weight:500}
.lv tr.exp td{opacity:.55}
.lv tr.cur td{background:#f7f5ff}
.lv-mini{height:6px;width:96px;border-radius:99px;background:#edebf6;overflow:hidden;margin-top:5px}
.lv-mini i{display:block;height:100%;background:var(--c,var(--brand));width:var(--w,0%);border-radius:99px}
.lv-badge{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:700;padding:3px 10px;border-radius:99px;background:var(--bb,#eceaf6);color:var(--bc,#3b2fa8);white-space:nowrap}
.lv-badge.code{font-family:ui-monospace,Consolas,monospace;border-radius:8px;padding:2px 8px;font-size:11.5px}
.lv-tag-A{--bb:#e3f0fd;--bc:#1565c0}.lv-tag-C{--bb:#fff3e0;--bc:#e65100}.lv-tag-S{--bb:#fdecea;--bc:#c62828}
.lv-tag-DE{--bb:#eceff1;--bc:#455a64}.lv-tag-W{--bb:#fce4ec;--bc:#ad1457}.lv-tag-MI{--bb:#fce4ec;--bc:#ad1457}
.lv-tag-M{--bb:#e0f7fa;--bc:#00838f}.lv-tag-PERM{--bb:#e0f7fa;--bc:#00838f}.lv-tag-D{--bb:#ffebee;--bc:#b71c1c}
.lv-tag-P{--bb:#e8f5e9;--bc:#2e7d32}.lv-tag-OFF{--bb:#eceff1;--bc:#455a64}.lv-tag-V{--bb:#e8f5e9;--bc:#2e7d32}
.lv-tag-ADA{--bb:#ede7f6;--bc:#5e35b1}.lv-tag-AD{--bb:#ede7f6;--bc:#5e35b1}
.lv-empty{text-align:center;color:var(--muted);padding:34px 10px}
.lv-empty .lv-ico{width:34px;height:34px;opacity:.4;margin-bottom:6px}

/* form */
.lv-fg{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.lv-fg .full{grid-column:1/-1}
.lv-hint{font-size:12px;color:var(--muted);margin-top:4px}
.lv-avail{display:flex;gap:10px;align-items:center;padding:10px 14px;border-radius:12px;background:var(--info-bg);color:var(--info);font-weight:700;font-size:13px}
.lv-avail.warn{background:var(--warn-bg);color:var(--warn)}
.lv-avail.bad{background:var(--bad-bg);color:var(--bad)}
.lv details.lv-appr{border:1.5px dashed var(--line);border-radius:12px;padding:10px 14px}
.lv details.lv-appr summary{cursor:pointer;font-weight:700;color:#3a3852}
.lv-check{display:flex;gap:9px;align-items:flex-start;font-weight:600;margin-top:10px;cursor:pointer}
.lv-check input{width:auto;margin-top:4px;accent-color:var(--brand)}
.lv-seg{display:flex;background:var(--soft);border:1px solid var(--line);border-radius:12px;padding:4px;gap:4px}
.lv-seg label{flex:1;margin:0;text-align:center;cursor:pointer;font-weight:700;font-size:12.5px;border-radius:9px;padding:8px 6px;color:var(--muted);transition:.15s}
.lv-seg input{position:absolute;opacity:0;pointer-events:none;width:0}
.lv-seg input:checked+span{display:block}
.lv-seg label:has(input:checked){background:#fff;color:var(--brand);box-shadow:0 1px 4px rgba(28,26,46,.12)}

/* team */
.lv-tools{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.lv-pills{display:flex;gap:6px;flex-wrap:wrap}
.lv-pill{border:1px solid var(--line);background:#fff;border-radius:99px;padding:6px 14px;font:inherit;font-weight:700;font-size:12.5px;color:var(--muted);cursor:pointer}
.lv-pill.on{background:var(--brand);border-color:var(--brand);color:#fff}
.lv tr.pick{cursor:pointer}
.lv tr.sel td{background:#f0edff}
.lv-legend{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}
.lv-legend div{display:flex;gap:10px;align-items:center;padding:8px 10px;border:1px solid var(--line);border-radius:10px;background:#fff}
.lv-rules{margin-top:14px;padding:14px 16px;background:var(--soft);border-radius:12px;color:#4a4863;font-size:13px}
.lv details>summary{list-style:none}
.lv details>summary::-webkit-details-marker{display:none}


/* ===== جدول احترافي ===== */
.lv-filters{display:flex;gap:10px;flex-wrap:wrap;align-items:center;padding:14px 22px 0}
.lv-filters .lv-field{flex:1;min-width:230px;max-width:360px}
.lv-filters select{width:auto;min-width:150px}
.lv-seg.sm label{padding:7px 14px;white-space:nowrap}
.lv-bar-tools{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.lv-scroll{max-height:620px;overflow:auto;border:1px solid #dcd9ea;border-radius:12px;margin:14px 22px 0;background:#fff;position:relative}
.lv-gt{width:100%;min-width:1240px;table-layout:fixed;border-collapse:separate;border-spacing:0;font-size:13.5px}
.lv-gt thead th{position:sticky;top:0;z-index:3;background:#1f2347;color:#fff;font-size:12px;letter-spacing:.03em;text-transform:none;font-weight:700;padding:12px 10px;border-bottom:0;text-align:start;white-space:nowrap}
.lv-gt thead th.c,.lv-gt td.c,.lv-gt input.c{text-align:center}
.lv-gt thead th[data-sort]{cursor:pointer;user-select:none}
.lv-gt thead th[data-sort]:hover{background:#2b3063}
.lv-gt thead th[data-sort]:after{content:"↕";opacity:.35;margin-inline-start:6px;font-size:11px}
.lv-gt thead th[data-dir=asc]:after{content:"▲";opacity:1}
.lv-gt thead th[data-dir=desc]:after{content:"▼";opacity:1}
.lv-gt tbody td{padding:0;border-bottom:1px solid #ecebf5;border-inline-end:1px solid #f1f0f8;height:42px;vertical-align:middle;background:#fff}
.lv-gt tbody td:last-child{border-inline-end:0}
.lv-gt tbody tr.gr:nth-child(even) td{background:#fbfbfe}
.lv-gt tbody tr.gr:hover td{background:#f3f1ff}
.lv-gt tbody{counter-reset:rn}
.lv-gt td.rn{text-align:center;color:#9a98b3;font-size:12px;font-weight:700;border-inline-start:4px solid var(--bc,#cfcbe6);background:#f6f5fb!important}
.lv-gt td.rn:before{counter-increment:rn;content:counter(rn)}
.lv-gt td.emp{padding:0 10px;line-height:1.25}
.lv-gt td.emp b{display:block;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lv-gt td.emp span{font-size:11.5px;color:var(--muted)}
.lv-gt td input,.lv-gt td select{width:100%;height:41px;border:0;border-radius:0;background:transparent;padding:0 10px;font-size:13.5px;box-shadow:none;margin:0}
.lv-gt td input[type=checkbox]{width:18px;height:18px;accent-color:var(--brand);display:block;margin:auto}
.lv-gt td select{font-weight:700;background:var(--bb,#eceaf6);color:var(--bc,#3b2fa8);cursor:pointer}
.lv-gt td input:focus,.lv-gt td select:focus{outline:2px solid var(--brand);outline-offset:-2px;background:#fff;color:var(--ink);border:0;box-shadow:none;position:relative;z-index:1}
.lv-gt td input:disabled{opacity:.35;background:transparent}
.lv-gt tr.dirty td{background:#fff8ec!important}
.lv-gt tr.dirty td.rn{background:#ffe9c2!important}
.lv-gt tr.isnew td{background:#f1eeff!important}
.lv-gt tr.errrow td{background:var(--bad-bg)!important;color:var(--bad);font-weight:700;padding:9px 14px;font-size:12.5px;height:auto;border-inline-end:0}
.lv-gt .acts{display:flex;gap:4px;justify-content:center;padding:0 6px}
.lv-gt .acts .lv-btn{padding:6px 9px}
.lv-gt .js-save{background:var(--ok);color:#fff}
.lv-gt .js-save[hidden]{display:none}
.lv-gt tfoot td{position:sticky;bottom:0;z-index:3;background:#eeecf8;font-weight:800;padding:11px 10px;border-top:2px solid #cfcbe6;font-variant-numeric:tabular-nums}
.lv-kbd{font-size:11.5px;color:var(--muted)}
.lv-kbd kbd{background:var(--soft);border:1px solid var(--line);border-bottom-width:2px;border-radius:5px;padding:0 6px;font:inherit;font-weight:700}
/* جدول أرصدة الفريق */
.lv-dt thead th{position:sticky;top:0;z-index:2;background:#1f2347;color:#fff;text-transform:none;letter-spacing:.02em;padding:12px 12px}
.lv-dt th:first-child,.lv-dt th:last-child{border-radius:0}
.lv-dt thead th[data-sort]{cursor:pointer;user-select:none}
.lv-dt thead th[data-sort]:hover{background:#2b3063}
.lv-dt thead th[data-sort]:after{content:"↕";opacity:.35;margin-inline-start:6px;font-size:11px}
.lv-dt thead th[data-dir=asc]:after{content:"▲";opacity:1}
.lv-dt thead th[data-dir=desc]:after{content:"▼";opacity:1}
.lv-dt tbody tr:nth-child(even) td{background:#fbfbfe}
.lv-dt tbody tr:hover td{background:#f3f1ff}
.lv-dt tbody tr.sel td{background:#e9e4ff!important}
.lv-dtw{max-height:560px;overflow:auto;border:1px solid #dcd9ea;border-radius:12px;background:#fff}
@media (max-width:1100px){.lv-kpis{grid-template-columns:repeat(2,1fr)}.lv-kpi.main{grid-column:1/-1}.lv-two{grid-template-columns:1fr}.lv-pick{grid-template-columns:1fr}}
@media (max-width:560px){.lv-fg{grid-template-columns:1fr}.lv-hero{padding:22px 18px}.lv-hero h1{font-size:21px}.lv-kpis{grid-template-columns:1fr}}
@media print{.lv-btn,.lv-pick-ctrl,form{display:none!important}}
</style>

{# ───────── هيرو ───────── #}
<section class="lv-hero">
  <div class="lv-hero-in">
    <div>
      <div class="lv-eyebrow">{{ t('leave_control') }}</div>
      <h1>{{ t('leave_hero_title') }}</h1>
      <p>{{ t('leave_hero_sub') }}</p>
    </div>
    <div class="lv-chips">
      <div class="lv-chip"><b>{{ employees|length }}</b><span>{{ tx('Active employees', 'موظف فعّال') }}</span></div>
      <div class="lv-chip"><b>{{ entry_total }}</b><span>{{ tx('Entries for selected', 'حركة للموظف المختار') }}</span></div>
      <div class="lv-chip"><b>{{ b.current_year if b else today[:4] }}</b><span>{{ t('leave_year') }}</span></div>
    </div>
  </div>
</section>

{% if error %}<div class="lv-note bad" role="alert">{{ ico('alert') }}<div>{{ error }}</div></div>{% endif %}
{% if saved %}<div class="lv-note ok" id="lvToast">{{ ico('check') }}<div>{{ t('leave_saved') }}</div></div>{% endif %}
{% if request.args.get('deleted') %}<div class="lv-note ok" id="lvToast">{{ ico('check') }}<div>{{ t('leave_deleted') }}</div></div>{% endif %}

{% if not employees %}
  <div class="lv-card lv-sec"><div class="lv-empty">{{ ico('users') }}<div>{{ t('leave_no_employees') }}</div></div></div>
{% else %}

{# ───────── اختيار الموظف ───────── #}
<section class="lv-card lv-sec">
  <div class="lv-card-b">
    <div class="lv-pick">
      <div>
        <label for="lvEmp">{{ t('leave_employee_select') }}</label>
        <div class="lv-pick-ctrl">
          <button type="button" class="lv-btn ghost sq" id="lvPrev" title="{{ t('prev') }}">{{ ico('chev-l' if DIR == 'ltr' else 'chev-r') }}</button>
          <div class="lv-field">
            {{ ico('search') }}
            <input id="lvEmp" list="lvEmps" autocomplete="off" placeholder="{{ t('att_search') }}"
                   value="{{ selected.code }} — {{ selected.name }}">
            <datalist id="lvEmps">
              {% for e in employees %}<option value="{{ e.code }} — {{ e.name }}">{% endfor %}
            </datalist>
          </div>
          <button type="button" class="lv-btn ghost sq" id="lvNext" title="{{ t('next') }}">{{ ico('chev-r' if DIR == 'ltr' else 'chev-l') }}</button>
        </div>
        <div class="lv-hint">{{ t('leave_select_hint') }}</div>
      </div>
      {% if selected %}
      <div class="lv-emp">
        <div class="lv-av">{{ (selected.name or '?')[:1] }}</div>
        <div style="min-width:0">
          <h3>{{ selected.name }}</h3>
          <div class="lv-meta">
            <span>{{ t('code') }}: <b>{{ selected.code }}</b></span>
            {% if selected.job %}<span><b>{{ selected.job }}</b></span>{% endif %}
            {% if selected.department %}<span>{{ selected.department }}</span>{% endif %}
            <span>{{ t('hire_date') }}: <b>{{ selected.hire_date|pdate or '—' }}</b></span>
            {% if b %}<span>{{ t('tenure') }}: <b>{% if b.service_months >= 12 %}{{ b.service_months // 12 }} {{ t('y') }} {{ b.service_months % 12 }} {{ t('mo') }}{% else %}{{ b.service_months }} {{ t('mo') }}{% endif %}</b></span>{% endif %}
          </div>
        </div>
      </div>
      {% endif %}
    </div>
  </div>
</section>

{% if selected and b %}

{% if not b.available %}
<div class="lv-note warn">{{ ico('lock') }}<div>{{ t('leave_waiting', days=b.waiting_days) }}</div></div>
{% endif %}

{# ───────── كروت الأرصدة ───────── #}
{% set ent = b.entitlement_total or 0 %}
{% set pct_total = ((b.total_balance / ent * 100) if ent else 0)|round(0)|int %}
{% set pct_c = ((b.casual_balance / b.casual_earned * 100) if b.casual_earned else 0)|round(0)|int %}
{% set pct_a = ((b.annual_balance / b.annual_earned * 100) if b.annual_earned else 0)|round(0)|int %}
{% set pct_s = (b.sick_remaining_3y / 90 * 100)|round(0)|int %}
<section class="lv-kpis lv-sec">
  <div class="lv-card lv-kpi main" style="--c:var(--brand)">
    <div class="lv-ring">
      <svg width="92" height="92" viewBox="0 0 92 92">
        <circle cx="46" cy="46" r="38" fill="none" stroke="#e6e3f5" stroke-width="9"/>
        <circle cx="46" cy="46" r="38" fill="none" stroke="url(#lvg)" stroke-width="9" stroke-linecap="round"
                stroke-dasharray="{{ (238.76 * pct_total / 100)|round(1) }} 238.76"/>
        <defs><linearGradient id="lvg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#5b3fd0"/><stop offset="1" stop-color="#1e5bd8"/></linearGradient></defs>
      </svg>
      <b>{{ b.total_balance|gnum }}</b>
    </div>
    <div>
      <small>{{ t('leave_total_balance') }}</small>
      <div class="s">{{ t('leave_current_year') }} · {{ b.current_year }}</div>
      <div class="s">{{ tx('Entitlement', 'الاستحقاق') }}: <b>{{ ent|gnum }}</b> {{ t('days') }}</div>
      {% if not b.available %}<span class="lv-lock">{{ ico('lock') }}{{ t('leave_locked') }}</span>{% endif %}
    </div>
  </div>

  <div class="lv-card lv-kpi" style="--c:#e65100">
    <small>{{ t('leave_casual_balance') }}</small>
    <div class="v">{{ b.casual_balance|gnum }}<i>/ {{ b.casual_earned|gnum }}</i></div>
    <div class="lv-bar" style="--w:{{ pct_c }}%"><i></i></div>
    <div class="s">{{ t('leave_casual_used') }}: {{ b.casual_used|gnum }}</div>
  </div>

  <div class="lv-card lv-kpi" style="--c:#1565c0">
    <small>{{ t('leave_annual_balance') }}</small>
    <div class="v">{{ b.annual_balance|gnum }}<i>/ {{ b.annual_earned|gnum }}</i></div>
    <div class="lv-bar" style="--w:{{ pct_a }}%"><i></i></div>
    <div class="s">{{ t('leave_annual_used') }}: {{ b.annual_used|gnum }}</div>
  </div>

  <div class="lv-card lv-kpi" style="--c:#c62828">
    <small>{{ t('leave_sick_remaining') }}</small>
    <div class="v">{{ b.sick_remaining_3y|gnum }}<i>/ 90</i></div>
    <div class="lv-bar" style="--w:{{ pct_s }}%"><i></i></div>
    <div class="s">{{ tx('Used', 'المستخدم') }}: {{ b.sick_used_3y|gnum }}</div>
  </div>

  <div class="lv-card lv-kpi" style="--c:#00838f">
    <small>{{ t('leave_permissions_remaining') }}</small>
    <div class="v">{{ b.permissions_remaining }}<i>/ 2</i></div>
    <div class="lv-bar" style="--w:{{ (b.permissions_remaining / 2 * 100)|int }}%"><i></i></div>
    <div class="s">{{ tx('Used this month', 'المستخدم هذا الشهر') }}: {{ b.permissions_used }}</div>
  </div>
</section>

{# ───────── سنة بسنة + تسجيل حركة ───────── #}
<section class="lv-two lv-sec">
  <div class="lv-grid">
    <div class="lv-card">
      <div class="lv-card-h">
        <div><h2>{{ ico('calendar') }}{{ t('leave_by_year') }}</h2><p>{{ t('leave_year_policy_note') }}</p></div>
      </div>
      <div class="lv-card-b lv-tw">
        <table>
          <thead><tr>
            <th>{{ t('leave_year') }}</th><th>{{ tx('Entitlement', 'الاستحقاق') }}</th>
            <th>{{ t('leave_casual_balance') }}</th><th>{{ t('leave_annual_balance') }}</th><th>{{ tx('Remaining', 'المتبقي') }}</th>
          </tr></thead>
          <tbody>
          {% for y in b.yearly_balances %}
            {% set yp = ((y.total_balance / y.entitlement_total * 100) if y.entitlement_total else 0)|int %}
            <tr class="{{ 'cur' if y.current }} {{ 'exp' if y.expired }}">
              <td class="num">{{ y.year }}
                {% if y.current %}<span class="lv-badge" style="--bb:#ede7f6;--bc:#5e35b1">{{ tx('Current', 'الحالية') }}</span>
                {% elif y.expired %}<div class="dim" style="font-size:11px;font-weight:500">{{ t('leave_expired') }}</div>{% endif %}
              </td>
              <td class="num">{{ y.entitlement_total|gnum }}</td>
              <td class="num">{{ y.casual_balance|gnum }} <span class="dim">/ {{ y.casual_earned|gnum }}</span></td>
              <td class="num">{{ y.annual_balance|gnum }} <span class="dim">/ {{ y.annual_earned|gnum }}</span></td>
              <td class="num">{{ y.total_balance|gnum }}
                <div class="lv-mini" style="--w:{{ yp }}%;--c:{{ '#9e9ab5' if y.expired else '#5b3fd0' }}"><i></i></div>
                {% if y.current and not y.available %}<div class="dim" style="font-size:11px">{{ t('leave_locked') }}</div>{% endif %}
              </td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
    </div>

    {# ───── سياسة التعويض ───── #}
    <div class="lv-card">
      <div class="lv-card-h">
        <div><h2>{{ ico('shield') }}{{ t('leave_compensation') }}</h2><p>{{ t('leave_compensation_hint') }}</p></div>
      </div>
      <div class="lv-card-b">
        <form method="post" action="{{ url_for('leaves') }}">
          <input type="hidden" name="action" value="save_policy">
          <input type="hidden" name="employee_code" value="{{ selected_code }}">
          <div class="lv-fg">
            {% for fname, flabel in (('weekend_comp', t('leave_weekend_policy')), ('season_comp', t('leave_season_policy'))) %}
            {% set cur = selected_policy.get(fname, '') %}
            <div>
              <label>{{ flabel }}</label>
              <div class="lv-seg">
                <label><input type="radio" name="{{ fname }}" value="" {{ 'checked' if not cur }}><span>{{ t('leave_not_set') }}</span></label>
                <label><input type="radio" name="{{ fname }}" value="money" {{ 'checked' if cur == 'money' }}><span>{{ t('leave_money') }}</span></label>
                <label><input type="radio" name="{{ fname }}" value="leave" {{ 'checked' if cur == 'leave' }}><span>{{ t('leave_as_days') }}</span></label>
              </div>
            </div>
            {% endfor %}
            <div class="full lv-hint">{{ ico('info') }} {{ t('leave_comp_save_note') }}</div>
            <div class="full"><button class="lv-btn ghost" type="submit">{{ ico('check') }}{{ t('leave_save_policy') }}</button></div>
          </div>
        </form>
      </div>
    </div>
  </div>

  {# ───── فورم تسجيل حركة ───── #}
  <div class="lv-card" style="position:sticky;top:12px">
    <div class="lv-card-h">
      <div><h2>{{ ico('plus') }}{{ t('leave_add_entry') }}</h2><p>{{ t('leave_add_hint') }}</p></div>
    </div>
    <div class="lv-card-b">
      <form method="post" action="{{ url_for('leaves') }}" id="lvForm" class="lv-grid" style="gap:14px">
        <input type="hidden" name="action" value="save_entry">
        <input type="hidden" name="employee_code" value="{{ selected_code }}">

        <div>
          <label for="lvType">{{ t('leave_kind') }}</label>
          <select name="leave_code" id="lvType" required>
            {% for gname, codes in CODE_GROUPS %}
            <optgroup label="{{ gname }}">
              {% for c in codes if c in leave_labels %}
              <option value="{{ c }}" data-mode="{{ 'hours' if c == 'PERM' else ('both' if c == 'M' else 'days') }}">{{ c }} — {{ t('leave_type_' ~ c) }}</option>
              {% endfor %}
            </optgroup>
            {% endfor %}
          </select>
        </div>

        <div id="lvAvail" class="lv-avail" hidden></div>

        <div class="lv-fg">
          <div><label for="lvFrom">{{ t('leave_start_date') }}</label><input type="date" name="leave_date" id="lvFrom" value="{{ today }}" required></div>
          <div><label for="lvTo">{{ t('leave_end_date') }}</label><input type="date" name="end_date" id="lvTo" value="{{ today }}" required></div>
          <div id="lvDaysBox"><label for="lvDays">{{ t('leave_days_count') }}</label><input type="number" name="days" id="lvDays" min="0" step="0.5" value="1"></div>
          <div id="lvHoursBox" hidden><label for="lvHours">{{ t('leave_hours_count') }}</label><input type="number" name="hours" id="lvHours" min="0" max="12" step="0.25" value="0"></div>
        </div>
        <div class="lv-hint" id="lvHelp" style="margin-top:-6px"></div>

        <details class="lv-appr" id="lvAppr">
          <summary>{{ t('leave_manager') }} <span class="dim">· {{ t('leave_manager_hint') }}</span></summary>
          <div style="margin-top:12px">
            <input type="text" name="manager_name" placeholder="{{ t('leave_manager') }}" maxlength="80">
            <label class="lv-check"><input type="checkbox" name="manager_approved"><span>{{ t('leave_manager_signed') }}</span></label>
            <div class="lv-hint">{{ t('leave_conversion_hint') }}</div>
          </div>
        </details>

        <div><label for="lvNotes">{{ t('notes') }}</label><textarea name="notes" id="lvNotes" rows="2" placeholder="{{ t('leave_notes_hint') }}"></textarea></div>

        <button class="lv-btn pri block" type="submit">{{ ico('check') }}{{ t('leave_save_entry') }}</button>
      </form>
    </div>
  </div>
</section>

{# ───────── سجل الإجازات — جدول احترافي قابل للتعديل ───────── #}
<section class="lv-card lv-sec" id="lvRegister">
  <div class="lv-card-h">
    <div>
      <h2>{{ ico('clock') }}{{ tx('Leave register', 'سجل الإجازات والحركات') }}</h2>
      <p>{{ tx('Click any cell to edit · Enter saves the row · Ctrl+↑/↓ moves between rows', 'اضغطي على أي خانة للتعديل · Enter يحفظ الصف · Ctrl+↑/↓ للتنقل بين الصفوف') }}</p>
    </div>
    <div class="lv-bar-tools">
      <button type="button" class="lv-btn pri" id="lvSaveAll" hidden>{{ ico('check') }}<span>{{ tx('Save all', 'حفظ الكل') }}</span> (<b id="lvDirtyN">0</b>)</button>
      <button type="button" class="lv-btn ghost" id="lvExport">{{ ico('download') }}CSV</button>
      <button type="button" class="lv-btn pri" id="lvAddRow">{{ ico('plus') }}{{ tx('New row', 'صف جديد') }}</button>
    </div>
  </div>

  <div class="lv-filters">
    <div class="lv-seg sm" id="lvScope">
      <label><input type="radio" name="lvscope" value="sel" checked><span>{{ tx('Selected employee', 'الموظف المختار') }}</span></label>
      <label><input type="radio" name="lvscope" value="all"><span>{{ tx('All employees', 'كل الموظفين') }} ({{ register_total }})</span></label>
    </div>
    <div class="lv-field">{{ ico('search') }}<input id="lvGQ" placeholder="{{ tx('Search name, code, notes…', 'بحث بالاسم أو الكود أو الملاحظات…') }}"></div>
    <select id="lvGType" aria-label="{{ t('leave_kind') }}">
      <option value="">{{ tx('All types', 'كل الأنواع') }}</option>
      {% for c in leave_labels %}<option value="{{ c }}">{{ c }} — {{ t('leave_type_' ~ c) }}</option>{% endfor %}
    </select>
    <select id="lvGYear" aria-label="{{ t('leave_year') }}"><option value="">{{ tx('All years', 'كل السنوات') }}</option></select>
    <button type="button" class="lv-btn ghost" id="lvGReset">{{ t('reset') }}</button>
  </div>

  <div class="lv-scroll">
    <table class="lv-gt scope-sel" id="lvGrid" data-code="{{ selected_code }}">
      <colgroup>
        <col style="width:46px"><col class="c-emp" style="width:150px"><col style="width:200px">
        <col style="width:130px"><col style="width:130px"><col style="width:80px"><col style="width:80px">
        <col style="width:130px"><col style="width:56px"><col><col style="width:96px">
      </colgroup>
      <thead><tr>
        <th class="c">#</th>
        <th data-sort="emp">{{ t('employee') }}</th>
        <th data-sort="type">{{ t('leave_kind') }}</th>
        <th data-sort="from">{{ t('leave_start_date') }}</th>
        <th data-sort="to">{{ t('leave_end_date') }}</th>
        <th data-sort="days" class="c">{{ t('leave_days_count') }}</th>
        <th data-sort="hours" class="c">{{ t('leave_hours_count') }}</th>
        <th>{{ t('leave_manager') }}</th>
        <th class="c">{{ t('leave_signed') }}</th>
        <th>{{ t('notes') }}</th>
        <th></th>
      </tr></thead>
      <tbody>
      {% for e in register %}
        <tr class="gr lv-tag-{{ e.leave_code }}" data-id="{{ e.id }}" data-code="{{ e.code }}" data-name="{{ (e.emp_name or '')|lower }}" data-year="{{ e.leave_date[:4] }}">
          <td class="rn"></td>
          <td class="emp"><b>{{ e.emp_name or '—' }}</b><span>{{ e.code }}</span></td>
          <td><select data-f="leave_code">{{ type_opts(e.leave_code) }}</select></td>
          <td><input type="date" data-f="leave_date" value="{{ e.leave_date }}"></td>
          <td><input type="date" data-f="end_date" value="{{ e.end_date or e.leave_date }}"></td>
          <td><input type="number" class="c" data-f="days" min="0" step="0.5" value="{{ e.days|gnum }}"></td>
          <td><input type="number" class="c" data-f="hours" min="0" max="12" step="0.25" value="{{ e.hours|gnum }}"></td>
          <td><input data-f="manager_name" maxlength="80" value="{{ e.manager_name }}"></td>
          <td class="c"><input type="checkbox" data-f="manager_approved" {{ 'checked' if e.manager_approved }}></td>
          <td><input data-f="notes" value="{{ e.notes }}"></td>
          <td><div class="acts">
            <button type="button" class="lv-btn js-save" hidden title="{{ tx('Save row', 'حفظ الصف') }}">{{ ico('check') }}</button>
            <button type="button" class="lv-btn del js-del" title="{{ t('delete') }}">{{ ico('trash') }}</button>
          </div></td>
        </tr>
      {% endfor %}
      </tbody>
      <tfoot><tr>
        <td colspan="5" id="lvFootLabel"></td>
        <td class="c" id="lvSumDays">0</td>
        <td class="c" id="lvSumHours">0</td>
        <td colspan="4"></td>
      </tr></tfoot>
    </table>
    <div class="lv-empty" id="lvGridEmpty" hidden>{{ ico('calendar') }}<div>{{ t('leave_no_entries') }}</div></div>
  </div>
  <div class="lv-card-b" style="padding-top:10px">
    <span class="lv-kbd"><kbd>Enter</kbd> {{ tx('save row', 'حفظ الصف') }} · <kbd>Tab</kbd> {{ tx('next cell', 'الخانة التالية') }} · {{ tx('click a column title to sort', 'اضغطي على عنوان العمود للترتيب') }}</span>
  </div>

  <template id="lvNewRow">
    <tr class="gr isnew dirty lv-tag-A" data-id="" data-code="">
      <td class="rn"></td>
      <td class="emp"><input data-f="employee" list="lvEmps" autocomplete="off" placeholder="{{ t('att_search') }}"></td>
      <td><select data-f="leave_code">{{ type_opts('A') }}</select></td>
      <td><input type="date" data-f="leave_date" value="{{ today }}"></td>
      <td><input type="date" data-f="end_date" value="{{ today }}"></td>
      <td><input type="number" class="c" data-f="days" min="0" step="0.5" value="1"></td>
      <td><input type="number" class="c" data-f="hours" min="0" max="12" step="0.25" value="0"></td>
      <td><input data-f="manager_name" maxlength="80" placeholder="{{ t('leave_manager') }}"></td>
      <td class="c"><input type="checkbox" data-f="manager_approved"></td>
      <td><input data-f="notes" placeholder="{{ t('leave_notes_hint') }}"></td>
      <td><div class="acts">
        <button type="button" class="lv-btn js-save" title="{{ tx('Save row', 'حفظ الصف') }}">{{ ico('check') }}</button>
        <button type="button" class="lv-btn del js-cancel" title="{{ tx('Discard', 'إلغاء') }}">{{ ico('trash') }}</button>
      </div></td>
    </tr>
  </template>
</section>
<script>
(function () {
  var grid = document.getElementById('lvGrid'); if (!grid) return;
  var tb = grid.tBodies[0], sel = grid.getAttribute('data-code');
  var API = {{ url_for('leaves_api_save')|tojson }}, BASE = {{ url_for('leaves')|tojson }};
  var DEL = {{ url_for('delete_leave_entry', entry_id=0)|tojson }};
  var SEL_LABEL = {{ (selected.code ~ ' — ' ~ selected.name)|tojson }};
  var M = {net: {{ tx('Network error — try again.', 'مشكلة في الاتصال — حاولي تاني.')|tojson }},
           del: {{ t('leave_delete_confirm')|tojson }}, rows: {{ tx('rows', 'صف')|tojson }},
           total: {{ tx('Total (shown)', 'الإجمالي (المعروض)')|tojson }}};
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var scope = new URLSearchParams(location.search).get('scope') === 'all' ? 'all' : 'sel';

  /* ───── أنماط الصف ───── */
  function mode(tr) {
    var v = $('[data-f=leave_code]', tr).value;
    var days = $('[data-f=days]', tr), hrs = $('[data-f=hours]', tr), to = $('[data-f=end_date]', tr), from = $('[data-f=leave_date]', tr);
    tr.className = tr.className.replace(/lv-tag-\S+/, 'lv-tag-' + v);
    hrs.disabled = !(v === 'PERM' || v === 'M'); days.disabled = v === 'PERM';
    if (v === 'PERM') { days.value = 0; to.value = from.value; to.disabled = true; if (!+hrs.value) hrs.value = 1; }
    else { to.disabled = false; if (hrs.disabled) hrs.value = 0; }
  }
  function empCode(tr) {
    var i = $('[data-f=employee]', tr);
    return i ? i.value.split(' — ')[0].trim() : tr.getAttribute('data-code');
  }
  function data(tr) {
    var d = {id: tr.getAttribute('data-id') || null, employee_code: empCode(tr)};
    $$('[data-f]', tr).forEach(function (el) { var f = el.getAttribute('data-f'); if (f !== 'employee') d[f] = el.type === 'checkbox' ? el.checked : el.value; });
    return d;
  }
  function clearErr(tr) { var n = tr.nextElementSibling; if (n && n.classList.contains('errrow')) n.remove(); }
  function showErr(tr, msg) {
    clearErr(tr);
    var r = document.createElement('tr'); r.className = 'errrow';
    var td = document.createElement('td'); td.colSpan = 11; td.textContent = msg; r.appendChild(td);
    tr.parentNode.insertBefore(r, tr.nextSibling); tr.scrollIntoView({block: 'nearest', behavior: 'smooth'});
  }
  function saveRow(tr) {
    clearErr(tr);
    return fetch(API, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data(tr))})
      .then(function (r) { return r.json(); })
      .then(function (j) { if (!j.ok) { showErr(tr, j.error || M.net); return false; } return true; })
      .catch(function () { showErr(tr, M.net); return false; });
  }
  function done(flag) {
    var u = BASE + '?code=' + encodeURIComponent(sel) + '&' + flag + '=1' + (scope === 'all' ? '&scope=all' : '');
    location.href = u;
  }
  function dirtyCount() { var n = $$('tr.dirty', tb).length; $('#lvDirtyN').textContent = n; $('#lvSaveAll').hidden = n < 2; }

  /* ───── الفلاتر والإجماليات ───── */
  var years = {};
  $$('tr.gr', tb).forEach(function (r) { var y = r.getAttribute('data-year'); if (y) years[y] = 1; });
  Object.keys(years).sort().reverse().forEach(function (y) { var o = document.createElement('option'); o.value = y; o.textContent = y; $('#lvGYear').appendChild(o); });
  function fmt(x) { return String(+x.toFixed(2)); }
  function filter() {
    var q = ($('#lvGQ').value || '').trim().toLowerCase(), ty = $('#lvGType').value, yr = $('#lvGYear').value, n = 0, sd = 0, sh = 0;
    grid.classList.toggle('scope-sel', scope === 'sel'); grid.classList.toggle('scope-all', scope === 'all');
    $$('tr.gr', tb).forEach(function (r) {
      var isnew = r.classList.contains('isnew');
      var code = r.getAttribute('data-code') || '';
      var ok = isnew || ((scope === 'all' || code === sel)
        && (!ty || $('[data-f=leave_code]', r).value === ty) && (!yr || r.getAttribute('data-year') === yr));
      if (ok && q && !isnew) {
        var hay = (r.getAttribute('data-name') + ' ' + code + ' ' + $('[data-f=notes]', r).value + ' ' + $('[data-f=manager_name]', r).value).toLowerCase();
        ok = hay.indexOf(q) > -1;
      }
      r.hidden = !ok; var e = r.nextElementSibling; if (e && e.classList.contains('errrow')) e.hidden = !ok;
      if (ok && !isnew) { n++; sd += +$('[data-f=days]', r).value || 0; sh += +$('[data-f=hours]', r).value || 0; }
    });
    $('#lvFootLabel').textContent = M.total + ' · ' + n + ' ' + M.rows;
    $('#lvSumDays').textContent = fmt(sd); $('#lvSumHours').textContent = fmt(sh);
    $('#lvGridEmpty').hidden = n > 0 || !!$('tr.isnew', tb);
    $$('#lvScope input').forEach(function (i) { i.checked = i.value === scope; });
  }
  $('#lvScope').addEventListener('change', function (e) {
    scope = e.target.value;
    var u = new URL(location.href); if (scope === 'all') u.searchParams.set('scope', 'all'); else u.searchParams.delete('scope');
    history.replaceState(null, '', u); filter();
  });
  ['input', 'change'].forEach(function (ev) { $('#lvGQ').addEventListener(ev, filter); });
  $('#lvGType').addEventListener('change', filter); $('#lvGYear').addEventListener('change', filter);
  $('#lvGReset').addEventListener('click', function () { $('#lvGQ').value = ''; $('#lvGType').value = ''; $('#lvGYear').value = ''; filter(); });

  /* ───── الترتيب ───── */
  var KEY = {emp: function (r) { return r.getAttribute('data-name'); }, type: function (r) { return $('[data-f=leave_code]', r).value; },
    from: function (r) { return $('[data-f=leave_date]', r).value; }, to: function (r) { return $('[data-f=end_date]', r).value; },
    days: function (r) { return +$('[data-f=days]', r).value || 0; }, hours: function (r) { return +$('[data-f=hours]', r).value || 0; }};
  $$('th[data-sort]', grid).forEach(function (th) {
    th.addEventListener('click', function () {
      var dir = th.getAttribute('data-dir') === 'asc' ? 'desc' : 'asc', k = KEY[th.getAttribute('data-sort')];
      $$('th[data-sort]', grid).forEach(function (x) { x.removeAttribute('data-dir'); }); th.setAttribute('data-dir', dir);
      $$('.errrow', tb).forEach(function (x) { x.remove(); });
      var rows = $$('tr.gr:not(.isnew)', tb);
      rows.sort(function (a, b) { var x = k(a), y = k(b); return (x < y ? -1 : x > y ? 1 : 0) * (dir === 'asc' ? 1 : -1); });
      rows.forEach(function (r) { tb.appendChild(r); });
    });
  });

  /* ───── التعديل ───── */
  tb.addEventListener('input', function (e) {
    var tr = e.target.closest('tr.gr'); if (!tr) return;
    var f = e.target.getAttribute('data-f');
    if (f === 'leave_code' || f === 'leave_date') mode(tr);
    tr.classList.add('dirty'); var s = $('.js-save', tr); if (s) s.hidden = false; dirtyCount();
    if (f === 'days' || f === 'hours') filter();
  });
  tb.addEventListener('keydown', function (e) {
    var tr = e.target.closest('tr.gr'); if (!tr) return;
    if (e.key === 'Enter' && e.target.tagName !== 'SELECT') { e.preventDefault(); saveRow(tr).then(function (ok) { if (ok) done('saved'); }); return; }
    if (e.ctrlKey && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault();
      var vis = $$('tr.gr', tb).filter(function (r) { return !r.hidden; }), i = vis.indexOf(tr) + (e.key === 'ArrowDown' ? 1 : -1);
      if (vis[i]) { var t = $('[data-f=' + e.target.getAttribute('data-f') + ']', vis[i]); if (t) t.focus(); }
    }
  });
  tb.addEventListener('click', function (e) {
    var tr = e.target.closest('tr.gr'); if (!tr) return;
    if (e.target.closest('.js-save')) saveRow(tr).then(function (ok) { if (ok) done('saved'); });
    else if (e.target.closest('.js-cancel')) { clearErr(tr); tr.remove(); dirtyCount(); filter(); }
    else if (e.target.closest('.js-del')) {
      if (!confirm(M.del)) return;
      var fd = new FormData(); fd.append('code', sel);
      fetch(DEL.replace(/0\/delete$/, tr.getAttribute('data-id') + '/delete'), {method: 'POST', body: fd})
        .then(function () { done('deleted'); }).catch(function () { showErr(tr, M.net); });
    }
  });
  $('#lvAddRow').addEventListener('click', function () {
    var row = $('#lvNewRow').content.firstElementChild.cloneNode(true);
    $('[data-f=employee]', row).value = SEL_LABEL;
    tb.insertBefore(row, tb.firstChild); mode(row); dirtyCount(); filter();
    grid.parentNode.scrollTop = 0; $('[data-f=leave_code]', row).focus();
  });
  $('#lvSaveAll').addEventListener('click', function () {
    var rows = $$('tr.dirty', tb), i = 0;
    (function next() { if (i >= rows.length) return done('saved'); saveRow(rows[i++]).then(function (ok) { if (ok) next(); }); })();
  });

  /* ───── تصدير CSV ───── */
  $('#lvExport').addEventListener('click', function () {
    var out = [['code', 'name', 'type', 'from', 'to', 'days', 'hours', 'manager', 'approved', 'notes']];
    $$('tr.gr:not(.isnew)', tb).filter(function (r) { return !r.hidden; }).forEach(function (r) {
      var v = function (f) { return $('[data-f=' + f + ']', r); };
      out.push([r.getAttribute('data-code'), $('.emp b', r).textContent, v('leave_code').value, v('leave_date').value, v('end_date').value,
                v('days').value, v('hours').value, v('manager_name').value, v('manager_approved').checked ? 1 : 0, v('notes').value]);
    });
    var csv = '﻿' + out.map(function (r) { return r.map(function (c) { return '"' + String(c).replace(/"/g, '""') + '"'; }).join(','); }).join('\r\n');
    var a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
    a.download = 'leave_register.csv'; document.body.appendChild(a); a.click(); a.remove();
  });

  $$('tr.gr', tb).forEach(mode); filter();
})();
</script>
{% endif %}

{# ───────── أرصدة الفريق ───────── #}
<section class="lv-card lv-sec">
  <div class="lv-card-h">
    <div><h2>{{ ico('users') }}{{ t('leave_team_balances') }}</h2><p>{{ t('leave_team_hint') }}</p></div>
    <div class="lv-tools">
      <div class="lv-pills" id="lvPills">
        <button type="button" class="lv-pill on" data-f="all">{{ t('all') }}</button>
        <button type="button" class="lv-pill" data-f="low">{{ tx('Low balance (≤ 3)', 'رصيد منخفض (≤ 3)') }}</button>
        <button type="button" class="lv-pill" data-f="locked">{{ t('leave_locked') }}</button>
      </div>
      <div class="lv-field" style="min-width:220px">{{ ico('search') }}<input id="lvQ" placeholder="{{ t('search') }}"></div>
    </div>
  </div>
  <div class="lv-card-b"><div class="lv-dtw">
    <table id="lvTeam" class="lv-dt">
      <thead><tr>
        <th data-sort="s">{{ t('employee') }}</th><th data-sort="s">{{ t('department') }}</th><th data-sort="n">{{ t('leave_total_balance') }}</th>
        <th data-sort="n">{{ t('leave_casual_balance') }}</th><th data-sort="n">{{ t('leave_annual_balance') }}</th>
        <th data-sort="n">{{ t('leave_sick_remaining') }}</th><th data-sort="n">{{ t('leave_permissions_remaining') }}</th>
      </tr></thead>
      <tbody>
      {% for s in summaries %}
        {% set sb = s.balance %}
        {% set low = sb.available and sb.total_balance <= 3 %}
        {% set ent2 = sb.entitlement_total or 0 %}
        <tr class="pick {{ 'sel' if s.employee.code == selected_code }}" data-href="{{ url_for('leaves', code=s.employee.code) }}"
            data-state="{{ 'locked' if not sb.available else ('low' if low else 'ok') }}"
            data-q="{{ (s.employee.code ~ ' ' ~ (s.employee.name or '') ~ ' ' ~ (s.employee.department or ''))|lower|e }}">
          <td data-v="{{ (s.employee.name or '')|lower }}"><b>{{ s.employee.name }}</b><div class="dim" style="font-size:12px">{{ s.employee.code }}{% if s.employee.job %} · {{ s.employee.job }}{% endif %}</div></td>
          <td data-v="{{ (s.employee.department or '')|lower }}">{{ s.employee.department or '—' }}</td>
          <td class="num" data-v="{{ sb.total_balance if sb.available else -1 }}">
            {% if not sb.available %}<span class="lv-lock" style="margin:0">{{ ico('lock') }}{{ t('leave_locked') }}</span>
            {% else %}<span class="lv-badge" style="--bb:{{ '#fdecea' if low else '#e8f5e9' }};--bc:{{ '#c62828' if low else '#2e7d32' }}">{{ sb.total_balance|gnum }} {{ t('days') }}</span>
              <div class="lv-mini" style="--w:{{ ((sb.total_balance / ent2 * 100) if ent2 else 0)|int }}%;--c:{{ '#c62828' if low else '#2e7d32' }}"><i></i></div>{% endif %}
          </td>
          <td class="num" data-v="{{ sb.casual_balance }}">{{ sb.casual_balance|gnum }}</td>
          <td class="num" data-v="{{ sb.annual_balance }}">{{ sb.annual_balance|gnum }}</td>
          <td class="num" data-v="{{ sb.sick_remaining_3y }}">{{ sb.sick_remaining_3y|gnum }}</td>
          <td class="num" data-v="{{ sb.permissions_remaining }}">{{ sb.permissions_remaining }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table></div>
    <div class="lv-empty" id="lvNone" hidden>{{ t('no_results') }}</div>
  </div>
</section>

{# ───────── دليل الأكواد والقواعد ───────── #}
<section class="lv-card lv-sec">
  <div class="lv-card-h"><div><h2>{{ ico('info') }}{{ t('leave_code_legend') }}</h2><p>{{ t('leave_code_hint') }}</p></div></div>
  <div class="lv-card-b">
    <div class="lv-legend">
      {% for c in leave_labels %}<div><span class="lv-badge code lv-tag-{{ c }}">{{ c }}</span><span>{{ t('leave_type_' ~ c) }}</span></div>{% endfor %}
    </div>
    <div class="lv-rules">{{ t('leave_rules_note') }}</div>
  </div>
</section>

<script>
(function () {
  var $ = function (s) { return document.querySelector(s); };
  var codes = {{ emp_codes|tojson }};
  var cur = {{ selected_code|tojson }};
  var go = function (c) { if (c && c !== cur) location.href = {{ url_for('leaves')|tojson }} + '?code=' + encodeURIComponent(c); };

  // اختيار الموظف
  var emp = $('#lvEmp');
  if (emp) {
    emp.addEventListener('focus', function () { this.select(); });
    emp.addEventListener('change', function () {
      var c = this.value.split(' — ')[0].trim();
      if (codes.indexOf(c) > -1) go(c);
    });
    var step = function (d) { var i = codes.indexOf(cur); if (i > -1) go(codes[(i + d + codes.length) % codes.length]); };
    $('#lvPrev').onclick = function () { step(-1); };
    $('#lvNext').onclick = function () { step(1); };
  }

  // الفورم
  var type = $('#lvType');
  if (type) {
    var B = {{ (b or {})|tojson }};
    var REST = {{ rest|tojson }};
    var M = {
      avail: {{ tx('Available', 'المتاح')|tojson }}, days: {{ t('days')|tojson }},
      over: {{ tx('Exceeds balance — manager approval is required to convert the excess to annual leave.', 'أكبر من الرصيد — لازم اعتماد المدير لتحويل الزيادة لاعتيادي.')|tojson }},
      none: {{ tx('Not enough balance.', 'الرصيد غير كافٍ.')|tojson }},
      locked: {{ t('leave_locked')|tojson }},
      permHelp: {{ tx('Permission: up to 2 hours, one day only.', 'الإذن: حتى ساعتين وفي يوم واحد فقط.')|tojson }},
      missHelp: {{ tx('Mission: enter days, or hours for a partial day.', 'المأمورية: اكتبي أيام، أو ساعات لو جزء من اليوم.')|tojson }},
      daysHelp: {{ tx('Days are counted automatically excluding weekly rest days — you can edit them.', 'الأيام بتتحسب تلقائيًا بدون أيام الراحة — وتقدري تعدّليها.')|tojson }},
      sickHelp: {{ tx('Paid sick leave is capped at 90 days in 3 years.', 'المرضي بأجر بحد 90 يومًا خلال 3 سنوات.')|tojson }}
    };
    var from = $('#lvFrom'), to = $('#lvTo'), days = $('#lvDays'), hours = $('#lvHours');
    var avail = $('#lvAvail'), help = $('#lvHelp'), appr = $('#lvAppr');
    var dirty = false;
    days.addEventListener('input', function () { dirty = true; update(); });

    function workdays(a, z) {
      var d = new Date(a + 'T00:00:00'), e = new Date(z + 'T00:00:00'), n = 0;
      if (isNaN(d) || isNaN(e) || e < d) return 0;
      for (; d <= e; d.setDate(d.getDate() + 1)) { if (REST.indexOf((d.getDay() + 6) % 7) < 0) n++; }
      return n;
    }
    function mode() { return type.options[type.selectedIndex].getAttribute('data-mode'); }
    function update() {
      var c = type.value, m = mode();
      $('#lvHoursBox').hidden = m === 'days';
      $('#lvDaysBox').hidden = m === 'hours';
      if (m === 'hours') { to.value = from.value; to.readOnly = true; days.value = 0; if (+hours.value === 0) hours.value = 1; }
      else {
        to.readOnly = false;
        if (to.value < from.value) to.value = from.value;
        if (m === 'days') hours.value = 0;
        if (!dirty && m !== 'hours') days.value = workdays(from.value, to.value) || 1;
      }
      // الرصيد المتاح للنوع
      var left = null, label = '', cls = '';
      if (c === 'A') { left = B.annual_balance; }
      else if (c === 'C') { left = B.casual_balance; }
      else if (c === 'S') { left = B.sick_remaining_3y; }
      else if (c === 'PERM') { left = B.permissions_remaining; }
      if (left !== null) {
        var need = c === 'PERM' ? 1 : (+days.value || 0);
        label = M.avail + ': ' + (+left.toFixed(2)) + (c === 'PERM' ? '' : ' ' + M.days);
        if ((c === 'A' || c === 'C') && !B.available) { label += ' — ' + M.locked; cls = 'bad'; }
        else if (need > left) { cls = 'warn'; label += ' — ' + (c === 'C' ? M.over : (c === 'S' ? M.sickHelp : M.none)); if (c === 'C') appr.open = true; }
        avail.textContent = label; avail.className = 'lv-avail ' + cls; avail.hidden = false;
      } else { avail.hidden = true; }
      help.textContent = c === 'PERM' ? M.permHelp : (c === 'M' ? M.missHelp : (c === 'S' ? M.sickHelp : M.daysHelp));
    }
    type.addEventListener('change', function () { dirty = false; update(); });
    from.addEventListener('change', function () { dirty = false; update(); });
    to.addEventListener('change', function () { dirty = false; update(); });
    hours.addEventListener('input', update);
    update();
  }

  // أرصدة الفريق: بحث وفلاتر وفتح الموظف
  var rows = Array.prototype.slice.call(document.querySelectorAll('#lvTeam tbody tr'));
  var q = $('#lvQ'), f = 'all';
  function filt() {
    var s = (q.value || '').trim().toLowerCase(), n = 0;
    rows.forEach(function (r) {
      var ok = (!s || r.getAttribute('data-q').indexOf(s) > -1) && (f === 'all' || r.getAttribute('data-state') === f);
      r.hidden = !ok; if (ok) n++;
    });
    $('#lvNone').hidden = n > 0;
  }
  if (q) q.addEventListener('input', filt);
  document.querySelectorAll('#lvPills .lv-pill').forEach(function (p) {
    p.addEventListener('click', function () {
      document.querySelectorAll('#lvPills .lv-pill').forEach(function (x) { x.classList.remove('on'); });
      p.classList.add('on'); f = p.getAttribute('data-f'); filt();
    });
  });
  rows.forEach(function (r) { r.addEventListener('click', function () { location.href = r.getAttribute('data-href'); }); });

  // ترتيب جدول أرصدة الفريق
  var tt = document.getElementById('lvTeam');
  if (tt) Array.prototype.forEach.call(tt.querySelectorAll('th[data-sort]'), function (th, ci) {
    th.addEventListener('click', function () {
      var dir = th.getAttribute('data-dir') === 'asc' ? 'desc' : 'asc', num = th.getAttribute('data-sort') === 'n';
      Array.prototype.forEach.call(tt.querySelectorAll('th'), function (x) { x.removeAttribute('data-dir'); });
      th.setAttribute('data-dir', dir);
      var tbody = tt.tBodies[0], rs = Array.prototype.slice.call(tbody.rows);
      var val = function (r) { var v = r.cells[ci].getAttribute('data-v'); return num ? parseFloat(v) : v; };
      rs.sort(function (a, b) { var x = val(a), y = val(b); return (x < y ? -1 : x > y ? 1 : 0) * (dir === 'asc' ? 1 : -1); });
      rs.forEach(function (r) { tbody.appendChild(r); });
    });
  });

  var toast = $('#lvToast');
  if (toast) setTimeout(function () { toast.style.transition = 'opacity .5s'; toast.style.opacity = 0; }, 4500);
})();
</script>
{% endif %}
</div>
{% endblock %}