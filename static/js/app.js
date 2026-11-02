// عدّاد متحرك للأرقام
document.querySelectorAll('[data-count]').forEach(el => {
  const end = parseFloat(el.dataset.count), dec = parseInt(el.dataset.dec || '0', 10);
  if (isNaN(end)) return;
  const t0 = performance.now(), dur = 700;
  const tick = now => {
    const p = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    el.textContent = (end * e).toLocaleString('en-US', {minimumFractionDigits: dec, maximumFractionDigits: dec});
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
});
// فلترة فورية لقائمة الهيكل التنظيمي
const oq = document.getElementById('orgq');
if (oq) oq.addEventListener('input', () => {
  const v = oq.value.trim().toLowerCase();
  document.querySelectorAll('.orgitem').forEach(i => i.classList.toggle('hide', !i.dataset.s.toLowerCase().includes(v)));
});

// تحسين اختياري: إغلاق القوائم المفتوحة عند الضغط بره أو Esc (الفتح والقفل نفسهم شغالين بدون JS)
(() => {
  const all = () => document.querySelectorAll('details.alert-wrap[open], details.dd[open]');
  document.addEventListener('click', e => all().forEach(d => { if (!d.contains(e.target)) d.removeAttribute('open'); }));
  document.addEventListener('keydown', e => { if (e.key === 'Escape') all().forEach(d => d.removeAttribute('open')); });
  document.querySelectorAll('details.alert-wrap, details.dd').forEach(d =>
    d.addEventListener('toggle', () => { if (d.open) all().forEach(o => { if (o !== d) o.removeAttribute('open'); }); }));
})();

// زر إغلاق بوب أب التنبيهات
document.querySelectorAll('[data-close-alerts]').forEach(b => b.addEventListener('click', e => {
  e.preventDefault(); b.closest('details')?.removeAttribute('open');
}));

// إشعار التنبيهات العائم: يظهر كل ساعتين (حتى لو انتقلتي بين الصفحات)، ويختفي بعد دقيقة (يتوقف العدّ لو الماوس عليه)
(() => {
  const el = document.getElementById('alertToast');
  if (!el) return;
  const SHOW_MS = 60 * 1000, EVERY_MS = 2 * 60 * 60 * 1000, KEY = 'hrAlertToastLast';
  let mem = 0;
  const lastShown = () => { try { return Math.max(mem, +localStorage.getItem(KEY) || 0); } catch (e) { return mem; } };
  const mark = () => { mem = Date.now(); try { localStorage.setItem(KEY, String(mem)); } catch (e) { /* التخزين غير متاح */ } };
  let hideT = null, left = SHOW_MS, started = 0;
  el.style.setProperty('--dur', SHOW_MS / 1000 + 's');
  const hide = () => { clearTimeout(hideT); el.classList.remove('show'); setTimeout(() => { if (!el.classList.contains('show')) el.hidden = true; }, 450); };
  const arm = ms => { clearTimeout(hideT); started = Date.now(); left = ms; hideT = setTimeout(hide, ms); };
  const show = () => {
    el.hidden = false; void el.offsetWidth;
    const bar = el.querySelector('.at-bar'); bar.style.animation = 'none'; void bar.offsetWidth; bar.style.animation = '';
    el.classList.add('show'); arm(SHOW_MS); mark();
  };
  el.addEventListener('mouseenter', () => { clearTimeout(hideT); left -= Date.now() - started; });
  el.addEventListener('mouseleave', () => { if (el.classList.contains('show')) arm(Math.max(left, 3000)); });
  el.querySelector('[data-close-toast]').addEventListener('click', hide);
  // أول ظهور: لو عدّت ساعتين من آخر مرة (أو أول مرة) يظهر فورًا، وإلا يستنى باقي المدة
  const schedule = () => {
    const last = lastShown(), wait = last ? Math.max(600, EVERY_MS - (Date.now() - last)) : 600;
    setTimeout(() => { if (document.hidden) { setTimeout(schedule, 30000); return; } show(); schedule(); }, wait);
  };
  schedule();
})();
