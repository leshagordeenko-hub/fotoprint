/* ООО «Фотопринт» · Управленческая платформа (трек 1). Фронтенд без сборки и внешних библиотек. */
'use strict';

/* ================================================================ helpers */
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const nf = (v, d = 0) => v == null || isNaN(v) ? '—' : new Intl.NumberFormat('ru-RU', { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);
const short = v => { const a = Math.abs(v); if (a >= 1e6) return nf(v / 1e6, 2) + ' млн'; if (a >= 1e4) return nf(v / 1e3, 1) + ' тыс.'; return nf(v, a < 100 && v % 1 ? 2 : 0); };
const axis = v => { const a = Math.abs(v); if (a >= 1e6) return nf(v / 1e6, 1) + ' млн'; if (a >= 1e3) return nf(v / 1e3, a >= 1e4 ? 0 : 1) + ' тыс'; return nf(v); };
const TZ = 'Europe/Minsk';
const fmtDT = s => s ? new Date(s).toLocaleString('ru-RU', { timeZone: TZ, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
const fmtT = s => s ? new Date(s).toLocaleString('ru-RU', { timeZone: TZ, day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—';
const fmtD = s => s ? s.slice(0, 10).split('-').reverse().join('.') : '—';
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
const ss = { get(k) { try { return JSON.parse(sessionStorage.getItem(k)) } catch { return null } }, set(k, v) { try { sessionStorage.setItem(k, JSON.stringify(v)) } catch { } }, del(k) { try { sessionStorage.removeItem(k) } catch { } } };
const ls = { get(k) { try { return JSON.parse(localStorage.getItem(k)) } catch { return null } }, set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)) } catch { } }, del(k) { try { localStorage.removeItem(k) } catch { } } };
function longDate(d) { const n = d.getDate(); return `${d.toLocaleDateString('ru-RU', { weekday: 'long', timeZone: TZ }).replace(/^./, c => c.toUpperCase())}, ${n} ${d.toLocaleDateString('ru-RU', { month: 'long', day: 'numeric', timeZone: TZ }).split(' ')[1]} ${d.getFullYear()}`; }

/* единицы и статусы KPI */
function fmtK(k, v, compact) {
  if (v == null) return '—';
  if (k.unit === '%') return nf(v, 1) + ' %';
  if (k.unit === 'BYN') return (compact ? short(v) : nf(v, Math.abs(v) < 1000 ? 2 : 0)) + ' BYN';
  if (k.unit === 'дн.') return nf(v, 1) + ' дн.';
  return (compact ? short(v) : nf(v)) + ' ' + k.unit;
}
function numK(k, v) { if (v == null) return '—'; if (k.unit === '%') return nf(v, 1) + ' %'; if (k.unit === 'дн.') return nf(v, 1); if (k.unit === 'BYN') return short(v); return short(v); }
const devText = k => k.dev == null ? '—' : (k.dev > 0 ? '+' : k.dev < 0 ? '−' : '') + nf(Math.abs(k.dev), 1) + (k.dev_unit === 'п.п.' ? ' п.п.' : ' %');
const STATUS = { ok: 'Норма', warn: 'Внимание', crit: 'Критично' };
const badgeK = k => `<span class="badge ${k.status === 'crit' ? 'neg' : k.status === 'warn' ? 'warn' : ''}" title="Отклонение от плана: ${esc(STATUS[k.status] || '')}">${devText(k)}</span>`;
const stChip = s => `<span class="st ${s === 'ok' ? 'ok' : s === 'warn' ? 'warn' : s === 'crit' ? 'bad' : 'info'}">${STATUS[s] || esc(s)}</span>`;
const st2 = s => { const m = { 'Выполнено': 'ok', 'В работе': 'info', 'Новое': 'warn', 'На проверке': 'info', 'Отменено': 'bad', 'Высокий': 'bad', 'Средний': 'warn', 'Низкий': 'info', 'успех': 'ok', 'отказано': 'bad', 'ошибка': 'bad' }; return `<span class="st ${m[s] || 'info'}">${esc(s)}</span>`; };

/* ================================================================ icons */
const ic = p => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${p}</svg>`;
const I = {
  dash: ic('<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>'),
  report: ic('<rect x="5" y="3" width="14" height="18" rx="2.5"/><path d="M9 8h6M9 12h6M9 16h3"/>'),
  box: ic('<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/>'),
  users: ic('<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.5a6.5 6.5 0 0 1 3.5 5.5"/>'),
  receipt: ic('<rect x="4" y="3" width="16" height="18" rx="2.5"/><path d="M8 8h8M8 12h8M8 16h5"/>'),
  invoice: ic('<circle cx="10" cy="8" r="4"/><path d="M3 21a7 7 0 0 1 10-6.3"/><path d="M19 14.5c-.5-.6-1.2-1-2-1-1.2 0-2 .6-2 1.5 0 2 4 1 4 3 0 .9-.9 1.5-2 1.5-.8 0-1.6-.4-2-1M17 12v1.5M17 19.5V21"/>'),
  gear: ic('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>'),
  edit: ic('<path d="M12 20h8"/><path d="M11 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/><path d="M17.5 3.5a2.1 2.1 0 0 1 3 3L13 14l-4 1 1-4z"/>'),
  help: ic('<path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M12 7.5v4M12 14h.01"/>'),
  search: ic('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>'),
  bell: ic('<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0"/>'),
  chev: ic('<path d="m6 9 6 6 6-6"/>'),
  chevR: ic('<path d="m9 6 6 6-6 6"/>'),
  x: ic('<path d="M18 6 6 18M6 6l12 12"/>'),
  plus: ic('<path d="M12 5v14M5 12h14"/>'),
  download: ic('<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>'),
  menu: ic('<path d="M4 6h16M4 12h16M4 18h16"/>'),
  check: ic('<path d="M20 6 9 17l-5-5"/>'),
  alert: ic('<circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/>'),
  logout: ic('<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>'),
  moon: ic('<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>'),
  sun: ic('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
  file: ic('<rect x="5" y="3" width="14" height="18" rx="2.5"/><path d="M9 8h6M9 12h2M14 12h1M9 16h2M14 16h1"/>'),
  orders: ic('<path d="M20 12V7a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h7"/><path d="M8 10l2 2 4-4"/><path d="M16 17h6M19 14v6"/>'),
  visitor: ic('<circle cx="10" cy="7.5" r="3.5"/><path d="M3.5 20a6.5 6.5 0 0 1 9.5-5.8"/><circle cx="17.5" cy="17.5" r="3"/><path d="m19.7 19.7 1.8 1.8"/>'),
  truck: ic('<path d="M3 6h11v10H3zM14 9h4l3 3v4h-7"/><circle cx="7" cy="17.5" r="1.8"/><circle cx="17" cy="17.5" r="1.8"/>'),
  lamp: ic('<path d="M5 3h14l-2 7H7z"/><path d="M12 10v11M8 21h8M9 6v2M15 6v2"/>'),
  swap: ic('<path d="M8 13.5 4 9.5l4-4M16 10.5l4 4-4 4"/><path d="M4 9.5h11M20 14.5H9"/>'),
  undo: ic('<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-15-6.7L3 13"/>'),
  zap: ic('<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>'),
  trash: ic('<path d="M3 6h18M8 6V4h8v2M6 6l1 14a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-14M10 11v6M14 11v6"/>'),
  lock: ic('<rect x="4" y="10.5" width="16" height="10.5" rx="2.5"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/>'),
  clock: ic('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
  info: ic('<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5h.01"/>'),
  db: ic('<ellipse cx="12" cy="5.5" rx="8" ry="3"/><path d="M4 5.5v13c0 1.7 3.6 3 8 3s8-1.3 8-3v-13M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>'),
  trend: ic('<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>'),
  globe: ic('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>'),
  phone: ic('<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/>'),
  store: ic('<path d="M4 9.5 5.5 4h13L20 9.5M4 9.5v10.5h16V9.5M10 20v-5h4v5"/><path d="M4 9.5c0 1.4 1.2 2.5 2.7 2.5s2.6-1.1 2.6-2.5c0 1.4 1.2 2.5 2.7 2.5s2.7-1.1 2.7-2.5c0 1.4 1.2 2.5 2.6 2.5S20 10.9 20 9.5"/>'),
  case: ic('<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18"/>'),
  cart: ic('<circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/><path d="M2.5 3h3l2.4 11.5a2 2 0 0 0 2 1.5h7.6a2 2 0 0 0 2-1.6L21 7H6.3"/>'),
  book: ic('<path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v17H6.5A2.5 2.5 0 0 0 4 21.5z"/><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'),
  printer: ic('<path d="M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="7"/>'),
  image: ic('<rect x="3" y="3" width="18" height="18" rx="2.5"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/>'),
  shield: ic('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>'),
};
const KICON = { revenue: 'file', gross_margin: 'trend', on_time: 'orders', defect: 'alert', new_customers: 'visitor', active_customers: 'users', sla: 'help', load: 'truck', staffing: 'users', avg_check: 'receipt', conversion: 'globe', repeat: 'undo', lead_time: 'clock', cac: 'invoice', reprint_cost: 'printer', payroll: 'case' };
const CH_ICON = { 'CH-WEB': 'globe', 'CH-APP': 'phone', 'CH-SALON': 'store', 'CH-B2B': 'case', 'CH-MKT': 'cart' };
const SEC_ICON = { 'SEC-PRINT': 'printer', 'SEC-BIND': 'book', 'SEC-WIDE': 'image' };

/* ================================================================ state & API */
const st = { token: ss.get('fp:token'), user: null, meta: null, F: ss.get('fp:filters') || null, alerts: [], pulse: null };
const ui = { chart: null, pcat: null, pcatPin: null, gmode: 'active', gHl: null, kstat: 'all', drill: null, dstatus: 'all', dprio: 'all', ddept: 'all', dq: '', apage: 1, aresult: 'all', auser: 'all', aq: '' };

class ApiError extends Error { constructor(msg, status, fields) { super(msg); this.status = status; this.fields = fields; } }
let netDown = false;
async function api(path, { method = 'GET', body } = {}) {
  let r;
  try {
    r = await fetch('/api' + path, { method, headers: { 'Content-Type': 'application/json', ...(st.token ? { Authorization: 'Bearer ' + st.token } : {}) }, body: body ? JSON.stringify(body) : undefined });
  } catch (e) {
    setNet(true);
    throw new ApiError('Нет связи с сервером. Проверьте подключение и повторите — введённые данные сохранены.', 0);
  }
  if (netDown) setNet(false);
  let data = null;
  try { data = await r.json(); } catch { }
  if (r.status === 401 && path !== '/login') { doLogout(true); throw new ApiError('Сессия завершена. Войдите снова.', 401); }
  if (!r.ok) throw new ApiError((data && data.error) || `Ошибка сервера (${r.status}). Повторите попытку.`, r.status, data && data.fields);
  return data;
}
function setNet(down) {
  netDown = down;
  $('#net').innerHTML = down ? `<div class="banner">${I.alert}<span>Нет связи с сервером. Показаны последние загруженные данные; изменения не потеряны.</span><button class="btn ghost sm" data-action="retry">Повторить</button></div>` : '';
}
const fq = (extra = {}) => new URLSearchParams({ period: st.F.period, dept: st.F.dept, product: st.F.product, ...extra }).toString();

/* ================================================================ shared UI */
function dd(key, value, options, label, cls = '') {
  const cur = options.find(o => o.value === value) || options[0];
  return `<div class="dd ${cls}" data-dd="${key}"><button class="dd-btn" aria-haspopup="listbox" aria-expanded="false" aria-label="${esc(label)}: ${esc(cur.label)}">${esc(cur.label)}<span class="chev">${I.chev}</span></button>
  <ul class="dd-menu" role="listbox" aria-label="${esc(label)}" hidden>${options.map(o => `<li role="option" tabindex="-1" data-value="${esc(o.value)}" aria-selected="${o.value === value}">${esc(o.label)}</li>`).join('')}</ul></div>`;
}
const DD = {};
function toast(msg, type = 'ok') {
  const t = document.createElement('div'); t.className = 'toast' + (type === 'err' ? ' err' : '');
  t.innerHTML = (type === 'err' ? I.alert : I.check) + `<span>${esc(msg)}</span>`;
  $('#toasts').appendChild(t);
  setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 220); }, type === 'err' ? 6000 : 4000);
}
let lastFocus = null, modalGuard = null;
function openModal({ title, body, footer = '', size = '', onMount, bare = false, guard = null }) {
  closeFloating();
  if ($('#modal').hidden) lastFocus = document.activeElement;
  modalGuard = guard;
  const m = $('#modal');
  m.innerHTML = `<div class="scrim" data-action="close-modal"></div><div class="dialog ${size}" role="dialog" aria-modal="true" ${bare ? `aria-label="${esc(title)}"` : 'aria-labelledby="mtitle"'}>
    ${bare ? body : `<div class="dlg-head"><h2 id="mtitle">${title}</h2><button class="icon-btn no-print" data-action="close-modal" aria-label="Закрыть">${I.x}</button></div>
    <div class="dlg-body">${body}</div>${footer ? `<div class="dlg-foot no-print">${footer}</div>` : ''}`}</div>`;
  m.hidden = false; document.body.classList.add('locked');
  onMount && onMount(m);
  const f = m.querySelector('[autofocus]') || m.querySelector('.dlg-body input,.dlg-body select,.dlg-body textarea') || m.querySelector('.dlg-head button') || m.querySelector('button');
  f && f.focus();
}
function closeModal(force) {
  const m = $('#modal'); if (m.hidden) return;
  if (!force && modalGuard && modalGuard()) { if (!confirm('Закрыть карточку? Несохранённые изменения останутся в черновике.')) return; }
  modalGuard = null; m.hidden = true; m.innerHTML = ''; document.body.classList.remove('locked');
  lastFocus && document.contains(lastFocus) && lastFocus.focus();
}
function field({ id, label, type = 'text', value = '', help = '', opts = null, attrs = '' }) {
  const ctl = opts ? `<select class="select" id="${id}" name="${id}" ${attrs}>${opts.map(o => `<option value="${esc(o.value)}" ${o.value === value ? 'selected' : ''}>${esc(o.label)}</option>`).join('')}</select>`
    : type === 'textarea' ? `<textarea class="textarea" id="${id}" name="${id}" ${attrs}>${esc(value)}</textarea>`
      : `<input class="input" id="${id}" name="${id}" type="${type}" value="${esc(value)}" ${attrs}>`;
  return `<div class="field"><label for="${id}">${label}</label>${ctl}${help ? `<span class="help" id="${id}-h">${help}</span>` : ''}<span class="err" id="${id}-e" role="alert" hidden></span></div>`;
}
function setErr(id, msg) {
  const el = document.getElementById(id), e = document.getElementById(id + '-e'); if (!el || !e) return;
  if (msg) { el.setAttribute('aria-invalid', 'true'); el.setAttribute('aria-describedby', id + '-e'); e.textContent = msg; e.hidden = false; }
  else { el.removeAttribute('aria-invalid'); el.removeAttribute('aria-describedby'); e.hidden = true; }
}
function countUp(root) {
  $$('[data-count]', root).forEach(el => {
    const end = +el.dataset.count, fmt = el.dataset.fmt; if (REDUCED || !isFinite(end)) return;
    const t0 = performance.now(), D = 800, txt = el.textContent;
    const f = v => fmt === 'pct' ? nf(v, 1) + ' %' : fmt === 'dec' || fmt === 'th' ? nf(v, 1) : short(v);
    const step = t => { const k = Math.min(1, (t - t0) / D), e = 1 - Math.pow(1 - k, 3); el.textContent = k < 1 ? f(end * e) : txt; if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  });
}
function downloadCSV(name, rows) {
  const csv = '\ufeff' + rows.map(r => r.map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(';')).join('\n');
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })); a.download = name; document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  api('/export', { method: 'POST', body: { object: name, rows: rows.length - 1 } }).catch(() => { });
}

/* ================================================================ универсальный столбчатый график (вид «Customer Habbits») */
const CH = {};
function niceTop(v) { if (v <= 0) return 1; const p = Math.pow(10, Math.floor(Math.log10(v))); for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p; return 10 * p; }
function barChart(id, cfg) { CH[id] = { hide: {}, idx: cfg.idx ?? Math.max(0, cfg.labels.length - 1), ...cfg }; return `<div class="chart" id="${id}">${chartInner(id)}</div>`; }
function chartInner(id) {
  const c = CH[id], n = c.labels.length; if (c.idx >= n) c.idx = n - 1;
  const vals = [...c.a, ...c.b, ...(c.f || []).filter(v => v != null)].filter(v => v != null);
  const top = niceTop(Math.max(1, ...vals) * 1.02);
  return `<div class="yax" aria-hidden="true">${[1, .75, .5, .25, 0].map((t, i) => `<div style="top:${i * 25}%">${axis(t * top)}</div>`).join('')}</div>
   <div class="plot" role="group" aria-label="${esc(c.aria || '')} Стрелки ← → — переход между столбцами." data-top="${top}">
   ${c.labels.map((m, i) => { const fc = c.f && c.f[i] != null; const hb = fc ? Math.max(c.b[i] || 0, c.f[i]) : (c.b[i] || 0);
    return `<button class="grp ${i === c.idx ? 'active' : ''}" data-chart="${id}" data-i="${i}" tabindex="${i === c.idx ? 0 : -1}" aria-label="${esc(m)}: ${esc(c.la)} ${c.fmt(c.a[i])}, ${esc(c.lb)} ${c.fmt(c.b[i])}${fc ? `, ${esc(c.lf)} ${c.fmt(c.f[i])}` : ''}">
      <span class="bar g ${c.hide.a ? 'off' : ''}" style="height:${(c.a[i] || 0) / top * 100}%"></span><span class="bar b ${fc ? 'fc' : ''} ${c.bad && c.bad[i] ? 'bad' : ''} ${c.hide.b ? 'off' : ''}" style="height:${hb / top * 100}%">${fc ? `<i style="height:${hb ? (c.b[i] || 0) / hb * 100 : 0}%"></i>` : ''}</span></button>`; }).join('')}
   <span class="pin"></span><div class="tip" aria-hidden="true"></div></div>
   <div class="xax" aria-hidden="true">${c.labels.map(m => `<div>${esc(m)}</div>`).join('')}</div>`;
}
function placeTip(id) {
  const c = CH[id], el = document.getElementById(id); if (!c || !el) return;
  const plot = $('.plot', el), g = $$('.grp', el)[c.idx], tip = $('.tip', el), pin = $('.pin', el); if (!g) return;
  $$('.grp', el).forEach((b, i) => { b.classList.toggle('active', i === c.idx); b.tabIndex = i === c.idx ? 0 : -1; });
  if (c.hide.a && c.hide.b) { tip.hidden = pin.hidden = true; return; }
  tip.hidden = pin.hidden = false;
  const top = +plot.dataset.top, i = c.idx, fc = c.f && c.f[i] != null;
  const lead = c.hide.a ? 'b' : 'a', v = lead === 'a' ? c.a[i] : Math.max(c.b[i] || 0, fc ? c.f[i] : 0);
  tip.innerHTML = `<div class="tl" style="font-weight:500;color:#b4b5bb;font-size:12.5px">${esc(c.labels[i])}${c.sub ? ' · ' + esc(c.sub[i]) : ''}</div>`
    + (!c.hide.a ? `<div class="tl"><i style="background:var(--soft)"></i><small>${esc(c.la)}</small>${c.fmt(c.a[i])}</div>` : '')
    + (!c.hide.b ? `<div class="tl"><i style="background:${c.bad && c.bad[i] ? 'var(--red)' : 'var(--blue)'}"></i><small>${esc(c.lb)}</small>${c.fmt(c.b[i])}</div>` : '')
    + (fc && !c.hide.b ? `<div class="tl"><i class="hatch"></i><small>${esc(c.lf)}</small>${c.fmt(c.f[i])}</div>` : '');
  const H = plot.clientHeight, y = H - (v || 0) / top * H, bar = g.querySelector(lead === 'a' ? '.g' : '.b');
  const x = g.offsetLeft + bar.offsetLeft + bar.offsetWidth / 2;
  pin.style.left = x + 'px'; pin.style.top = y + 'px';
  const tw = tip.offsetWidth, th = tip.offsetHeight; let left = x + 16, flip = false;
  if (left + tw > plot.clientWidth) { left = x - 16 - tw; flip = true; }
  left = Math.max(0, Math.min(left, plot.clientWidth - tw)); tip.style.left = left + 'px'; tip.style.top = Math.min(H - th, Math.max(-th / 2, y - th - 2)) + 'px'; tip.classList.toggle('flip', flip);
}
const placeAll = () => Object.keys(CH).forEach(placeTip);

/* ================================================================ login */
const TEST_USERS = [['director', 'Директор', 'Видит все показатели, создаёт решения'], ['prod', 'Руководитель производства', 'Закрытые показатели других подразделений скрыты'], ['sales', 'Руководитель продаж и маркетинга', 'Закрытые показатели других подразделений скрыты'], ['analyst', 'Аналитик / администратор', 'Качество данных, журнал; реестр — только чтение']];
function renderLogin(msg) {
  $('#app').hidden = true; const L = $('#login'); L.hidden = false;
  L.innerHTML = `<div class="login-wrap"><div class="login">
    <section class="promo">
      <div><span class="logo-chip"><img src="picpac-logo.png" alt="PicPac" width="58" height="30"><span>Фотопринт</span></span></div>
      <div><h2>Пульс компании<br>в одном окне</h2><p>Финансы, клиенты, производство и персонал — от показателя до причины и решения.</p>
      <ul>${['План, факт и прогноз 16 KPI', 'Детализация до заказа и причины', 'Реестр решений с историей', 'Прогноз мощности на 6 недель'].map(t => `<li>${I.check}${t}</li>`).join('')}</ul></div>
      <small>Демонстрация на синтетических данных · ООО «Фотопринт»</small>
    </section>
    <section class="card">
      <h1 style="font-size:26px">Вход</h1><p class="stl">Управленческая платформа</p>
      <form id="lform" novalidate>
        ${msg ? `<div class="err-box" role="alert">${esc(msg)}</div>` : ''}
        ${field({ id: 'l-login', label: 'Логин', value: ls.get('fp:lastLogin') || '', attrs: 'autocomplete="username" required autocapitalize="none"' })}
        ${field({ id: 'l-pass', label: 'Пароль', type: 'password', attrs: 'autocomplete="current-password" required' })}
        <button class="btn primary" type="submit" id="lbtn">Войти</button>
      </form>
      <p class="note">Тестовые учётные записи (пароль <code>demo2026</code>):</p>
      <div class="roles">${TEST_USERS.map(([l, r, d]) => `<button class="role-btn" type="button" data-fill="${l}"><span><b>${r}</b><small>${d}</small></span><code>${l}</code></button>`).join('')}</div>
    </section></div></div>`;
  $$('[data-fill]', L).forEach(b => b.onclick = () => { $('#l-login').value = b.dataset.fill; $('#l-pass').value = 'demo2026'; $('#lbtn').focus(); });
  $('#lform').onsubmit = async e => {
    e.preventDefault();
    const login = $('#l-login').value.trim(), password = $('#l-pass').value;
    setErr('l-login', login ? '' : 'Введите логин.'); setErr('l-pass', password ? '' : 'Введите пароль.');
    if (!login || !password) return;
    const b = $('#lbtn'); b.disabled = true; b.textContent = 'Вход…';
    try {
      const r = await api('/login', { method: 'POST', body: { login, password } });
      st.token = r.token; ss.set('fp:token', r.token); ls.set('fp:lastLogin', login);
      await boot();
    } catch (err) { renderLogin(err.message); $('#l-login').value = login; $('#l-pass').focus(); }
  };
  ($('#l-login').value ? $('#l-pass') : $('#l-login')).focus();
}
async function doLogout(expired) {
  if (!expired && st.token) { try { await api('/logout', { method: 'POST' }); } catch { } }
  st.token = null; st.user = null; ss.del('fp:token'); closeModal(true);
  renderLogin(expired ? 'Сессия завершена. Войдите снова.' : '');
}

/* ================================================================ shell */
const NAV = [['МЕНЮ', [['pulse', 'Пульс компании', 'dash'], ['sales', 'Продажи', 'users'], ['production', 'Производство', 'box'], ['finance', 'Финансы и люди', 'invoice']]],
['УПРАВЛЕНИЕ', [['decisions', 'Реестр решений', 'report'], ['forecast', 'Прогноз', 'trend']]],
['ИНСТРУМЕНТЫ', [['quality', 'Качество данных', 'db', 'quality'], ['audit', 'Журнал', 'receipt', 'audit'], ['help', 'Справка', 'help']]]];
// доступ к экранам приходит с сервера: директор и аналитик — все, руководитель — только экраны своего подразделения
const canScreen = id => id === 'help' || (st.meta?.permissions.screens || []).includes(id);
const homeRoute = () => canScreen('pulse') ? 'pulse' : (st.meta?.permissions.screens || [])[0] || 'help';
function renderSide() {
  $('#side').innerHTML = `
    <a class="logo" href="#/${homeRoute()}" aria-label="PicPac · Фотопринт — пульс компании"><img src="picpac-logo.png" alt="PicPac" width="62" height="32"><span class="brand-name">Фотопринт</span></a>
    ${NAV.map(([sec, items]) => { const vis = items.filter(it => canScreen(it[0])); return vis.length ? `<div class="sec">${sec}</div><nav class="nav" aria-label="${sec.toLowerCase()}">${vis.map(([id, l, icn]) => `<a href="#/${id}" data-route="${id}">${I[icn]}${l}</a>`).join('')}</nav>` : ''; }).join('')}`;
  markNav();
}
const plural = (n, a, b, c) => { const m = n % 10, h = n % 100; return m === 1 && h !== 11 ? a : m >= 2 && m <= 4 && (h < 12 || h > 14) ? b : c; };
function markNav() { const id = route(); $$('.nav a').forEach(a => { const on = a.dataset.route === id; a.classList.toggle('on', on); on ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current'); }); }
function renderHeader() {
  $('.burger').innerHTML = I.menu; $('#searchBtn').innerHTML = I.search;
  const unread = st.alerts.filter(a => a.unread).length;
  $('#bellBtn').innerHTML = I.bell + (unread ? '<span class="dot"></span>' : '');
  $('#bellBtn').setAttribute('aria-label', `Уведомления${unread ? `: непрочитанных ${unread}` : ''}`);
  $('#uname').textContent = st.user.name; $('#urole').textContent = st.user.title;
  renderFbar();
}
const FILTER_ROUTES = ['pulse', 'sales', 'production', 'finance'];
function renderFbar() {
  const m = st.meta, r = route();
  const upd = `<span class="upd" title="Время сервера, Europe/Minsk (UTC+3)">${I.clock}${longDate(new Date())}</span>`;
  if (!FILTER_ROUTES.includes(r)) { $('#fbar').innerHTML = upd; return; }
  $('#fbar').innerHTML = `
    <span class="f"><span class="lbl">Период</span>${dd('f-period', st.F.period, m.periods.map(p => ({ value: p.key, label: p.label })), 'Период')}</span>
    ${st.user.role === 'head' ? '' : `<span class="f"><span class="lbl">Подразделение</span>${dd('f-dept', st.F.dept, [{ value: 'all', label: 'Все' }, ...m.departments.map(d => ({ value: d.id, label: d.name }))], 'Подразделение')}</span>`}
    <span class="f"><span class="lbl">Продукт</span>${dd('f-product', st.F.product, [{ value: 'all', label: 'Все продукты' }, ...m.products.map(p => ({ value: p.id, label: p.name }))], 'Продукт')}</span>`;
}
DD['f-period'] = v => setFilter('period', v);
DD['f-dept'] = v => setFilter('dept', v);
DD['f-product'] = v => setFilter('product', v);
function setFilter(k, v) { st.F[k] = v; ss.set('fp:filters', st.F); renderFbar(); render(true); }

async function loadAlerts() { try { st.alerts = (await api('/alerts')).items; } catch { st.alerts = []; } renderHeader(); }
function renderNotif() {
  $('#pop-notif').innerHTML = `<header><b>Уведомления</b><button class="linkbtn" data-action="read-all">Отметить прочитанными</button></header>
   <div>${st.alerts.length ? st.alerts.map(n => `<a class="nitem ${n.unread ? 'unread' : ''}" href="${n.href}" data-action="notif-open" data-id="${esc(n.id)}"><span class="nic">${I[n.icon] || I.alert}</span><span><p>${esc(n.text)}</p><small>${{ kpi: 'Показатель', decision: 'Реестр решений', forecast: 'Прогноз', source: 'Источник данных' }[n.kind]}</small></span></a>`).join('') : '<div class="empty">Новых уведомлений нет</div>'}</div>`;
}
function renderProfileMenu() {
  $('#pop-profile').innerHTML = `
   <div style="padding:10px 12px 12px;border-bottom:1px solid var(--line);margin-bottom:6px"><b>${esc(st.user.name)}</b><div class="muted" style="font-size:13px">${esc(st.user.role_name)}${st.user.dept_name ? ' · ' + esc(st.user.dept_name) : ''}</div></div>
   <a class="menu-item" href="#/help" data-action="close-pops">${I.help}Справка и формулы</a>
   <button class="menu-item" data-action="logout">${I.logout}Сменить пользователя</button>`;
}
function closeFloating(except) {
  $$('.dd-menu').forEach(m => { if (m !== except && !m.hidden) { m.hidden = true; m.previousElementSibling.setAttribute('aria-expanded', 'false'); } });
  $$('.pop').forEach(p => { if (p !== except && !p.hidden) { p.hidden = true; const b = $(`[data-pop="${p.id.slice(4)}"]`); b && b.setAttribute('aria-expanded', 'false'); } });
}
function applyTheme() { ls.del('fp:theme'); document.documentElement.setAttribute('data-theme', 'light'); } // тёмная тема убрана — всегда светлая
function openDrawer() { $('#side').classList.add('open'); $('#navScrim').classList.add('open'); $('.burger').setAttribute('aria-expanded', 'true'); setTimeout(() => $('#side a.on, #side a')?.focus(), 50); }
function closeDrawer() { if (!$('#side').classList.contains('open')) return; $('#side').classList.remove('open'); $('#navScrim').classList.remove('open'); $('.burger').setAttribute('aria-expanded', 'false'); }

/* ================================================================ ПУЛЬС КОМПАНИИ — исходная вёрстка дашборда */
async function vPulse() {
  const d = await api('/pulse?' + fq(ui.chart ? { chart: ui.chart } : {}));
  st.pulse = d;
  return `<div class="page">
   <div class="report">
    <div class="left">
      ${d.cards.map((k, i) => statCard(k, i)).join('')}
      <section class="card habits rise" style="--i:4" id="habits" aria-labelledby="habits-t">${habitsInner()}</section>
    </div>
    <div class="right">
      <section class="card pstat rise" style="--i:5" id="pstat" aria-labelledby="pstat-t">${pstatInner()}</section>
      <section class="card growth rise" style="--i:6" id="growth" aria-labelledby="growth-t">${growthInner()}</section>
    </div>
   </div>
   <section class="card panel rise" style="--i:7" id="ktable" aria-labelledby="kt-t">${kpiTableInner()}</section>
  </div>`;
}
function statCard(k, i) {
  if (k.locked) return `<button class="card stat locked rise" style="--i:${i}" data-action="drill" data-k="${k.id}" aria-label="${esc(k.name)}: нет доступа">
     <div class="ic">${I.lock}</div><div class="lbl">${esc(k.name)}</div><div class="row"><div class="num">Нет доступа</div><div class="sub">Закрытый показатель<br>${esc(k.dept_name)}</div></div></button>`;
  const P = st.pulse.period, fcLabel = P.partial ? 'прогноз' : 'пред.', fcV = P.partial ? k.forecast : k.prev;
  const th = k.unit === 'BYN' && Math.abs(k.plan || k.fact || 0) >= 1e4, sc = v => v == null ? '—' : th ? nf(v / 1e3, 1) : numK(k, v);
  const fmt = th ? 'th' : k.unit === '%' ? 'pct' : k.unit === 'дн.' ? 'dec' : 'n';
  return `<button class="card stat ${i === 0 ? 'primary' : ''} rise" style="--i:${i}" data-action="drill" data-k="${k.id}" aria-label="${esc(k.name)}: факт ${fmtK(k, k.fact)}, план ${fmtK(k, k.plan)}, ${STATUS[k.status]}. Открыть детализацию">
     <div class="ic">${I[KICON[k.id]] || I.file}</div>${badgeK(k)}
     <div class="lbl">${esc(k.name)}${k.unit === 'BYN' ? (th ? ', тыс. BYN' : ', BYN') : k.unit === 'чел.' ? ', чел.' : k.unit === 'дн.' ? ', дн.' : ''}</div>
     <div class="row"><div class="num" data-count="${th ? k.fact / 1e3 : k.fact}" data-fmt="${fmt}">${sc(k.fact)}</div><div class="sub">план ${sc(k.plan)}<br>${fcLabel} ${sc(fcV)}</div></div></button>`;
}
const CHART_META = { revenue: ['Оборот: план и факт', 'BYN', 'Оборот'], orders: ['Заказы: план и факт', 'заказов', 'Заказы'], output: ['Выпуск: план и факт', 'изделий', 'Выпуск'] };
function habitsInner() {
  const d = st.pulse, c = d.chart, m = CHART_META[c.metric];
  const b = c.buckets, weekly = d.period.days <= 31;
  const cfg = { labels: b.map(x => x.label), a: b.map(x => x.plan), b: b.map(x => x.fact), f: b.map(x => x.forecast), la: 'План', lb: 'Факт', lf: 'Прогноз',
    sub: b.map(x => `${fmtD(x.start)}–${fmtD(x.end)}`), fmt: v => v == null ? '—' : nf(v, 0) + (c.metric === 'revenue' ? ' BYN' : ''), aria: m[0] + '.',
    idx: Math.max(0, b.findIndex(x => !x.complete)) || b.length - 1 };
  if (b.every(x => x.complete)) cfg.idx = b.length - 1;
  return `<div class="card-head"><div><h2 class="ttl" id="habits-t">${m[0]}</h2><p class="stl">${esc(d.period.label)} · по ${weekly ? 'неделям' : 'месяцам'} · ${m[1]}</p></div>${dd('chart', c.metric, Object.entries(CHART_META).map(([k, v]) => ({ value: k, label: v[2] })), 'Показатель графика')}</div>
  <div class="legend"><button class="lg ${CH.hc?.hide.a ? 'off' : ''}" data-action="legend" data-chart="hc" data-s="a" aria-pressed="true"><i class="dot-seen"></i>План</button><button class="lg" data-action="legend" data-chart="hc" data-s="b" aria-pressed="true"><i class="dot-sales"></i>Факт</button>${b.some(x => x.forecast != null) ? '<span class="lg static"><i class="dot-fc"></i>Прогноз</span>' : ''}</div>
  ${barChart('hc', cfg)}`;
}
DD.chart = v => { ui.chart = v; render(true); };
const RING_R = [122, 100, 78, 56];
const pcatAct = () => { const s = ui.pcatPin != null ? st.pulse.load.sections[ui.pcatPin] : null;
  return s ? `<button class="btn ghost sm pcat-act" data-action="orders-by" data-p="section" data-v="${esc(s.name)}" data-kind="late">Заказы с опозданием · ${esc(s.name)} ${I.chevR}</button>` : ''; };
function pstatInner() {
  const L = st.pulse.load, secs = L.sections;
  const rings = RING_R.map((r, i) => { const C = 2 * Math.PI * r, T = .75 * C, s = secs[i];
    let h = `<g class="ring ${ui.pcat === i ? 'hl' : ''}" ${s ? `data-i="${i}" data-action="pcat"` : ''}><circle cx="130" cy="130" r="${r}" class="trk" stroke-dasharray="${T} ${C}"/>`;
    if (s && s.load != null) { const Lh = Math.max(.001, Math.min(1, s.load / 100) * T); h += `<circle cx="130" cy="130" r="${r}" class="arc ${s.status === 'crit' ? 'neg' : ''}" stroke-dasharray="${Lh} ${C}" stroke-dashoffset="${-(T - Lh)}" style="--C:${C}"><title>${esc(s.name)}: ${nf(s.load, 1)} %</title></circle>`; }
    return h + '</g>'; }).join('');
  return `<div class="card-head"><div><h2 class="ttl" id="pstat-t">Загрузка мощности</h2></div>${dd('pcat', ui.pcat == null ? 'all' : String(ui.pcat), [{ value: 'all', label: 'Все' }, ...secs.map((s, i) => ({ value: String(i), label: s.name }))], 'Участок')}</div>
  <div class="donut-wrap"><svg class="donut ${ui.pcat != null ? 'focus' : ''}" width="260" height="260" viewBox="0 0 260 260" role="img" aria-label="Загрузка участков в процентах от мощности">${rings}</svg>
    <div class="dval" id="dval" aria-live="polite">${dvalInner()}</div></div>
  <ul class="cats">${secs.map((s, i) => `<li><button class="cat ${ui.pcat === i ? 'on' : ''}" data-action="pcat" data-i="${i}" aria-pressed="${ui.pcat === i}">${I[SEC_ICON[s.id]]}<span>${esc(s.name)}</span><span class="v">${nf(s.load, 0)} %</span><span class="badge ${s.status === 'crit' ? 'neg' : s.status === 'warn' ? 'warn' : ''}" title="Изменение к предыдущему периоду">${s.prev == null ? '—' : (s.load - s.prev >= 0 ? '+' : '−') + nf(Math.abs(s.load - s.prev), 1)}</span></button></li>`).join('')}</ul><div id="pcat-act">${pcatAct()}</div>`;
}
function dvalInner() {
  const L = st.pulse.load, s = ui.pcat != null ? L.sections[ui.pcat] : null, v = s ? s.load : L.total, p = s ? s.prev : L.prev;
  const crit = s ? s.status === 'crit' : v > 100;
  return `<b>${nf(v, 1)} %</b><span class="cap">${s ? esc(s.name) : 'Все участки'}</span><span class="badge ${crit ? 'neg' : ''}">${p == null ? '—' : (v - p >= 0 ? '+' : '−') + nf(Math.abs(v - p), 1) + ' п.п.'}</span>`;
}
function setPcat(i) {
  ui.pcat = i; const svg = $('#pstat .donut'); if (!svg) return;
  svg.classList.toggle('focus', i != null); $$('#pstat .ring').forEach(g => g.classList.toggle('hl', g.dataset.i != null && +g.dataset.i === i));
  $$('#pstat .cat').forEach((b, k) => { b.classList.toggle('on', k === i); b.setAttribute('aria-pressed', k === i); });
  $('#dval').innerHTML = dvalInner();
  const act = $('#pcat-act'); if (act) act.innerHTML = pcatAct();
  const dd = $('#pstat [data-dd="pcat"]'); // подпись выпадающего списка следует за закреплённым участком
  if (dd) { const v = ui.pcatPin == null ? 'all' : String(ui.pcatPin); const li = $(`li[data-value="${v}"]`, dd);
    if (li) { $('.dd-btn', dd).firstChild.textContent = li.textContent; $$('li', dd).forEach(x => x.setAttribute('aria-selected', x === li)); } }
}
DD.pcat = v => { ui.pcatPin = v === 'all' ? null : +v; setPcat(ui.pcatPin); };
const SLOTS = [{ x: 30, y: 2, s: 144, c: '#4B56EE', fs: 21, st: 'padding-left:26px;padding-bottom:6px' }, { x: 2, y: 88, s: 106, c: '#5F69F0', fs: 20, b: 1, st: 'padding-right:22px;padding-bottom:4px' }, { x: 74, y: 106, s: 90, c: '#7780F3', fs: 18, b: 1 }, { x: 8, y: 22, s: 62, c: '#8E95F5', fs: 16, b: 1 }];
function growthInner() {
  const key = ui.gmode, all = st.pulse.clients, ranked = [...all].sort((a, b) => b[key] - a[key]).slice(0, 4), max = ranked[0]?.[key] || 1, order = [0, 3, 1, 2];
  return `<div class="card-head"><div><h2 class="ttl" id="growth-t">Клиенты</h2><p class="stl">${key === 'active' ? 'Активные' : 'Новые'} по каналам</p></div>${dd('gmode', key, [{ value: 'active', label: 'Активные' }, { value: 'new', label: 'Новые' }], 'Клиенты')}</div>
  <div class="growth-body">
    <div class="bubbles ${ui.gHl ? 'focus' : ''}" aria-hidden="true">${order.map(si => { const c = ranked[si], s = SLOTS[si]; if (!c) return '';
      return `<div class="bub ${s.b ? 'bord' : ''} ${ui.gHl === c.id ? 'hl' : ''}" data-c="${c.id}" data-action="orders-by" data-p="channel" data-v="${esc(c.name)}" style="left:${s.x}px;top:${s.y}px;width:${s.s}px;height:${s.s}px;background:${s.c};font-size:${s.fs}px;${s.st || ''}" title="${esc(c.name)}: ${nf(c[key])}">${short(c[key])}</div>`; }).join('')}</div>
    <ul class="countries">${ranked.map(c => `<li><button class="cty ${ui.gHl === c.id ? 'hl' : ''}" data-action="orders-by" data-p="channel" data-v="${esc(c.name)}" data-c="${c.id}" aria-label="${esc(c.name)}: ${nf(c[key])} клиентов. Показать заказы канала">
      <span class="flag chi" aria-hidden="true">${I[CH_ICON[c.id]]}</span><span class="nm">${esc(c.name.replace('Сайт picPac.by', 'Сайт picPac'))}<small>${nf(c[key])}</small></span><div class="track"><b style="width:${c[key] / max * 100}%"></b></div></button></li>`).join('')}</ul>
  </div>`;
}
DD.gmode = v => { ui.gmode = v; ui.gHl = null; $('#growth').innerHTML = growthInner(); };
function setGhl(c) { ui.gHl = c; $('#growth .bubbles')?.classList.toggle('focus', !!c); $$('#growth .bub').forEach(b => b.classList.toggle('hl', b.dataset.c === c)); $$('#growth .cty').forEach(b => b.classList.toggle('hl', b.dataset.c === c)); }

function kpiTableInner() {
  const d = st.pulse, ks = d.kpis, cnt = s => ks.filter(k => k.status === s).length;
  const rows = ks.filter(k => ui.kstat === 'all' || k.status === ui.kstat);
  const canDecide = st.meta.permissions.decide;
  return `<div class="card-head" style="margin-bottom:14px"><div><h2 class="ttl" id="kt-t">Ключевые показатели</h2><p class="stl">${esc(d.period.label)}${d.period.partial ? ` · прошло ${d.period.elapsed_days} из ${d.period.days} дн.` : ''}</p></div>
    <button class="btn ghost sm" data-action="kpi-export">${I.download}CSV</button></div>
   <div class="chips" role="group" aria-label="Фильтр по статусу" style="margin-bottom:12px">${[['all', 'Все', ks.length], ['crit', 'Критично', cnt('crit')], ['warn', 'Внимание', cnt('warn')], ['ok', 'Норма', cnt('ok')]].map(([v, l, n]) => `<button class="chip-btn" data-action="kstat" data-v="${v}" aria-pressed="${ui.kstat === v}">${l} · ${n}</button>`).join('')}</div>
   <div class="tbl-wrap"><table><thead><tr><th>Показатель</th><th class="num">План</th><th class="num">Факт</th><th class="num">Прогноз</th><th>Отклонение</th><th>Статус</th><th>Источник · обновлено</th><th><span class="sr">Действия</span></th></tr></thead><tbody>
   ${rows.map(k => k.locked ? `<tr><td><span class="kname"><b>${esc(k.name)}</b><small>${esc(k.dept_name)} · закрытый</small></span></td><td colspan="5"><span class="lock">${I.lock}Нет доступа: закрытый показатель подразделения «${esc(k.dept_name)}»</span></td><td class="small muted">${k.sources.map(s => s.name.split(' ')[0]).join(' · ')}</td><td></td></tr>`
    : `<tr class="${k.status === 'crit' ? 'row-crit' : k.status === 'warn' ? 'row-warn' : ''}"><td><button class="kname" data-action="drill" data-k="${k.id}"><b>${esc(k.name)}</b><small>${esc(k.dept_name)}${k.closed ? ' · закрытый' : ''}${!k.product_scope && st.F.product !== 'all' ? ' · без разреза по продукту' : ''}${k.responsible ? ' · отв.: ' + esc(k.responsible.name) : ''}${k.comments_count ? ` · комментариев: ${k.comments_count}` : ''}</small></button></td>
      <td class="num">${fmtK(k, k.plan)}</td><td class="num"><b>${fmtK(k, k.fact)}</b></td><td class="num">${fmtK(k, k.forecast)}</td><td>${badgeK(k)}</td><td>${stChip(k.status)}</td>
      <td class="small muted">${k.sources.map(s => esc(s.name.split(' (')[0])).join(' · ')}<br>${fmtT(k.updated_at)}</td>
      <td><div class="row-actions"><button class="icon-btn" data-action="kinfo" data-k="${k.id}" aria-label="Формула и источник: ${esc(k.name)}">${I.info}</button>${canDecide && k.status === 'crit' ? `<button class="btn ghost sm" data-action="decide" data-k="${k.id}">${I.plus}Решение</button>` : ''}<button class="icon-btn" data-action="drill" data-k="${k.id}" aria-label="Детализация: ${esc(k.name)}">${I.chevR}</button></div></td></tr>`).join('')}
   </tbody></table></div>`;
}
function kpiInfo(kid) {
  const k = (st.pulse?.kpis || []).find(x => x.id === kid) || st.meta.kpis.find(x => x.id === kid);
  openModal({ title: esc(k.name), body: `<dl class="kv" style="grid-template-columns:150px 1fr">
     <dt>Формула</dt><dd style="text-align:left;font-weight:500">${esc(k.formula)}</dd>
     <dt>Источники</dt><dd style="text-align:left;font-weight:500">${k.sources.map(s => `${esc(s.name)} — выгрузка ${fmtDT(s.last_sync)}`).join('<br>')}</dd>
     <dt>План / цель</dt><dd style="text-align:left;font-weight:500">${k.target != null ? `Целевое значение ${fmtK(k, k.target)}` : 'Утверждённый план (бюджет), пропорционально дням периода'}</dd>
     <dt>Владелец</dt><dd style="text-align:left;font-weight:500">${esc(k.dept_name)}${k.closed ? ' · закрытый показатель' : ''}</dd>
     <dt>Разрез по продукту</dt><dd style="text-align:left;font-weight:500">${k.product_scope ? 'Да' : 'Нет — показатель общий для компании'}</dd>
     <dt>Статус</dt><dd style="text-align:left;font-weight:500">Норма — план достигнут; «Внимание» — отставание в пределах допуска; «Критично» — за пределами допуска.</dd></dl>`,
    footer: `<button class="btn primary" data-action="close-modal">Понятно</button>` });
}

/* ================================================================ детализация KPI */
const DIM_PARAM = { product: 'product_name', section: 'section', channel: 'channel', campaign: 'campaign', reason: 'reason', topic: 'topic', tchannel: 'channel' };
async function openDrill(kid) {
  let d;
  try { d = await api(`/kpi/${kid}?` + fq()); }
  catch (e) { toast(e.message, 'err'); return; }
  ui.drill = { d, tab: 0, sel: null, page: 1 };
  openModal({ title: esc(d.name), size: 'xwide', body: `<div id="drill">${drillBody()}</div>`, footer: drillFooter() });
}
function drillFooter() {
  const d = ui.drill.d;
  return `${st.meta.permissions.decide ? `<button class="btn ${d.status === 'crit' ? 'primary' : 'ghost'}" data-action="decide" data-k="${d.id}">${I.plus}Создать решение</button>` : ''}<button class="btn ghost" data-action="close-modal">Закрыть</button>`;
}
function drillBody() {
  const { d } = ui.drill, ex = d.explanation;
  const filt = [d.period.label, st.F.dept !== 'all' ? st.meta.departments.find(x => x.id === st.F.dept)?.name : null, st.F.product !== 'all' ? st.meta.products.find(x => x.id === st.F.product)?.name : null].filter(Boolean).join(' · ');
  return `<p class="stl" style="margin-top:-8px">${esc(d.dept_name)} · ${esc(filt)}</p>
   <div class="mini">${[['План', fmtK(d, d.plan)], ['Факт', fmtK(d, d.fact)], [d.period.partial ? 'Прогноз на конец периода' : 'Прогноз', fmtK(d, d.forecast)], ['Отклонение от плана', badgeK(d) + stChip(d.status)]].map(([l, v]) => `<div><small>${l}</small><b>${v}</b></div>`).join('')}</div>
   <div class="explain" role="note"><b>${I.zap}Почему так</b><p>${esc(ex.text)}</p></div>
   <section class="knotes" id="knotes" aria-labelledby="kn-t">${notesInner()}</section>
   ${d.breakdowns.length ? `<div class="tabs" role="tablist" aria-label="Разрез детализации">${d.breakdowns.map((b, i) => `<button class="tab" role="tab" id="tab-${i}" aria-selected="${i === ui.drill.tab}" aria-controls="bdp" data-action="dtab" data-i="${i}">${esc(b.label)}</button>`).join('')}</div>
   <div id="bdp" role="tabpanel" aria-labelledby="tab-${ui.drill.tab}">${bdTable()}</div>` : ''}
   <div id="drill-list"></div>
   <div class="meta-line"><span><b>Формула:</b> ${esc(d.formula)}</span><span><b>Источники:</b> ${d.sources.map(s => `${esc(s.name)} (выгрузка ${fmtDT(s.last_sync)})`).join('; ')}</span><span><b>База сравнения:</b> ${esc(d.baseline.label)}${d.baseline.last_normal ? ' — последний период, когда показатель был в норме' : ''} · часовой пояс Europe/Minsk (UTC+3) · валюта BYN</span></div>`;
}
/* ответственный и комментарии по KPI: пишет директор, остальные с доступом к KPI читают */
function notesInner() {
  const n = ui.drill.d.notes || { owner: null, feed: [], can_edit: false };
  const oname = o => esc(o.name) + (o.title && o.title !== 'Должность' ? ' · ' + esc(o.title) : '');
  const own = n.can_edit
    ? `<label class="sr" for="kn-owner">Ответственный</label><select class="select" id="kn-owner"><option value="">— не назначен —</option>${st.meta.owners.map(o => `<option value="${esc(o.id)}" ${n.owner?.id === o.id ? 'selected' : ''}>${oname(o)}</option>`).join('')}</select>`
    : `<b class="kn-owner">${n.owner ? oname(n.owner) : 'не назначен'}</b>`;
  const feed = [...n.feed].reverse();
  return `<div class="kn-head"><h3 id="kn-t">${I.visitor}Ответственный</h3>${own}</div>
   <h3 class="kn-sub">Комментарии</h3>
   ${feed.length ? `<ul class="kn-feed">${feed.map(c => `<li class="${c.kind}"><div class="kn-meta"><b>${esc(c.user_name)}</b><small>${fmtDT(c.at)}</small></div><p>${esc(c.text)}</p></li>`).join('')}</ul>` : '<p class="muted small">Комментариев пока нет</p>'}
   ${n.can_edit ? `<div class="kn-add"><label class="sr" for="kn-text">Новый комментарий</label><textarea class="textarea" id="kn-text" maxlength="1000" placeholder="Комментарий к показателю…"></textarea><span class="err" id="kn-text-e" role="alert" hidden></span><button class="btn primary sm" data-action="kn-add">${I.plus}Добавить</button></div>` : ''}`;
}
function applyNotes(n) {
  const d = ui.drill?.d; if (!d) return;
  d.notes = n; const box = $('#knotes'); if (box) box.innerHTML = notesInner();
  const k = (st.pulse?.kpis || []).find(x => x.id === d.id);
  if (k) { k.responsible = n.owner; k.comments_count = n.feed.filter(c => c.kind === 'comment').length; const t = $('#ktable'); if (t) t.innerHTML = kpiTableInner(); }
}
async function setKpiOwner(v) {
  const sel = $('#kn-owner'); if (sel) sel.disabled = true;
  try { applyNotes(await api(`/kpi/${ui.drill.d.id}/owner`, { method: 'PATCH', body: { owner: v || null } })); toast(v ? 'Ответственный назначен' : 'Ответственный снят'); }
  catch (e) { toast(e.message, 'err'); if (sel) { sel.disabled = false; sel.value = ui.drill.d.notes?.owner?.id || ''; } }
}
document.addEventListener('change', e => { if (e.target.id === 'kn-owner') setKpiOwner(e.target.value); });
document.addEventListener('input', e => { if (e.target.id === 'kn-text') setErr('kn-text', ''); });
function bdTable() {
  const { d, tab } = ui.drill, b = d.breakdowns[tab]; if (!b) return '';
  const maxC = Math.max(...b.rows.map(r => Math.abs(r.contribution || 0)), 1e-9);
  const bad = d.dir === -1, clickable = !!(d.orders_kind && DIM_PARAM[b.dim]);
  const sumKind = ['revenue', 'new_customers', 'active_customers', 'reprint_cost', 'payroll'].includes(d.id);
  return `<div class="tbl-wrap"><table><thead><tr><th>${esc(b.label)}</th><th class="num">Значение</th><th class="num">База сравнения</th><th class="num">${sumKind ? 'Доля' : 'Вес'}</th><th>Вклад в изменение</th></tr></thead><tbody>
   ${b.rows.map(r => { const c = r.contribution || 0, w = Math.abs(c) / maxC * 50;
    return `<tr class="${clickable ? 'click' : ''}" ${clickable ? `data-action="dsel" data-key="${esc(r.key)}" tabindex="0" aria-label="Показать заказы: ${esc(r.key)}"` : ''}><td style="font-weight:600">${esc(r.key)}${ui.drill.sel === r.key ? ' ✓' : ''}</td><td class="num">${fmtK(d, r.value)}</td><td class="num muted">${fmtK(d, r.prev)}</td><td class="num">${nf(r.weight, 1)} %</td>
      <td><span class="contrib ${bad ? 'bad-up' : ''}" aria-hidden="true"><b class="${c < 0 ? 'neg' : 'pos'}" style="${c < 0 ? `right:50%;width:${w}%` : `left:50%;width:${w}%`}"></b></span> <span class="small" style="margin-left:6px">${c > 0 ? '+' : c < 0 ? '−' : ''}${d.unit === '%' ? nf(Math.abs(c), 2) + ' п.п.' : fmtK(d, Math.abs(c), true)}</span></td></tr>`; }).join('')}
   </tbody></table></div>${clickable ? '' : ''}`;
}
async function drillList() {
  const { d, sel, tab } = ui.drill, b = d.breakdowns[tab], box = $('#drill-list'); if (!box) return;
  box.innerHTML = `<div class="state">Загрузка…</div>`;
  try {
    if (d.orders_kind === 'tickets') {
      const r = await api('/tickets?' + fq({ breached: '1', [DIM_PARAM[b.dim] === 'channel' ? 'channel' : 'topic']: sel, page: ui.drill.page }));
      box.innerHTML = listHead(`Обращения с нарушением SLA · ${sel}`, r) + `<div class="tbl-wrap"><table><thead><tr><th>Обращение</th><th>Заказ</th><th>Тема</th><th>Канал</th><th>Создано</th><th class="num">Первый ответ</th><th class="num">SLA</th></tr></thead><tbody>
       ${r.items.map(t => `<tr class="click" data-action="order" data-id="${t.order_id}" tabindex="0"><td><b>${t.id}</b></td><td>${t.order_id}</td><td>${esc(t.topic)}</td><td>${esc(t.channel)}</td><td class="muted">${fmtT(t.created_at)}</td><td class="num neg-num">${nf(t.first_response_min)} мин</td><td class="num">${nf(t.sla_min)} мин</td></tr>`).join('')}</tbody></table></div>` + pager(r, 'dpage');
    } else {
      const kind = d.orders_kind === 'top' ? 'all' : d.orders_kind;
      const r = await api('/orders?' + fq({ kind, [DIM_PARAM[b.dim]]: sel, page: ui.drill.page }));
      const title = { late: 'Заказы с опозданием', defect: 'Заказы с браком', all: 'Заказы' }[kind] + ' · ' + sel;
      box.innerHTML = listHead(title, r) + ordersTable(r.items, kind) + pager(r, 'dpage');
    }
  } catch (e) { box.innerHTML = `<div class="state" role="alert"><b>Не удалось загрузить список</b>${esc(e.message)}</div>`; }
}
const listHead = (t, r) => `<h3 style="font-size:15px;margin:20px 0 8px;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap"><span>${esc(t)}</span><span class="muted small">Найдено: ${nf(r.total)}${r.amount != null ? ` · на ${nf(r.amount, 2)} BYN` : ''}</span></h3>`;
function ordersTable(items, kind) {
  if (!items.length) return '<div class="empty">Нет заказов</div>';
  return `<div class="tbl-wrap"><table><thead><tr><th>Заказ</th><th>Создан</th><th>Продукт</th><th>Канал</th><th class="num">Сумма</th><th>Статус</th><th>Срок</th><th>${kind === 'defect' ? 'Причина брака' : 'Опоздание'}</th></tr></thead><tbody>
   ${items.map(o => `<tr class="click" data-action="order" data-id="${o.id}" tabindex="0"><td><b>${o.id}</b></td><td class="muted">${fmtT(o.created_at)}</td><td>${esc(o.product)}</td><td>${esc(o.channel || 'не указан')}</td><td class="num">${nf(o.amount, 2)} BYN</td><td>${st2(o.status)}</td><td>${fmtD(o.promised_date)}</td><td>${kind === 'defect' ? esc(o.defect_reason || '—') : o.late_days ? `<span class="neg-num">+${o.late_days} дн.</span>` : '—'}</td></tr>`).join('')}</tbody></table></div>`;
}
function pager(r, action) {
  const pages = Math.max(1, Math.ceil(r.total / r.per_page)); if (pages <= 1) return '';
  return `<nav class="pager" aria-label="Страницы"><span>Стр. ${r.page} из ${pages}</span><div class="pg"><button data-action="${action}" data-p="${r.page - 1}" ${r.page <= 1 ? 'disabled' : ''} aria-label="Предыдущая страница">‹</button><button data-action="${action}" data-p="${r.page + 1}" ${r.page >= pages ? 'disabled' : ''} aria-label="Следующая страница">›</button></div></nav>`;
}
async function openOrder(id) {
  let r; try { r = await api('/orders/' + encodeURIComponent(id)); } catch (e) { toast(e.message, 'err'); return; }
  const o = r.order, inDrill = !!ui.drill && !$('#modal').hidden && $('#drill');
  const html = `${inDrill ? `<button class="back" data-action="drill-back">${I.chev}К показателю</button>` : ''}
   
   <div class="srcgrid">
    <section class="srcbox"><h3>ERP · заказ <span class="src-tag">${o.id}</span></h3><dl class="kv">
      <dt>Продукт</dt><dd>${esc(o.product)} · ${o.units} изд.</dd><dt>Канал</dt><dd>${esc(o.channel || 'не указан (пропуск)')}</dd><dt>Кампания</dt><dd>${esc(o.campaign || '—')}</dd>
      <dt>Сумма</dt><dd>${nf(o.amount, 2)} BYN${o.discount ? ` (скидка ${nf(o.discount, 2)})` : ''}</dd>${o.cost != null ? `<dt>Себестоимость</dt><dd>${nf(o.cost, 2)} BYN</dd>` : ''}
      <dt>Обещан к</dt><dd>${fmtD(o.promised_date)}${o.late_days ? ` · <span class="neg-num">опоздание ${o.late_days} дн.</span>` : ''}</dd>${o.defect ? `<dt>Брак</dt><dd class="neg-num">${esc(o.defect_reason)}</dd>` : ''}</dl>
      <ul class="timeline" aria-label="История статусов">${o.status_history.map(h => `<li><span><b>${esc(h.status)}</b><small>${fmtDT(h.at)}</small></span></li>`).join('')}</ul></section>
    <div style="display:grid;gap:14px;align-content:start">
     <section class="srcbox"><h3>CRM · клиент <span class="src-tag">${r.customer ? r.customer.id : '—'}</span></h3>${r.customer ? `<dl class="kv"><dt>Сегмент</dt><dd>${esc(r.customer.segment)}</dd><dt>Регион</dt><dd>${esc(r.customer.region)}</dd><dt>Клиент с</dt><dd>${fmtD(r.customer.created_at)}</dd><dt>Заказов всего</dt><dd>${r.customer.orders}</dd></dl>` : '<p class="muted">Клиент не найден в CRM</p>'}</section>
     <section class="srcbox"><h3>Helpdesk · обращения <span class="src-tag">${r.tickets.length}</span></h3>${r.tickets.length ? r.tickets.map(t => `<dl class="kv" style="margin-bottom:8px"><dt>${t.id}</dt><dd>${esc(t.topic)}</dd><dt>Первый ответ</dt><dd class="${t.sla_met ? 'pos-num' : 'neg-num'}">${t.first_response_min} мин (SLA ${t.sla_min})</dd><dt>Результат</dt><dd>${esc(t.result)}</dd></dl>`).join('') : '<p class="muted small">Обращений нет</p>'}</section>
     <section class="srcbox"><h3>MES · производство</h3>${r.production ? `<dl class="kv"><dt>Участок</dt><dd>${esc(r.production.section)}</dd><dt>Изготовлен</dt><dd>${fmtD(r.production.date)}</dd><dt>Загрузка в этот день</dt><dd>${r.production.load_day} %</dd><dt>Очередь на конец дня</dt><dd>${nf(r.production.queue_units_eod)} изд.</dd></dl>` : '<p class="muted small">Ещё не изготовлен</p>'}</section>
     <section class="srcbox"><h3>1С:Бухгалтерия</h3><p class="small ${r.finance.posted_1c ? '' : 'muted'}">${esc(r.finance.note.replace(/T(\d\d:\d\d).*$/, ' $1'))}</p></section>
    </div></div>`;
  if (inDrill) { $('#mtitle').textContent = 'Заказ ' + o.id; $('#drill').innerHTML = html; $('#drill').scrollIntoView({ block: 'start' }); }
  else openModal({ title: 'Заказ ' + esc(o.id), size: 'xwide', body: html, footer: `<button class="btn primary" data-action="close-modal">Закрыть</button>` });
}

/* ================================================================ карточка решения */
const DRAFT = 'fp:draft:decision';
function decisionPrefill(kid) {
  const d = ui.drill?.d?.id === kid ? ui.drill.d : null, k = d || (st.pulse?.kpis || []).find(x => x.id === kid) || st.meta.kpis.find(x => x.id === kid);
  const period = (d || st.pulse)?.period?.label || '';
  const facts = d ? d.explanation.factors.filter(f => f.source).map(f => f.text) : [];
  let dept = k.dept;
  if (st.user.role === 'head' && dept !== st.user.dept) dept = st.user.dept;
  const owner = st.meta.owners.find(o => o.dept === dept && !o.id.startsWith('pos-')) || st.meta.owners.find(o => o.dept === dept) || st.meta.owners[0];
  return { kpi_id: kid, dept, title: `${k.name}: ${fmtK(k, k.fact)} при плане ${fmtK(k, k.plan)} (${period})`,
    impact: k.dev != null ? `Отклонение ${devText(k)} от плана; статус «${STATUS[k.status] || '—'}»` : '',
    cause: d ? [(t => { const i = t.indexOf('Основной вклад'); return i >= 0 ? t.slice(i) : t; })(d.explanation.text), ...facts].filter(Boolean).join(' ') : '',
    action: '', owner: owner.id, due: new Date(Date.now() + 14 * 864e5).toISOString().slice(0, 10), priority: k.status === 'crit' ? 'Высокий' : 'Средний', status: 'Новое',
    context: { period: st.F.period, dept: st.F.dept, product: st.F.product, plan: k.plan, fact: k.fact, forecast: k.forecast, status: k.status } };
}
function openDecisionForm(existing, prefill) {
  const draft = !existing ? ls.get(DRAFT) : null;
  const useDraft = draft && (!prefill || draft.kpi_id === prefill.kpi_id);
  const v = existing || (useDraft ? draft : prefill) || { title: '', impact: '', cause: '', action: '', owner: st.meta.owners[0].id, due: new Date(Date.now() + 14 * 864e5).toISOString().slice(0, 10), priority: 'Средний', status: 'Новое', dept: st.user.dept || 'D-PROD', kpi_id: '' };
  const editable = !existing || existing.can_edit !== false;
  const depts = st.meta.departments.filter(d => st.user.role === 'director' || d.id === st.user.dept);
  const initial = JSON.stringify(collect0(v));
  openModal({ title: existing ? `${esc(existing.code)} · карточка решения` : 'Новое решение по отклонению', size: 'wide',
    body: `${useDraft && !existing ? `<div class="banner" style="background:var(--blue-soft);color:var(--blue)">${I.info}<span>Восстановлен несохранённый черновик.</span><button class="btn ghost sm" type="button" data-action="draft-clear">Очистить</button></div>` : ''}
     <form id="dform" class="form-grid" novalidate style="margin-top:4px">
      ${field({ id: 'd-title', label: 'Проблема', type: 'textarea', value: v.title, attrs: 'rows="2" maxlength="600" required' })}
      <div class="form-grid two" style="margin:0">${field({ id: 'd-impact', label: 'Влияние', type: 'textarea', value: v.impact, attrs: 'rows="3" maxlength="600"' })}${field({ id: 'd-cause', label: 'Причина', type: 'textarea', value: v.cause, attrs: 'rows="3" maxlength="600"' })}</div>
      ${field({ id: 'd-action', label: 'Действие', type: 'textarea', value: v.action, help: 'Что конкретно делаем, чтобы вернуть показатель к плану', attrs: 'rows="2" maxlength="600" required' })}
      <div class="form-grid two" style="margin:0">
        ${field({ id: 'd-owner', label: 'Ответственный', value: v.owner, opts: st.meta.owners.map(o => ({ value: o.id, label: o.name + (o.title !== 'Должность' ? ' — ' + o.title : '') })) })}
        ${field({ id: 'd-due', label: 'Срок', type: 'date', value: v.due })}
        ${field({ id: 'd-priority', label: 'Приоритет', value: v.priority, opts: st.meta.priorities.map(p => ({ value: p, label: p })) })}
        ${field({ id: 'd-status', label: 'Статус', value: v.status, opts: st.meta.statuses.map(p => ({ value: p, label: p })) })}
        ${field({ id: 'd-dept', label: 'Подразделение', value: v.dept, opts: depts.map(d => ({ value: d.id, label: d.name })), attrs: depts.length < 2 ? 'disabled' : '' })}
        ${field({ id: 'd-kpi', label: 'Показатель', value: v.kpi_id || '', opts: [{ value: '', label: '— не привязан —' }, ...st.meta.kpis.filter(k => !k.locked).map(k => ({ value: k.id, label: k.name }))] })}
      </div><button hidden></button></form>
      ${existing ? historyHtml(existing) : ''}`,
    footer: `<button class="btn ghost" data-action="close-modal">Отмена</button>${editable ? `<button class="btn primary" id="dsave">${existing ? 'Сохранить изменения' : 'Создать решение'}</button>` : ''}`,
    guard: () => JSON.stringify(collect()) !== initial,
    onMount: m => {
      if (!editable) $$('input,select,textarea', m).forEach(x => x.disabled = true);
      const persist = () => { if (!existing) ls.set(DRAFT, { ...collect(), context: v.context }); };
      $$('input,select,textarea', m).forEach(x => x.addEventListener('input', () => { setErr(x.id, ''); persist(); }));
      const save = async e => {
        e && e.preventDefault();
        const body = collect(); let ok = true;
        if (body.title.length < 5) { setErr('d-title', 'Опишите проблему (минимум 5 символов).'); ok = false; }
        if (body.action.length < 5) { setErr('d-action', 'Укажите действие (минимум 5 символов).'); ok = false; }
        if (!body.due) { setErr('d-due', 'Укажите срок.'); ok = false; }
        else if (!existing && body.due < new Date().toISOString().slice(0, 10)) { setErr('d-due', 'Срок не может быть в прошлом.'); ok = false; }
        if (!ok) { $('[aria-invalid="true"]', m)?.focus(); return; }
        const btn = $('#dsave'); btn.disabled = true; btn.textContent = 'Сохранение…';
        try {
          const r = existing ? await api('/decisions/' + existing.id, { method: 'PATCH', body: { ...body, version: existing.rev ?? 1 } })
            : await api('/decisions', { method: 'POST', body: { ...body, context: v.context } });
          if (!existing) ls.del(DRAFT);
          closeModal(true); toast(existing ? `${r.code}: изменения сохранены и записаны в журнал` : `${r.code} создано и записано в журнал`);
          loadAlerts(); if (route() === 'decisions') render(true);
        } catch (err) {
          btn.disabled = false; btn.textContent = existing ? 'Сохранить изменения' : 'Создать решение';
          if (err.fields) Object.entries(err.fields).forEach(([f, msg]) => setErr('d-' + ({ kpi_id: 'kpi' }[f] || f), msg));
          toast(err.message + (err.status === 0 ? '' : ''), 'err');
        }
      };
      $('#dsave') && ($('#dsave').onclick = save); $('#dform', m).onsubmit = save;
    } });
  function collect() { return { title: $('#d-title').value.trim(), impact: $('#d-impact').value.trim(), cause: $('#d-cause').value.trim(), action: $('#d-action').value.trim(), owner: $('#d-owner').value, due: $('#d-due').value, priority: $('#d-priority').value, status: $('#d-status').value, dept: $('#d-dept').value, kpi_id: $('#d-kpi').value || null }; }
  function collect0(x) { return { title: x.title || '', impact: x.impact || '', cause: x.cause || '', action: x.action || '', owner: x.owner, due: x.due, priority: x.priority, status: x.status, dept: x.dept, kpi_id: x.kpi_id || null }; }
}
function historyHtml(d) {
  return `<h3 style="font-size:15px;margin:22px 0 4px">История изменений</h3><ul class="timeline">${[...d.history].reverse().map(h => `<li><span><b>${esc(h.action)}</b> · ${esc(h.user_name)}<small>${fmtDT(h.at)}</small>${(h.changes || []).map(c => `<small>${esc(c.label || c.field)}: «${esc(fmtField(c.field, c.from))}» → «${esc(fmtField(c.field, c.to))}»</small>`).join('')}</span></li>`).join('')}</ul>`;
}
const fmtField = (f, v) => f === 'owner' ? (st.meta.owners.find(o => o.id === v)?.name || v) : f === 'dept' ? (st.meta.departments.find(d => d.id === v)?.name || v) : f === 'due' ? fmtD(v) : f === 'kpi_id' ? (st.meta.kpis.find(k => k.id === v)?.name || '—') : (v ?? '—');

/* ================================================================ общие блоки страниц */
function kpiTile(k, i) {
  if (k.locked) return `<button class="card kpi locked rise" style="--i:${i}" data-action="drill" data-k="${k.id}" aria-label="${esc(k.name)}: нет доступа"><div class="k-top"><span class="k-lbl">${esc(k.name)}</span><span class="k-ic">${I.lock}</span></div><div class="k-val">Нет доступа</div><div class="k-sub">Закрытый показатель · ${esc(k.dept_name)}</div></button>`;
  return `<button class="card kpi rise" style="--i:${i}" data-action="drill" data-k="${k.id}" aria-label="${esc(k.name)}: ${fmtK(k, k.fact)}, план ${fmtK(k, k.plan)}, ${STATUS[k.status]}">
   <div class="k-top"><span class="k-lbl">${esc(k.name)}</span><span class="k-ic">${I[KICON[k.id]] || I.file}</span></div>
   <div class="k-val">${fmtK(k, k.fact, true)}</div><div class="k-sub">${badgeK(k)}<span>план ${fmtK(k, k.plan, true)}</span>${k.forecast != null && k.forecast !== k.fact ? `<span>прогноз ${fmtK(k, k.forecast, true)}</span>` : ''}</div></button>`;
}
const srcLine = arr => `<p class="note">${I.db.replace('class="i"', 'class="i" style="width:14px;height:14px;vertical-align:-2px"')} Источники: ${arr.map(s => `${esc(s.name)} — ${fmtDT(s.last_sync)}`).join('; ')} · Europe/Minsk (UTC+3)</p>`;
const lockedPanel = (t, d) => `<div class="locked-panel"><span class="thumb">${I.lock}</span><div><b>${esc(t)}</b><p class="muted small" style="margin-top:4px">${esc(d)}</p></div></div>`;
const pctBar = (v, max, bad) => `<div class="track" style="max-width:none;margin:6px 0 0"><b style="width:${Math.max(0, Math.min(100, v / max * 100))}%;${bad ? 'background:var(--red)' : ''}"></b></div>`;
const signed = (v, d = 0, unit = '') => v == null ? '—' : `<span class="${v < 0 ? 'neg-num' : v > 0 ? 'pos-num' : ''}">${v > 0 ? '+' : v < 0 ? '−' : ''}${nf(Math.abs(v), d)}${unit}</span>`;

/* ================================================================ ПРОДАЖИ И КЛИЕНТЫ */
async function vSales() {
  const d = await api('/sales?' + fq()); st.sales = d;
  const f = d.funnel, top = f[0].value || 1;
  return `<div class="page">
   <div class="kpis">${d.kpis.map(kpiTile).join('')}</div>
   <div class="grid2">
    <section class="card panel rise" style="--i:4" aria-labelledby="fn-t"><div class="card-head"><div><h2 class="ttl" id="fn-t">Воронка picPac.by</h2><p class="stl">Сайт и приложение · ${esc(d.period.label)}</p></div></div>
     <ol class="funnel">${f.map((s, i) => `<li><span style="font-weight:600">${esc(s.step)}</span><div><div class="track"><b style="width:${Math.max(1.5, s.value / top * 100)}%"></b></div></div><span style="text-align:right"><b>${nf(s.value)}</b>${i ? `<div class="conv">${nf(s.value / f[i - 1].value * 100, 1)} % от пред.</div>` : ''}</span></li>`).join('')}</ol>
     <p class="note">Конверсия визит → заказ: <b>${nf(f[3].value / top * 100, 2)} %</b> · оплачено ${nf(f[4].value / Math.max(1, f[3].value) * 100, 1)} % заказов · отток клиентов к прошлому периоду: <b>${d.churn == null ? '—' : nf(d.churn, 1) + ' %'}</b></p>
     ${srcLine(d.funnel_source)}</section>
    <section class="card panel rise" style="--i:5" aria-labelledby="sg-t"><div class="card-head"><div><h2 class="ttl" id="sg-t">Сегменты</h2></div></div>
     <div class="tbl-wrap"><table style="min-width:420px"><thead><tr><th>Сегмент</th><th class="num">Заказы</th><th class="num">Клиенты</th><th class="num">Выручка</th><th class="num">Ср. чек</th><th>Доля</th></tr></thead><tbody>
     ${d.segments.map(s => `<tr><td style="font-weight:600">${esc(s.name)}</td><td class="num">${nf(s.orders)}</td><td class="num">${nf(s.customers)}</td><td class="num">${nf(s.revenue)} BYN</td><td class="num">${nf(s.avg_check, 2)}</td><td style="min-width:110px">${nf(s.share, 1)} %${pctBar(s.share, 100)}</td></tr>`).join('')}</tbody></table></div></section>
   </div>
   <section class="card panel rise" style="--i:6" aria-labelledby="ch-t"><div class="card-head" style="margin-bottom:12px"><div><h2 class="ttl" id="ch-t">Каналы продаж</h2></div><button class="btn ghost sm" data-action="sales-export">${I.download}CSV</button></div>
    <div class="tbl-wrap"><table><thead><tr><th>Канал</th><th class="num">Заказы</th><th class="num">Клиенты</th><th class="num">Выручка, BYN</th><th class="num">Ср. чек</th><th>Доля выручки</th><th class="num">К пред. периоду</th></tr></thead><tbody>
    ${d.channels.map(c => `<tr class="click" data-action="orders-by" data-p="channel" data-v="${esc(c.name)}" tabindex="0"><td><div class="cell-main"><span class="thumb">${I[CH_ICON[c.id]] || I.alert}</span>${esc(c.name)}</div></td><td class="num">${nf(c.orders)}</td><td class="num">${nf(c.customers)}</td><td class="num">${nf(c.revenue)}</td><td class="num">${nf(c.avg_check, 2)}</td><td style="min-width:130px">${nf(c.share, 1)} %${pctBar(c.share, 100)}</td><td class="num">${signed(c.delta, 1, ' %')}</td></tr>`).join('')}</tbody></table></div></section>
   <section class="card panel rise" style="--i:7" aria-labelledby="cp-t"><div class="card-head" style="margin-bottom:12px"><div><h2 class="ttl" id="cp-t">Маркетинговые кампании</h2></div></div>
    <div class="tbl-wrap"><table><thead><tr><th>Кампания</th><th>Продукт</th><th>Период</th><th class="num">Заказы</th><th class="num">Выручка</th><th class="num">Скидки</th><th class="num">Бюджет</th><th class="num">ROMI</th></tr></thead><tbody>
    ${d.campaigns.length ? d.campaigns.map(c => `<tr class="click" data-action="orders-by" data-p="campaign" data-v="${esc(c.name)}" tabindex="0"><td><b>${esc(c.name)}</b><div class="muted small">${esc(c.source)}</div></td><td>${esc(c.product)}</td><td class="muted">${fmtD(c.start)} — ${fmtD(c.end)}</td><td class="num">${nf(c.orders)}</td><td class="num">${nf(c.revenue)} BYN</td><td class="num">${nf(c.discount)} BYN</td><td class="num">${nf(c.budget)} BYN</td><td class="num">${c.romi == null ? `<span class="lock" title="Закрытый показатель подразделения «Финансы»">${I.lock}</span>` : signed(c.romi, 0, ' %')}</td></tr>`).join('') : '<tr><td colspan="8" class="empty">Кампаний в периоде нет</td></tr>'}</tbody></table></div></section>
  </div>`;
}
async function ordersBy(param, value, kind = 'all', page = 1) {
  const q = { kind, page }; q[param === 'channel' ? 'channel' : param === 'campaign' ? 'campaign' : param === 'section' ? 'section' : param] = value;
  let r; try { r = await api('/orders?' + fq(q)); } catch (e) { toast(e.message, 'err'); return; }
  ui.drill = null;
  const title = ({ late: 'Заказы с опозданием', defect: 'Заказы с браком', all: 'Заказы' }[kind]) + ' · ' + value;
  const body = listHead(title, r) + ordersTable(r.items, kind) + pager({ ...r }, 'ob-page');
  if (!$('#modal').hidden && $('#oblist')) { $('#oblist').innerHTML = body; }
  else openModal({ title: esc(title), size: 'xwide', body: `<div id="oblist">${body}</div>`, footer: `<button class="btn primary" data-action="close-modal">Закрыть</button>` });
  ui.ob = { param, value, kind };
}

/* ================================================================ ПРОИЗВОДСТВО И КАЧЕСТВО */
async function vProduction() {
  const d = await api('/production?' + fq());
  const c = d.chart, b = c.buckets, maxR = Math.max(1, ...d.defect_reasons.map(r => r.count));
  return `<div class="page">
   <div class="kpis five">${d.kpis.map(kpiTile).join('')}</div>
   <section class="card habits rise" style="--i:5" id="pc" aria-labelledby="pc-t"><div class="card-head"><div><h2 class="ttl" id="pc-t">Выпуск: план и факт</h2><p class="stl">${esc(d.period.label)} · изделий · в работе сейчас ${nf(d.queue_orders)} заказов</p></div></div>
    <div class="legend"><button class="lg" data-action="legend" data-chart="pch" data-s="a" aria-pressed="true"><i class="dot-seen"></i>План</button><button class="lg" data-action="legend" data-chart="pch" data-s="b" aria-pressed="true"><i class="dot-sales"></i>Факт</button>${b.some(x => x.forecast != null) ? '<span class="lg static"><i class="dot-fc"></i>Прогноз</span>' : ''}</div>
    ${barChart('pch', { labels: b.map(x => x.label), a: b.map(x => x.plan), b: b.map(x => x.fact), f: b.map(x => x.forecast), la: 'План', lb: 'Факт', lf: 'Прогноз', sub: b.map(x => `${fmtD(x.start)}–${fmtD(x.end)}`), fmt: v => v == null ? '—' : nf(v) + ' изд.', aria: 'Выпуск, план и факт.' })}</section>
   <section class="card panel rise" style="--i:6" aria-labelledby="sc-t"><div class="card-head" style="margin-bottom:12px"><div><h2 class="ttl" id="sc-t">Участки</h2></div></div>
    <div class="tbl-wrap"><table><thead><tr><th>Участок</th><th class="num">План, изд.</th><th class="num">Факт, изд.</th><th>Загрузка</th><th class="num">Очередь</th><th>Простои</th><th class="num">Брак</th><th class="num">Lead time</th><th class="num">Операторы</th></tr></thead><tbody>
    ${d.sections.map(s => `<tr class="click" data-action="orders-by" data-p="section" data-v="${esc(s.name)}" data-kind="late" tabindex="0"><td><div class="cell-main"><span class="thumb">${I[SEC_ICON[s.id]]}</span>${esc(s.name)}</div></td>
      <td class="num">${nf(s.plan_output)}</td><td class="num"><b>${nf(s.output)}</b> ${signed(s.plan_output ? (s.output - s.plan_output) / s.plan_output * 100 : null, 0, ' %')}</td>
      <td style="min-width:120px"><b class="${s.load > 100 ? 'neg-num' : ''}">${nf(s.load, 0)} %</b>${pctBar(s.load, 120, s.load > 100)}</td><td class="num">${nf(s.queue)} изд.</td>
      <td class="small">${nf(s.downtime_h, 1)} ч${s.downtime_reasons[0] ? `<div class="muted">${esc(s.downtime_reasons[0].reason)}</div>` : ''}</td>
      <td class="num ${s.defect > 2 ? 'neg-num' : ''}">${nf(s.defect, 2)} %<div class="muted small">${s.reprints} перепеч.</div></td><td class="num">${nf(s.lead_time, 1)} дн.</td>
      <td class="num ${s.staff && s.staff.fact < s.staff.plan ? 'neg-num' : ''}">${s.staff ? `${s.staff.fact} / ${s.staff.plan}` : '—'}<div class="muted small">смен ${s.staff?.shifts_fact ?? '—'} / ${s.staff?.shifts_plan ?? '—'}</div></td></tr>`).join('')}</tbody></table></div>
    ${srcLine(d.sources)}</section>
   <section class="card panel rise" style="--i:7" aria-labelledby="dr-t"><div class="card-head"><div><h2 class="ttl" id="dr-t">Причины брака и перепечатки</h2></div></div>
    <ol class="top-list">${d.defect_reasons.length ? d.defect_reasons.map(r => `<li class="click" data-action="orders-by" data-p="reason" data-v="${esc(r.reason)}" data-kind="defect" tabindex="0" style="cursor:pointer"><span class="thumb">${I.alert}</span><div><div class="nm">${esc(r.reason)}</div><div class="track"><b style="width:${r.count / maxR * 100}%;background:var(--red)"></b></div></div><b>${r.count}</b></li>`).join('') : '<li class="empty">Брака нет</li>'}</ol></section>
  </div>`;
}

/* ================================================================ ПРОГНОЗ СПРОСА И МОЩНОСТИ */
async function vForecast() {
  const d = await api('/forecast'); st.forecast = d;
  const w = d.weeks, dw = d.deficit_week;
  return `<div class="page">
   <section class="card stat primary rise" style="padding:26px 30px" aria-labelledby="dw-t"><div class="callout">
     <div><span class="pill">${I.clock}Прогноз на 6 недель · обновлён ${fmtT(d.generated_at)}</span>
      <h3 id="dw-t">${dw ? `Ожидаемый дефицит мощности: ${esc(dw.label)}` : 'Дефицита мощности в ближайшие 6 недель не ожидается'}</h3>
      <p>${dw ? dw.sections.map(s => `${esc(s.name)}: не хватает ${nf(s.gap)} изд.`).join(' · ') : 'Спрос укладывается в доступную мощность всех участков'}</p></div>
     ${dw && st.meta.permissions.decide ? `<button class="btn" style="background:#fff;color:var(--blue)" data-action="decide-forecast">${I.plus}Создать решение</button>` : ''}</div></section>
   <section class="card habits rise" style="--i:1" aria-labelledby="fc-t"><div class="card-head"><div><h2 class="ttl" id="fc-t">Спрос и доступная мощность</h2><p class="stl">Все участки · изделий в неделю</p></div></div>
    <div class="legend"><button class="lg" data-action="legend" data-chart="fch" data-s="a" aria-pressed="true"><i class="dot-seen"></i>Мощность</button><button class="lg" data-action="legend" data-chart="fch" data-s="b" aria-pressed="true"><i class="dot-sales"></i>Прогноз спроса</button><span class="lg static"><i class="dot-bad"></i>Дефицит</span></div>
    ${barChart('fch', { labels: w.map(x => x.short), a: w.map(x => x.capacity), b: w.map(x => x.demand), f: null, bad: w.map(x => x.deficit_sections.length > 0), la: 'Мощность', lb: 'Спрос', sub: w.map(x => x.label + (x.deficit_sections.length ? ' · дефицит: ' + x.deficit_sections.join(', ') : '')), fmt: v => nf(v) + ' изд.', aria: 'Прогноз спроса и мощности по неделям.', idx: Math.max(0, w.findIndex(x => x.deficit_sections.length)) })}</section>
   <section class="card panel rise" style="--i:2" aria-labelledby="fw-t"><div class="card-head" style="margin-bottom:12px"><div><h2 class="ttl" id="fw-t">Баланс по участкам и неделям</h2><p class="stl">Спрос / мощность, изделий</p></div></div>
    <div class="tbl-wrap"><table><thead><tr><th>Неделя</th>${w[0].sections.map(s => `<th class="num">${esc(s.name)}</th>`).join('')}<th class="num">Итого</th></tr></thead><tbody>
    ${w.map(x => `<tr class="${x.deficit_sections.length ? 'row-crit' : ''}"><td style="font-weight:600;white-space:nowrap">${esc(x.label)}</td>${x.sections.map(s => `<td class="num">${nf(s.demand)} / ${nf(s.capacity)}<div class="small">${signed(s.balance, 0)}</div></td>`).join('')}<td class="num"><b>${nf(x.demand)} / ${nf(x.capacity)}</b></td></tr>`).join('')}</tbody></table></div>
    <p class="note"><b>Метод:</b> ${esc(d.method)}</p>${srcLine(d.sources)}</section>
  </div>`;
}

/* ================================================================ ФИНАНСЫ И ЛЮДИ */
async function vFinance() {
  const d = await api('/finance?' + fq());
  const tbl = (rows, res, title, id) => `<section class="card panel rise" aria-labelledby="${id}"><div class="card-head" style="margin-bottom:12px"><div><h2 class="ttl" id="${id}">${title}</h2><p class="stl">BYN · ${d.months.join(', ')}</p></div></div>
     <div class="tbl-wrap"><table style="min-width:520px"><thead><tr><th>Статья</th><th>Подразделение</th><th class="num">План</th><th class="num">Факт</th><th class="num">Отклонение</th><th class="num">%</th></tr></thead><tbody>
     ${rows.map(r => { const good = r.article === 'Выручка' || r.article.startsWith('Поступления') ? r.dev >= 0 : r.dev <= 0; return `<tr><td style="font-weight:600">${esc(r.article)}</td><td class="muted">${esc(r.dept)}</td><td class="num">${nf(r.plan)}</td><td class="num">${nf(r.fact)}</td><td class="num"><span class="${good ? 'pos-num' : 'neg-num'}">${r.dev > 0 ? '+' : r.dev < 0 ? '−' : ''}${nf(Math.abs(r.dev))}</span></td><td class="num">${r.dev_pct == null ? '—' : nf(r.dev_pct, 1)}</td></tr>`; }).join('')}
     <tr style="font-weight:700"><td>Итог</td><td></td><td class="num">${nf(res.plan)}</td><td class="num">${nf(res.fact)}</td><td class="num">${signed(res.fact - res.plan)}</td><td></td></tr></tbody></table></div></section>`;
  return `<div class="page">
   <div class="kpis">${d.kpis.map(kpiTile).join('')}</div>
   ${d.access.finance ? `<div class="grid2">${tbl(d.bdr, d.bdr_result, 'БДР: доходы и расходы', 'bdr-t')}${tbl(d.bdds, d.bdds_result, 'БДДС: движение денег', 'bdds-t')}</div>
    <section class="card panel rise" aria-labelledby="mp-t"><div class="card-head" style="margin-bottom:12px"><div><h2 class="ttl" id="mp-t">Себестоимость и маржа по продуктам</h2></div></div>
     <div class="tbl-wrap"><table><thead><tr><th>Продукт</th><th class="num">Выручка, BYN</th><th class="num">Себестоимость, BYN</th><th>Валовая маржа</th></tr></thead><tbody>
     ${d.margin_by_product.map(p => `<tr><td style="font-weight:600">${esc(p.product)}</td><td class="num">${nf(p.revenue)}</td><td class="num">${nf(p.cost)}</td><td style="min-width:140px"><b class="${p.margin < 50 ? 'neg-num' : ''}">${nf(p.margin, 1)} %</b>${pctBar(p.margin, 100, p.margin < 50)}</td></tr>`).join('')}</tbody></table></div>
     <p class="note">${I.alert.replace('class="i"', 'class="i" style="width:14px;height:14px;vertical-align:-2px"')} ${esc(d.onec_note.replace(/T(\d\d:\d\d):\d\d\+03:00/, ' $1'))}</p></section>`
      : `<section class="card panel">${lockedPanel('БДР, БДДС и маржа скрыты для вашей роли', 'Это закрытые показатели подразделения «Финансы». Доступ: директор и аналитик. Проверка выполняется на сервере, попытка записана в журнал.')}</section>`}
   <section class="card panel rise" aria-labelledby="pp-t"><div class="card-head" style="margin-bottom:12px"><div><h2 class="ttl" id="pp-t">Персонал</h2><p class="stl">${esc(d.people_month)}</p></div></div>
    <div class="tbl-wrap"><table><thead><tr><th>Подразделение</th><th class="num">Штат</th><th class="num">Факт</th><th>Обеспеченность</th><th class="num">Вакансии</th><th class="num">Отпуск, дн.</th><th class="num">Больничный, дн.</th><th class="num">ФОТ план / факт, BYN</th></tr></thead><tbody>
    ${d.people.map(p => `<tr><td style="font-weight:600">${esc(p.dept)}</td><td class="num">${p.plan}</td><td class="num">${p.fact}</td><td style="min-width:130px"><b class="${p.staffing < 95 ? 'neg-num' : ''}">${nf(p.staffing, 1)} %</b>${pctBar(p.staffing, 100, p.staffing < 95)}</td><td class="num ${p.vacancies ? 'neg-num' : ''}">${p.vacancies}</td><td class="num">${nf(p.vacation_days, 1)}</td><td class="num">${nf(p.sick_days, 1)}</td><td class="num">${p.payroll_fact != null ? `${nf(p.payroll_plan)} / ${nf(p.payroll_fact)}` : `<span class="lock">${I.lock}закрыто</span>`}</td></tr>`).join('')}</tbody></table></div>
    ${srcLine(d.sources)}</section>
  </div>`;
}

/* ================================================================ РЕЕСТР РЕШЕНИЙ */
async function vDecisions() {
  const q = { status: ui.dstatus === 'overdue' ? 'all' : ui.dstatus, priority: ui.dprio, dept: ui.ddept, q: ui.dq, overdue: ui.dstatus === 'overdue' ? '1' : '0' };
  const d = await api('/decisions?' + new URLSearchParams(q)); st.decisions = d.items;
  const depts = st.meta.departments;
  return `<section class="card panel rise" aria-labelledby="dc-t">
   <div class="card-head" style="margin-bottom:16px"><div><h2 class="ttl" id="dc-t">Реестр решений</h2><p class="stl">${d.items.length} ${plural(d.items.length, 'решение', 'решения', 'решений')}</p></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn ghost" data-action="dec-export">${I.download}CSV</button>${d.can_create ? `<button class="btn primary" data-action="dec-new">${I.plus}Новое решение</button>` : `<span class="lock">${I.lock}Только просмотр</span>`}</div></div>
   <div class="toolbar"><label class="search-field">${I.search}<span class="sr">Поиск решений</span><input class="input" id="dq" type="search" placeholder="Поиск по проблеме, действию, ответственному…" value="${esc(ui.dq)}"></label>
    <label class="sr" for="dprio">Приоритет</label><select class="select" id="dprio"><option value="all">Любой приоритет</option>${st.meta.priorities.map(p => `<option ${ui.dprio === p ? 'selected' : ''}>${p}</option>`).join('')}</select>
    <label class="sr" for="ddept">Подразделение</label><select class="select" id="ddept"><option value="all">Все подразделения</option>${depts.map(x => `<option value="${x.id}" ${ui.ddept === x.id ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</select></div>
   <div class="chips" role="group" aria-label="Фильтр по статусу" style="margin-bottom:14px">${[['all', 'Все'], ...st.meta.statuses.map(s => [s, s]), ['overdue', 'Просрочено']].map(([v, l]) => `<button class="chip-btn" data-action="dstatus" data-v="${esc(v)}" aria-pressed="${ui.dstatus === v}">${esc(l)}</button>`).join('')}</div>
   ${d.items.length ? `<div class="tbl-wrap"><table><thead><tr><th>Код</th><th>Проблема и действие</th><th>Подразделение</th><th>Ответственный</th><th>Срок</th><th>Приоритет</th><th>Статус</th><th>Изменено</th></tr></thead><tbody>
   ${d.items.map(x => `<tr class="click ${x.overdue ? 'row-crit' : ''}" data-action="dec-open" data-id="${x.id}" tabindex="0"><td style="font-weight:700;white-space:nowrap">${x.code}</td><td style="max-width:380px"><b>${esc(x.title)}</b><div class="muted small">${esc(x.action)}</div>${x.kpi_name ? `<div class="small" style="color:var(--blue);margin-top:2px">${esc(x.kpi_name)}</div>` : ''}</td>
    <td class="small">${esc(x.dept_name)}</td><td class="small"><b>${esc(x.owner_name)}</b><div class="muted">${esc(x.owner_title === 'Должность' ? '' : x.owner_title)}</div></td>
    <td class="${x.overdue ? 'neg-num' : ''}" style="white-space:nowrap">${fmtD(x.due)}${x.overdue ? '<div class="small">просрочено</div>' : ''}</td><td>${st2(x.priority)}</td><td>${st2(x.status)}</td><td class="small muted" style="white-space:nowrap">${fmtT(x.updated_at)}<div>${x.history.length} ${plural(x.history.length, 'запись', 'записи', 'записей')}</div></td></tr>`).join('')}</tbody></table></div>`
      : `<div class="empty"><b>Решений не найдено</b>Измените фильтры или создайте решение из красного показателя.</div>`}
  </section>`;
}
function decisionsMount() {
  const re = () => render(true);
  let t; $('#dq').oninput = e => { clearTimeout(t); t = setTimeout(() => { ui.dq = e.target.value; re().then(() => { const i = $('#dq'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); }, 300); };
  $('#dprio').onchange = e => { ui.dprio = e.target.value; re(); };
  $('#ddept').onchange = e => { ui.ddept = e.target.value; re(); };
  const q = new URLSearchParams(location.hash.split('?')[1] || ''); if (q.get('id')) { history.replaceState(null, '', '#/decisions'); openDecision(q.get('id')); }
}
async function openDecision(id) {
  let d; try { d = await api('/decisions/' + id); } catch (e) { toast(e.message, 'err'); return; }
  d.can_edit = st.user.role === 'director' || (st.user.role === 'head' && st.user.dept === d.dept);
  openDecisionForm(d);
}

/* ================================================================ КАЧЕСТВО ДАННЫХ */
async function vQuality() {
  const d = await api('/quality');
  const card = (x, i) => `<div class="card kpi rise" style="--i:${i};cursor:default"><div class="k-top"><span class="k-lbl">${esc(x.check)}</span>${stChip(x.status)}</div><div class="k-val">${nf(x.count)}</div>
    <div class="k-sub">${esc(x.source)}${x.hint ? ' · ' + esc(x.hint) : ''}</div>${x.sample.length ? `<div class="small muted" style="margin-top:8px;word-break:break-word">Примеры: ${x.sample.slice(0, 5).map(s => Array.isArray(s) ? s.join(' = ') : s).map(s => /^ORD-/.test(s) ? `<button class="linkbtn" data-action="order" data-id="${s}">${s}</button>` : esc(s)).join(', ')}</div>` : ''}</div>`;
  return `<div class="page">
   <section class="card panel rise" aria-labelledby="sr-t"><div class="card-head" style="margin-bottom:12px"><div><h2 class="ttl" id="sr-t">Свежесть источников</h2><p class="stl">Проверено ${fmtDT(d.checked_at)}</p></div></div>
    <div class="tbl-wrap"><table><thead><tr><th>Источник</th><th>Сущность</th><th class="num">Записей</th><th>Последняя выгрузка</th><th class="num">Возраст</th><th>Статус</th><th>Владелец</th></tr></thead><tbody>
    ${d.sources.map(s => `<tr class="${s.status === 'crit' ? 'row-crit' : ''}"><td><b>${esc(s.name)}</b>${s.error ? `<div class="small neg-num">${esc(s.error)}</div>` : ''}</td><td><code>${s.entity}</code></td><td class="num">${nf(s.records)}</td><td>${fmtDT(s.last_sync)}</td><td class="num">${s.age_min >= 120 ? nf(s.age_min / 60, 1) + ' ч' : s.age_min + ' мин'}<div class="muted small">норма ${s.interval_min >= 60 ? s.interval_min / 60 + ' ч' : s.interval_min + ' мин'}</div></td><td>${stChip(s.status)}</td><td class="small muted">${esc(s.owner)}</td></tr>`).join('')}</tbody></table></div></section>
   <section aria-labelledby="gd-t"><div style="margin:4px 4px 14px"><h2 class="ttl" id="gd-t">Пропуски и дубли</h2></div>
   <div class="kpis">${[...d.gaps, ...d.duplicates].map(card).join('')}</div></section>
   <section class="card panel rise" aria-labelledby="rc-t"><div class="card-head" style="margin-bottom:12px"><div><h2 class="ttl" id="rc-t">Сверка финансовых итогов: ERP ↔ 1С</h2></div></div>
    <div class="tbl-wrap"><table><thead><tr><th>Месяц</th><th class="num">ERP</th><th class="num">1С</th><th class="num">Расхождение</th><th class="num">%</th><th>Статус</th><th>Комментарий</th></tr></thead><tbody>
    ${d.reconciliation.map(r => `<tr class="${r.status === 'crit' ? 'row-crit' : ''}"><td style="font-weight:600">${r.month}</td><td class="num">${nf(r.erp, 2)}</td><td class="num">${nf(r.one_c, 2)}</td><td class="num">${signed(r.diff, 2)}</td><td class="num">${nf(r.diff_pct, 2)}</td><td>${stChip(r.status)}</td><td class="small">${esc(r.note)}${r.by_product.length ? `<div class="muted">${r.by_product.map(p => `${esc(p.product)}: ${nf(p.diff, 2)}`).join('; ')}</div>` : ''}</td></tr>`).join('')}</tbody></table></div></section>
   <section class="card panel rise" aria-labelledby="lk-t"><h2 class="ttl" id="lk-t">Связность источников</h2>
    <div class="kpis" style="margin-top:16px"><div class="kpi" style="cursor:default;background:var(--surface-2);border-radius:18px"><span class="k-lbl">Заказы ERP с клиентом в CRM</span><div class="k-val">${nf(d.linkage.orders_with_customer, 1)} %</div></div><div class="kpi" style="cursor:default;background:var(--surface-2);border-radius:18px"><span class="k-lbl">Обращения с заказом в ERP</span><div class="k-val">${nf(d.linkage.tickets_with_order, 1)} %</div></div></div>
    <ul class="kb">${d.linkage.keys.map(k => `<li>${I.check.replace('class="i"', 'class="i" style="width:16px;height:16px;color:var(--blue);vertical-align:-3px;margin-right:6px"')}<code>${esc(k)}</code></li>`).join('')}</ul></section>
  </div>`;
}

/* ================================================================ ЖУРНАЛ ДЕЙСТВИЙ */
async function vAudit() {
  const d = await api('/audit?' + new URLSearchParams({ page: ui.apage, result: ui.aresult, user: ui.auser, q: ui.aq }));
  return `<section class="card panel rise" aria-labelledby="au-t">
   <div class="card-head" style="margin-bottom:16px"><div><h2 class="ttl" id="au-t">Журнал действий</h2><p class="stl">${nf(d.total)} записей</p></div><button class="btn ghost" data-action="audit-export">${I.download}CSV</button></div>
   <div class="toolbar"><label class="search-field">${I.search}<span class="sr">Поиск по журналу</span><input class="input" id="aq" type="search" placeholder="Действие или объект…" value="${esc(ui.aq)}"></label>
    <label class="sr" for="auser">Пользователь</label><select class="select" id="auser"><option value="all">Все пользователи</option>${['director', 'prod', 'sales', 'analyst'].map(u => `<option ${ui.auser === u ? 'selected' : ''}>${u}</option>`).join('')}</select>
    <div class="chips" role="group" aria-label="Результат">${[['all', 'Все'], ['успех', 'Успех'], ['отказано', 'Отказано']].map(([v, l]) => `<button class="chip-btn" data-action="aresult" data-v="${v}" aria-pressed="${ui.aresult === v}">${l}</button>`).join('')}</div></div>
   ${d.items.length ? `<div class="tbl-wrap"><table><thead><tr><th>Время (UTC+3)</th><th>Пользователь</th><th>Действие</th><th>Объект</th><th>Результат</th></tr></thead><tbody>
   ${d.items.map(r => `<tr><td class="small" style="white-space:nowrap">${fmtDT(r.at)}</td><td><b>${esc(r.user_name)}</b><div class="muted small">${esc(r.user)} · ${esc(r.role)}</div></td><td>${esc(r.action)}</td><td class="small">${esc(r.object)}${r.details ? `<div class="muted">${esc(typeof r.details === 'string' ? r.details : Object.entries(r.details).map(([k, v]) => k + ': ' + v).join('; '))}</div>` : ''}</td><td>${st2(r.result)}</td></tr>`).join('')}</tbody></table></div>${pager(d, 'apage')}`
      : '<div class="empty"><b>Записей нет</b></div>'}</section>`;
}
function auditMount() {
  let t; $('#aq').oninput = e => { clearTimeout(t); t = setTimeout(() => { ui.aq = e.target.value; ui.apage = 1; render(true).then(() => { const i = $('#aq'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); }, 300); };
  $('#auser').onchange = e => { ui.auser = e.target.value; ui.apage = 1; render(true); };
}

/* ================================================================ СПРАВКА */
async function vHelp() {
  const m = st.meta;
  return `<div class="page">
   <section class="card panel rise" aria-labelledby="hf-t"><h2 class="ttl" id="hf-t">Показатели: формулы и источники</h2>
    <div class="tbl-wrap" style="margin-top:14px"><table><thead><tr><th>Показатель</th><th>Формула</th><th>Источники</th><th>Владелец</th><th>Цель</th></tr></thead><tbody>
    ${m.kpis.map(k => `<tr><td style="font-weight:600">${esc(k.name)}<div class="muted small">${esc(k.unit)}</div></td><td class="small">${k.locked ? `<span class="lock">${I.lock}закрыто для роли</span>` : esc(k.formula)}</td><td class="small">${k.sources.map(s => esc(s.name)).join('<br>')}</td><td class="small">${esc(k.dept_name)}${k.closed ? '<div class="muted">закрытый</div>' : ''}</td><td class="small">${k.target != null ? fmtK(k, k.target) : 'бюджет'}</td></tr>`).join('')}</tbody></table></div></section>
   <div class="grid2">
    <section class="card panel rise" aria-labelledby="hr-t"><h2 class="ttl" id="hr-t">Роли и права</h2>
     <div class="tbl-wrap" style="margin-top:12px"><table style="min-width:420px"><thead><tr><th>Возможность</th><th>Директор</th><th>Руководитель</th><th>Аналитик</th></tr></thead><tbody>
     ${[['Пульс компании, финансы и люди', 1, 0, 1], ['Дашборд своего подразделения', 1, 'только свой', 1], ['KPI своего подразделения (вкл. закрытые)', 1, 1, 1], ['KPI других подразделений', 1, 0, 1], ['Реестр решений', 'создание и изменение', 0, 'чтение'], ['Качество данных, журнал', 1, 0, 1]].map(r => `<tr><td>${r[0]}</td>${r.slice(1).map(v => `<td>${v === 1 ? I.check.replace('class="i"', 'class="i" style="color:#16722e"') : v === 0 ? I.x.replace('class="i"', 'class="i" style="color:var(--muted)"') : `<span class="small">${v}</span>`}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
     <p class="note">Тестовые учётные записи: director, prod, sales, analyst · пароль demo2026 (синтетические данные).</p></section>
    <section class="card panel rise" aria-labelledby="hk-t"><h2 class="ttl" id="hk-t">Клавиатура и данные</h2>
     <div class="kb"><div>Поиск по разделам, KPI, заказам<span><kbd>Ctrl</kbd> / <kbd>⌘</kbd> + <kbd>K</kbd></span></div><div>Быстрый поиск<kbd>/</kbd></div><div>Закрыть окно или меню<kbd>Esc</kbd></div><div>Столбцы графика<span><kbd>←</kbd> <kbd>→</kbd></span></div></div>
     <p class="note">Данные: синтетический набор (seed ${m.data.seed}), ${nf(m.data.counts.orders)} заказов, ${nf(m.data.counts.customers)} клиентов, ${nf(m.data.counts.tickets)} обращений с ${fmtD(m.data.start)}. Сгенерирован ${fmtDT(m.data.generated_at)}. Время — Europe/Minsk (UTC+3), деньги — BYN.</p></section>
   </div>
   <section class="card panel rise" aria-labelledby="hl-t"><h2 class="ttl" id="hl-t">Сторонние компоненты и лицензии</h2>
    <div class="tbl-wrap" style="margin-top:12px"><table style="min-width:420px"><thead><tr><th>Компонент</th><th>Назначение</th><th>Лицензия</th></tr></thead><tbody>
     <tr><td>Plus Jakarta Sans (Google Fonts)</td><td>Шрифт интерфейса</td><td>SIL Open Font License 1.1</td></tr>
     <tr><td>Иконки в стиле Lucide (контуры нарисованы вручную)</td><td>Пиктограммы</td><td>ISC</td></tr>
     <tr><td>Python 3 (стандартная библиотека)</td><td>Сервер и генератор данных</td><td>PSF License</td></tr>
     <tr><td>Синтетический датасет «Фотопринт»</td><td>Демонстрационные данные</td><td>Создан командой, без реальных ПДн</td></tr></tbody></table></div></section>
  </div>`;
}

/* ================================================================ router */
const ROUTES = {
  pulse: { title: 'Пульс компании', view: vPulse, mount: () => { if (!st.silent) countUp($('#view')); requestAnimationFrame(placeAll); } },
  sales: { title: 'Продажи и клиенты', view: vSales },
  production: { title: 'Производство и качество', view: vProduction, mount: () => requestAnimationFrame(placeAll) },
  forecast: { title: 'Прогноз спроса и мощности', view: vForecast, mount: () => requestAnimationFrame(placeAll) },
  finance: { title: 'Финансы и люди', view: vFinance },
  decisions: { title: 'Реестр решений', view: vDecisions, mount: decisionsMount },
  quality: { title: 'Качество данных', view: vQuality },
  audit: { title: 'Журнал действий', view: vAudit, mount: auditMount },
  help: { title: 'Справка', view: vHelp },
};
const EXTRA_ACTIONS = ({
  'orders-by': a => ordersBy(a.dataset.p, a.dataset.v, a.dataset.kind || 'all'),
  'ob-page': a => ordersBy(ui.ob.param, ui.ob.value, ui.ob.kind, +a.dataset.p),
  'sales-export': () => { const d = st.sales; downloadCSV('channels_' + st.F.period + '.csv', [['Канал', 'Заказы', 'Клиенты', 'Выручка BYN', 'Средний чек', 'Доля %'], ...d.channels.map(c => [c.name, c.orders, c.customers, c.revenue, c.avg_check, c.share])]); toast('Файл выгружен'); },
  'decide-forecast': () => { const dw = st.forecast.deficit_week; openDecisionForm(null, { kpi_id: 'load', dept: st.user.role === 'head' ? st.user.dept : 'D-PROD', title: `Дефицит мощности на неделе ${dw.label}`, impact: dw.sections.map(s => `${s.name}: не хватает ${nf(s.gap)} изд.`).join('; '), cause: 'Прогноз спроса (сезонность, кампании, текущая очередь MES) превышает доступную мощность с учётом фактической численности операторов (1С:ЗУП).', action: '', owner: 'prod', due: dw.start, priority: 'Высокий', status: 'Новое', context: { forecast_week: dw.start } }); },
  'dec-new': () => openDecisionForm(null, null),
  'dec-open': a => openDecision(a.dataset.id),
  dstatus: a => { ui.dstatus = a.dataset.v; render(true); },
  'dec-export': () => downloadCSV('decisions.csv', [['Код', 'Проблема', 'Влияние', 'Причина', 'Действие', 'Ответственный', 'Срок', 'Приоритет', 'Статус', 'Подразделение', 'Изменено'], ...st.decisions.map(d => [d.code, d.title, d.impact, d.cause, d.action, d.owner_name, d.due, d.priority, d.status, d.dept_name, d.updated_at])]),
  aresult: a => { ui.aresult = a.dataset.v; ui.apage = 1; render(true); },
  apage: a => { ui.apage = +a.dataset.p; render(true); },
  'audit-export': async () => { try { const r = await api('/audit?per=1000&page=1'); downloadCSV('audit.csv', [['Время', 'Логин', 'Пользователь', 'Роль', 'Действие', 'Объект', 'Результат'], ...r.items.map(x => [x.at, x.user, x.user_name, x.role, x.action, x.object, x.result])]); } catch (e) { toast(e.message, 'err'); } },
});
const route = () => { const id = location.hash.replace(/^#\/?/, '').split('?')[0]; return ROUTES[id] && canScreen(id) ? id : homeRoute(); };
let renderSeq = 0, firstRender = true;
async function render(keepScroll) {
  if (!st.user) return;
  const id = route(), r = ROUTES[id], seq = ++renderSeq;
  { const [raw, qs] = location.hash.replace(/^#\/?/, '').split('?'); if (raw !== id) history.replaceState(null, '', '#/' + id + (qs ? '?' + qs : '')); }
  closeFloating(); closeDrawer(); markNav(); renderFbar();
  Object.keys(CH).forEach(k => delete CH[k]);
  $('#ptitle').textContent = r.title; document.title = r.title + ' · Фотопринт';
  const view = $('#view'); view.setAttribute('aria-busy', 'true');
  if (!keepScroll || !view.innerHTML) view.innerHTML = `<div class="skel" aria-label="Загрузка">${'<div></div>'.repeat(3)}</div>`;
  try {
    const html = await r.view();
    if (seq !== renderSeq) return;
    view.innerHTML = html; if (!st.silent) view.classList.remove('no-anim'); r.mount && r.mount();
  } catch (e) {
    if (seq !== renderSeq) return;
    if (e.status === 401) return;
    view.innerHTML = `<div class="card state" role="alert">${e.status === 403 ? I.lock : I.alert}<b>${e.status === 403 ? 'Нет доступа' : 'Не удалось загрузить данные'}</b>${esc(e.message)}<br><button class="btn ghost" data-action="retry">${I.undo}Повторить</button></div>`;
  }
  view.removeAttribute('aria-busy');
  if (!firstRender && !keepScroll) { window.scrollTo({ top: 0, behavior: REDUCED ? 'auto' : 'smooth' }); $('#ptitle').focus({ preventScroll: true }); }
  firstRender = false;
  const q = new URLSearchParams(location.hash.split('?')[1] || '');
  if (q.get('kpi')) { history.replaceState(null, '', '#/' + id); openDrill(q.get('kpi')); }
}

/* ================================================================ events */
document.addEventListener('click', e => {
  const ddBtn = e.target.closest('.dd-btn');
  if (ddBtn) { const menu = ddBtn.nextElementSibling, open = menu.hidden; closeFloating(menu); menu.hidden = !open; ddBtn.setAttribute('aria-expanded', open); if (open) ($('[aria-selected="true"]', menu) || menu.firstElementChild).focus(); return; }
  const opt = e.target.closest('.dd-menu li'); if (opt) { pickOption(opt); return; }
  const grp = e.target.closest('.grp'); if (grp) { CH[grp.dataset.chart].idx = +grp.dataset.i; placeTip(grp.dataset.chart); return; }
  const a = e.target.closest('[data-action]');
  if (!a) { if (!e.target.closest('.pop')) closeFloating(); return; }
  const act = a.dataset.action;
  const fn = ACTIONS[act] || EXTRA_ACTIONS[act]; fn && fn(a, e);
});
const ACTIONS = {
  'close-modal': () => closeModal(), 'open-drawer': openDrawer, 'close-drawer': closeDrawer, palette: () => openPalette(),
  retry: () => { setNet(false); render(true); },
  'toggle-pop': a => { const p = $('#pop-' + a.dataset.pop), open = p.hidden; closeFloating(p);
    if (open) { a.dataset.pop === 'notif' ? renderNotif() : renderProfileMenu(); p.hidden = false; a.setAttribute('aria-expanded', 'true'); p.querySelector('button,a')?.focus(); } else { p.hidden = true; a.setAttribute('aria-expanded', 'false'); } },
  'close-pops': () => closeFloating(),
  'read-all': async () => { try { await api('/alerts/read', { method: 'POST', body: { ids: st.alerts.map(x => x.id) } }); st.alerts.forEach(x => x.unread = false); renderNotif(); renderHeader(); } catch (e) { toast(e.message, 'err'); } },
  'notif-open': a => { api('/alerts/read', { method: 'POST', body: { ids: [a.dataset.id] } }).catch(() => { }); const n = st.alerts.find(x => x.id === a.dataset.id); n && (n.unread = false); renderHeader(); closeFloating(); },
  logout: () => doLogout(false),
  legend: a => { const c = CH[a.dataset.chart], s = a.dataset.s; c.hide[s] = !c.hide[s]; a.classList.toggle('off', c.hide[s]); a.setAttribute('aria-pressed', !c.hide[s]); $$(`#${a.dataset.chart} .bar.${s === 'a' ? 'g' : 'b'}`).forEach(b => b.classList.toggle('off', c.hide[s])); placeTip(a.dataset.chart); },
  pcat: a => { const i = +a.dataset.i; ui.pcatPin = ui.pcatPin === i ? null : i; setPcat(ui.pcatPin ?? i); }, // клик закрепляет участок, повторный — снимает
  cty: a => setGhl(ui.gHl === a.dataset.c ? null : a.dataset.c),
  kstat: a => { ui.kstat = a.dataset.v; $('#ktable').innerHTML = kpiTableInner(); $(`[data-action="kstat"][data-v="${ui.kstat}"]`)?.focus(); },
  kinfo: a => kpiInfo(a.dataset.k),
  drill: a => openDrill(a.dataset.k),
  decide: async a => {
    if (!st.meta.permissions.decide) { toast('Создавать решения может только директор', 'err'); return; }
    const kid = a.dataset.k;
    if (ui.drill?.d?.id !== kid) { try { ui.drill = { d: await api(`/kpi/${kid}?` + fq()), tab: 0, sel: null, page: 1 }; } catch { ui.drill = null; } }
    openDecisionForm(null, decisionPrefill(kid));
  },
  'kn-add': async a => {
    const t = $('#kn-text'), text = t.value.trim();
    if (!text) { setErr('kn-text', 'Введите текст комментария'); t.focus(); return; }
    a.disabled = true;
    try { applyNotes(await api(`/kpi/${ui.drill.d.id}/comments`, { method: 'POST', body: { text } })); toast('Комментарий добавлен'); $('#kn-text')?.focus(); }
    catch (e) { a.disabled = false; e.fields?.text ? setErr('kn-text', e.fields.text) : toast(e.message, 'err'); }
  },
  dtab: a => { ui.drill.tab = +a.dataset.i; ui.drill.sel = null; $$('.tab').forEach((t, i) => t.setAttribute('aria-selected', i === ui.drill.tab)); $('#bdp').innerHTML = bdTable(); $('#drill-list').innerHTML = ''; },
  dsel: a => { ui.drill.sel = a.dataset.key; ui.drill.page = 1; $('#bdp').innerHTML = bdTable(); drillList(); },
  dpage: a => { ui.drill.page = +a.dataset.p; drillList(); },
  order: a => openOrder(a.dataset.id),
  'drill-back': () => { $('#mtitle').textContent = ui.drill.d.name; $('#drill').innerHTML = drillBody(); if (ui.drill.sel) drillList(); },
  'draft-clear': () => { ls.del(DRAFT); closeModal(true); toast('Черновик удалён'); },
  'kpi-export': () => { const k = st.pulse.kpis.filter(x => !x.locked); downloadCSV('kpi_' + st.F.period + '.csv', [['Показатель', 'Подразделение', 'Ед.', 'План', 'Факт', 'Прогноз', 'Отклонение', 'Статус', 'Формула', 'Обновлено'], ...k.map(x => [x.name, x.dept_name, x.unit, x.plan, x.fact, x.forecast, devText(x), STATUS[x.status], x.formula, x.updated_at])]); toast('Файл KPI выгружен'); },
};
function pickOption(li) {
  const menu = li.parentElement, wrap = menu.closest('.dd'), key = wrap.dataset.dd, v = li.dataset.value;
  menu.hidden = true; menu.previousElementSibling.setAttribute('aria-expanded', 'false');
  const btn = menu.previousElementSibling; btn.firstChild.textContent = li.textContent;
  $$('li', menu).forEach(x => x.setAttribute('aria-selected', x === li));
  DD[key] && DD[key](v);
  btn.focus();
}
document.addEventListener('pointerover', e => {
  if (e.pointerType === 'touch') return;
  const g = e.target.closest('.grp'); if (g && CH[g.dataset.chart] && +g.dataset.i !== CH[g.dataset.chart].idx) { CH[g.dataset.chart].idx = +g.dataset.i; placeTip(g.dataset.chart); }
  const ring = e.target.closest('#pstat .ring[data-i]'), cat = e.target.closest('#pstat .cat');
  if ((ring || cat) && ui.pcatPin == null) { const i = +(ring || cat).dataset.i; if (i !== ui.pcat) setPcat(i); }
  const b = e.target.closest('#growth .bub, #growth .cty'); if (b && b.dataset.c !== ui.gHl) setGhl(b.dataset.c);
});
document.addEventListener('pointerout', e => {
  if (e.pointerType === 'touch') return;
  if (e.target.closest('#pstat .ring, #pstat .cat') && !e.relatedTarget?.closest?.('#pstat .ring[data-i], #pstat .cat')) setPcat(ui.pcatPin);
  if (e.target.closest('#growth .bub, #growth .cty') && !e.relatedTarget?.closest?.('#growth .bub, #growth .cty')) setGhl(null);
});
document.addEventListener('focusin', e => { const c = e.target.closest('#pstat .cat'); if (c) setPcat(+c.dataset.i); const g = e.target.closest('#growth .cty'); if (g) setGhl(g.dataset.c); });
document.addEventListener('keydown', e => {
  const m = $('#modal');
  if (!st.user) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); m.hidden ? openPalette() : closeModal(); return; }
  if (e.key === '/' && m.hidden && !e.target.closest('input,textarea,select,[contenteditable]')) { e.preventDefault(); openPalette(); return; }
  if (e.key === 'Escape') {
    const openDd = $$('.dd-menu').find(x => !x.hidden); if (openDd) { closeFloating(); openDd.previousElementSibling.focus(); return; }
    if (!m.hidden) { closeModal(); return; }
    const openPop = $$('.pop').find(x => !x.hidden); if (openPop) { closeFloating(); $(`[data-pop="${openPop.id.slice(4)}"]`).focus(); return; }
    if ($('#side').classList.contains('open')) { closeDrawer(); $('.burger').focus(); return; }
    if (ui.pcat != null) { ui.pcatPin = null; setPcat(null); } if (ui.gHl) setGhl(null); return;
  }
  if (e.key === 'Tab' && !m.hidden) { const f = $$('button:not([disabled]),a[href],input:not([type=hidden]):not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])', m).filter(x => x.offsetParent !== null);
    if (!f.length) return; const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); } return; }
  if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('tr[data-action]')) { e.preventDefault(); e.target.click(); return; }
  const li = e.target.closest('.dd-menu li');
  if (li) { const all = $$('li', li.parentElement), i = all.indexOf(li);
    if (e.key === 'ArrowDown') { e.preventDefault(); all[(i + 1) % all.length].focus(); } else if (e.key === 'ArrowUp') { e.preventDefault(); all[(i - 1 + all.length) % all.length].focus(); }
    else if (e.key === 'Home') { e.preventDefault(); all[0].focus(); } else if (e.key === 'End') { e.preventDefault(); all[all.length - 1].focus(); }
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pickOption(li); } else if (e.key === 'Tab') closeFloating(); return; }
  const g = e.target.closest('.grp');
  if (g && ['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(e.key)) { e.preventDefault(); const c = CH[g.dataset.chart], n = c.labels.length;
    c.idx = e.key === 'Home' ? 0 : e.key === 'End' ? n - 1 : (c.idx + (e.key === 'ArrowRight' ? 1 : -1) + n) % n; placeTip(g.dataset.chart); $$(`#${g.dataset.chart} .grp`)[c.idx].focus(); }
});
let rT; addEventListener('resize', () => { clearTimeout(rT); rT = setTimeout(() => { placeAll(); if (innerWidth > 1000) closeDrawer(); }, 80); });
addEventListener('hashchange', () => render());

/* ================================================================ поиск (палитра) */
function openPalette() {
  let sel = 0, items = [];
  openModal({ title: 'Поиск', bare: true, size: 'palette', body: `<div class="pin-in">${I.search}<label class="sr" for="pal-q">Поиск</label><input id="pal-q" autocomplete="off" placeholder="Разделы, показатели, решения, номер заказа ORD-…" role="combobox" aria-expanded="true" aria-controls="pal-list" autofocus><kbd>Esc</kbd></div>
    <ul class="pal-list" id="pal-list" role="listbox"></ul><div class="pal-foot"><span><kbd>↑</kbd> <kbd>↓</kbd> выбор</span><span><kbd>Enter</kbd> открыть</span></div>`,
    onMount: m => {
      const inp = $('#pal-q', m), list = $('#pal-list', m);
      const pages = NAV.flatMap(([, it]) => it.filter(x => canScreen(x[0])).map(([id, l, icn]) => ({ t: l, k: 'Раздел', icn, go: () => location.hash = '#/' + id })));
      const kpis = st.meta.kpis.map(k => ({ t: k.name, k: k.locked ? 'KPI · закрыт' : 'Показатель', icn: KICON[k.id] || 'file', go: () => { const h = homeRoute(); if (route() !== h) location.hash = '#/' + h; openDrill(k.id); } }));
      const draw = () => { const q = inp.value.trim().toLowerCase();
        const ord = /^ord-\d{3,}$/i.test(q) ? [{ t: q.toUpperCase(), k: 'Заказ ERP', icn: 'orders', go: () => openOrder(q.toUpperCase()) }] : [];
        items = [...ord, ...(q ? [...pages, ...kpis].filter(x => x.t.toLowerCase().includes(q)) : pages)].slice(0, 10); sel = Math.min(sel, Math.max(0, items.length - 1));
        list.innerHTML = items.length ? items.map((x, i) => `<li role="option" id="po${i}" data-i="${i}" aria-selected="${i === sel}"><span class="thumb">${I[x.icn]}</span>${esc(x.t)}<small>${x.k}</small></li>`).join('') : '<li class="muted" aria-disabled="true">Ничего не найдено</li>';
        inp.setAttribute('aria-activedescendant', items.length ? 'po' + sel : ''); };
      const choose = i => { const x = items[i]; if (!x) return; closeModal(true); x.go(); };
      inp.oninput = () => { sel = 0; draw(); };
      inp.onkeydown = e => { if (e.key === 'ArrowDown') { e.preventDefault(); sel = (sel + 1) % Math.max(1, items.length); draw(); } else if (e.key === 'ArrowUp') { e.preventDefault(); sel = (sel - 1 + items.length) % Math.max(1, items.length); draw(); } else if (e.key === 'Enter') { e.preventDefault(); choose(sel); } };
      list.onclick = e => { const li = e.target.closest('[data-i]'); li && choose(+li.dataset.i); };
      draw();
    } });
}

/* ================================================================ автообновление
   Сервер перечитывает базу раз в refresh_sec (15 с); экран тихо подтягивает свежие данные с той же частотой.
   Экран не трогаем, пока пользователь работает: открыто окно, меню, мобильное меню или курсор в поле ввода. */
let autoT = null;
function startAutoRefresh() {
  clearInterval(autoT);
  autoT = setInterval(silentRefresh, (st.meta?.refresh_sec || 15) * 1000);
}
async function silentRefresh() {
  if (!st.user || document.hidden || st.silent) return;
  const busy = !$('#modal').hidden || $$('.dd-menu').some(m => !m.hidden) || $$('.pop').some(p => !p.hidden) || $('#side').classList.contains('open')
    || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName);
  if (busy) return;
  const view = $('#view'); st.silent = true; view.classList.add('no-anim');
  // класс no-anim остаётся до следующей обычной отрисовки: если снять его сразу, анимации появления проиграются заново
  try { await render(true); await loadAlerts(); st.refreshedAt = new Date(); }
  finally { st.silent = false; }
}
document.addEventListener('visibilitychange', () => { if (!document.hidden && st.user && st.refreshedAt && Date.now() - st.refreshedAt > (st.meta?.refresh_sec || 15) * 1000) silentRefresh(); });

/* ================================================================ boot */
async function boot() {
  applyTheme();
  if (!st.token) { renderLogin(); return; }
  try {
    st.meta = await api('/meta'); st.user = st.meta.user;
  } catch (e) { if (e.status !== 401) renderLogin(e.message); return; }
  const def = { period: st.meta.default_period, dept: st.user.role === 'head' ? st.user.dept : 'all', product: 'all' };
  if (!st.F || st.F._u !== st.user.login || !st.meta.periods.some(p => p.key === st.F.period)) st.F = { ...def, _u: st.user.login };
  ss.set('fp:filters', st.F);
  $('#login').hidden = true; $('#login').innerHTML = ''; $('#app').hidden = false;
  renderSide(); renderHeader();
  if (!location.hash) history.replaceState(null, '', '#/' + homeRoute());
  await render();
  loadAlerts(); st.refreshedAt = new Date();
  startAutoRefresh();
}
boot();
