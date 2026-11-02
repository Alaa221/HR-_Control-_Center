// بانل سحب البصمات من الأجهزة (بيتحدّث كل 4 ثواني)
(() => {
  const $ = id => document.getElementById(id), C = window.SYNC; if (!C || !$('sync')) return;
  const S = C.s, esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let open = false;
  const post = u => fetch(u, { method: 'POST' }).then(() => poll());
  $('syRun').onclick = () => post(C.run); $('syTog').onclick = () => post(C.tog);
  $('syShow').onclick = () => { open = !open; $('syList').hidden = !open; };
  async function poll() {
    try {
      const d = await (await fetch(C.api)).json();
      $('sync').hidden = !d.available; if (!d.available) return;
      $('syOk').textContent = `${d.ok} ${S.ok}`; $('syErr').textContent = `${d.err} ${S.err}`;
      $('syErr').hidden = !d.err;
      $('syInfo').textContent = !d.enabled ? S.off : d.running ? S.busy
        : `${d.new ? d.new + ' ' + S.new + ' · ' : ''}${d.last_sweep ? S.last + ' ' + d.last_sweep.slice(11) : ''}${d.next_in != null ? ' · ' + S.next + ' ' + d.next_in + 's' : ''}`;
      $('syTog').querySelector('span').textContent = d.enabled ? S.stop : S.start;
      $('syRun').disabled = d.running;
      const warn = d.no_code ? `<div class="sy-warn">لم يتم العثور على عمود <b>New Code</b> في جدول Machines — الأعمدة الموجودة: ${esc((d.cols || []).join(' ، '))}</div>` : '';
      $('syList').innerHTML = warn + d.machines.map(m => `
        <div class="sy-m ${m.state}${m.busy ? ' busy' : ''}" title="${esc(m.error || '')}">
          <i></i><b>${esc(m.name)}${m.alias && m.alias.toLowerCase() !== String(m.name).toLowerCase() ? `<span class="sy-alias" title="${esc(m.alias)}">${esc(m.alias)}</span>` : ''}</b><small>${esc(m.ip)}</small>
          <span>${m.busy ? '…' : m.state === 'ok' ? (m.new ? '+' + m.new : '✓') : m.state === 'err' ? esc((m.error || '').slice(0, 48)) : m.state === 'busy' ? '…' : ''}</span>
          <em>${m.last_ok ? m.last_ok.slice(11) : S.never}</em>
        </div>`).join('');
    } catch (e) { /* الخادم مش متاح مؤقتًا */ }
  }
  poll(); setInterval(poll, 4000);
})();
