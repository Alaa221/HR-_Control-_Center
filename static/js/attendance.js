// صفحة الحضور اللحظي: تسحب من /api/attendance كل N ثانية وتعرض النتايج بدون ريفريش للصفحة.
(() => {
  const $ = id => document.getElementById(id);
  const root = $('att'); if (!root) return;
  const A = window.ATT, S = A.s, REFRESH = Math.max(5, parseInt(root.dataset.refresh || '15', 10));
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = (t, o) => t.replace(/\{(\w+)\}/g, (_, k) => o[k]);
  const num = n => Number(n).toLocaleString('en-US');
  const iso = d => { const z = n => String(n).padStart(2, '0'); return `${d.getFullYear()}-${z(d.getMonth()+1)}-${z(d.getDate())}`; };
  const shift = n => { const d = new Date(); d.setDate(d.getDate() - n); return iso(d); };

  // ── الحالة (بتتقرا من الـ URL وبتتكتب فيه) ──
  const P = new URLSearchParams(location.search);
  const st = { q: P.get('q') || '', machine: P.get('machine') || '', dept: P.get('dept') || '',
               manager: P.get('manager') || '', job: P.get('job') || '',
               location: P.get('location') || '',
               start: P.get('start') || shift(0), end: P.get('end') || shift(0), page: 1 };
  let paused = false, left = REFRESH, timer = null, busy = false, seen = null, last = null, offline = false;

  const params = (extra = {}) => { const p = new URLSearchParams();
    Object.entries({ ...st, ...extra }).forEach(([k, v]) => { if (v) p.set(k, v); }); return p; };
  const syncUrl = () => { const p = params({ page: st.page > 1 ? st.page : '' });
    if (st.start === shift(0) && st.end === shift(0)) { p.delete('start'); p.delete('end'); }
    history.replaceState(null, '', location.pathname + (p.toString() ? '?' + p : '')); };

  // ── ربط الفلاتر ──
  const bind = () => {
    $('fq').value = st.q; $('fDept').value = st.dept; $('fJob').value = st.job;
    $('fManager').value = st.manager;
    $('fLocation').value = st.location;
    $('fStart').value = st.start; $('fEnd').value = st.end;
    const diff = (new Date(st.end) - new Date(st.start)) / 864e5;
    document.querySelectorAll('#chips button').forEach(b => {
      const r = +b.dataset.r;
      b.classList.toggle('on', (r === 0 && st.start === shift(0) && st.end === shift(0)) ||
        (r === 1 && st.start === shift(1) && st.end === shift(1)) || (r === 7 && st.end === shift(0) && Math.round(diff) === 6));
    });
  };
  let deb; const changed = (immediate) => { st.page = 1; seen = null; bind(); clearTimeout(deb); deb = setTimeout(load, immediate ? 0 : 300); };
  // البحث بكود/اسم الموظف: لو الفترة "النهارده" بس بنوسّعها لآخر 30 يوم تلقائيًا، وترجع النهارده لما البحث يتمسح
  let autoWide = false;
  $('fq').addEventListener('input', e => {
    st.q = e.target.value.trim();
    if (st.q && st.start === shift(0) && st.end === shift(0)) { st.start = shift(30); autoWide = true; }
    else if (!st.q && autoWide) { st.start = shift(0); autoWide = false; }
    changed();
  });
  $('fMachine').addEventListener('change', e => { st.machine = e.target.value; changed(true); });
  $('fManager').addEventListener('change', e => { st.manager = e.target.value; changed(true); });
  $('fLocation').addEventListener('change', e => { st.location = e.target.value; changed(true); });
  const dl = (id, key, listId) => $(id).addEventListener('input', e => {
    const v = e.target.value.trim(), ok = [...document.querySelectorAll(`#${listId} option`)].some(o => o.value === v);
    if (ok || v === '') { st[key] = v; changed(true); }
  });
  dl('fDept', 'dept', 'dl-dept'); dl('fJob', 'job', 'dl-job');
  $('fStart').addEventListener('change', e => { autoWide = false; st.start = e.target.value || shift(0); if (st.end < st.start) st.end = st.start; changed(true); });
  $('fEnd').addEventListener('change', e => { autoWide = false; st.end = e.target.value || shift(0); if (st.end < st.start) st.start = st.end; changed(true); });
  $('chips').addEventListener('click', e => { autoWide = false; const b = e.target.closest('button'); if (!b) return; const r = +b.dataset.r;
    st.end = r === 1 ? shift(1) : shift(0); st.start = r === 7 ? shift(6) : st.end; changed(true); });
  $('btnClear').addEventListener('click', () => { Object.assign(st, { q: '', machine: '', dept: '', manager: '', job: '', location: '', start: shift(0), end: shift(0) }); $('fMachine').value = ''; changed(true); });
  $('btnNow').addEventListener('click', () => load());
  $('btnRetry').addEventListener('click', () => load());
  $('btnPause').addEventListener('click', () => { paused = !paused; setPause(); if (!paused) load(); });
  const setPause = () => {
    $('btnPause').querySelector('span').textContent = paused ? S.resume : S.pause;
    $('btnPause').classList.toggle('on', paused); setLive();
  };
  const setLive = () => {
    const p = $('livePill'); p.classList.toggle('off', offline); p.classList.toggle('paused', paused && !offline);
    $('liveTxt').textContent = offline ? S.offline : paused ? S.paused : S.live;
  };

  // ── عرض ──
  const ago = (t, now) => { const s = Math.max(0, Math.round((new Date(now.replace(' ', 'T')) - new Date(t.replace(' ', 'T'))) / 1000));
    if (s < 60) return fmt(S.ago_s, { n: s }); if (s < 3600) return fmt(S.ago_m, { n: Math.floor(s / 60) });
    if (s < 86400) return fmt(S.ago_h, { n: Math.floor(s / 3600) }); return ''; };
  const hhmm = t => t.slice(11, 19), dstr = t => t.slice(0, 10);

  const renderMachineFilter = d => {
    const sel = $('fMachine'), cur = st.machine;
    const names = [...new Set([...(d.all_machines || []), ...d.machines.map(m => m.name)])].sort();
    sel.innerHTML = `<option value="">${esc(S.all_m)}</option>` + names.map(n => `<option ${n === cur ? 'selected' : ''}>${esc(n)}</option>`).join('');
  };

  const render = d => {
    offline = false; setLive();
    $('attErr').hidden = true; $('attMain').hidden = false;
    $('demoPill').hidden = d.source !== 'demo';
    $('updTxt').textContent = hhmm(d.now);
    $('btnCsv').href = A.csv + '?' + params();
    const k = d.kpi;
    renderMachineFilter(d);
    $('cntTxt').textContent = fmt(S.rows, { n: num(d.total) }) + (k.unmatched ? `  ·  ${num(k.unmatched)} ${S.unmatched}` : '');

    const key = r => `${r.code}|${r.t}|${r.machine}`;
    const fresh = new Set();
    if (seen && st.page === 1) d.rows.forEach(r => { if (!seen.has(key(r))) fresh.add(key(r)); });
    if (st.page === 1) seen = new Set(d.rows.map(key));
    const multi = d.start !== d.end, today = d.now.slice(0, 10);
    $('tb').innerHTML = d.rows.length ? d.rows.map(r => {
      const tag = r.dir === 'in' ? `<span class="dir in"><svg class="ico" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>${S.in}</span>`
        : r.dir === 'out' ? `<span class="dir out"><svg class="ico" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>${S.out}</span>` : '<span class="muted">—</span>';
      const a = dstr(r.t) === today ? ago(r.t, d.now) : '';
      const nm = r.known ? `<a class="lnk" href="${A.emp.replace('__C__', encodeURIComponent(r.hr))}">${esc(r.name)}</a>` : `<span class="muted">${esc(r.name)}</span>`;
      return `<tr class="${fresh.has(key(r)) ? 'fresh' : ''}">
        <td class="tcell"><b>${hhmm(r.t)}</b><small>${multi || dstr(r.t) !== today ? dstr(r.t) : (a || '')}</small></td>
        <td><span class="mono">${esc(r.code)}</span></td><td>${nm}</td>
        <td class="muted">${esc(r.job)}</td><td>${esc(r.dept)}</td>
        <td><span class="mtag">${esc(r.machine)}</span></td><td>${tag}</td></tr>`;
    }).join('') : `<tr><td colspan="7" class="empty">${esc(S.none)}</td></tr>`;

    if (fresh.size) { const b = $('newBadge'); b.textContent = fmt(S.n_new, { n: fresh.size }); b.hidden = false; clearTimeout(b._t); b._t = setTimeout(() => b.hidden = true, 6000); }
    $('pager').innerHTML = d.pages > 1 ? `
      <button class="btn" data-p="${d.page - 1}" ${d.page <= 1 ? 'disabled' : ''}>${esc(S.prev)}</button>
      <span class="muted">${fmt(S.page, { a: d.page, b: d.pages })}</span>
      <button class="btn" data-p="${d.page + 1}" ${d.page >= d.pages ? 'disabled' : ''}>${esc(S.nextp)}</button>` : '';
  };

  $('pager').addEventListener('click', e => { const b = e.target.closest('button[data-p]'); if (!b || b.disabled) return; st.page = +b.dataset.p; seen = null; load(); });
  // ── تحميل ──
  async function load() {
    if (busy) return; busy = true; left = REFRESH; root.classList.add('loading');
    try {
      const r = await fetch(A.api + '?' + params({ page: st.page }), { headers: { Accept: 'application/json' } });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || 'error');
      last = d; render(d); syncUrl();
    } catch (e) {
      offline = true; setLive(); $('attErrMsg').textContent = e.message; $('attErr').hidden = false; $('attMain').hidden = last == null;
    } finally { busy = false; root.classList.remove('loading'); }
  }

  // ── مؤقّت التحديث التلقائي ──
  const tick = () => {
    if (!paused && !document.hidden) { left -= 1; if (left <= 0) load(); }
    $('cdTxt').textContent = paused ? '' : `${S.next}: ${Math.max(left, 0)}s`;
  };
  setInterval(tick, 1000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !paused && left < REFRESH - 3) load(); });

  bind(); setPause(); load();
})();
