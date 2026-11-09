// Small DOM/format helpers shared by every view.

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const SVGNS = 'http://www.w3.org/2000/svg';
export function s(tag, attrs = {}, ...children) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export const esc = (x) => String(x ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export const SEV_COLOR = { info: '#4caf7a', low: '#c9b14a', medium: '#d8b13a', high: '#e0832f', critical: '#d9473f' };
export const SEV_RANK = { info: 0, low: 1, medium: 2, high: 3, critical: 4 };
// Status palette per brief: green normal, yellow warning, orange suspicious, red critical.
export const STATUS_COLOR = { normal: '#4caf7a', warning: '#d8b13a', suspicious: '#e0832f', critical: '#d9473f' };
export const sevToStatus = (sev) => ({ info: 'normal', low: 'warning', medium: 'warning', high: 'suspicious', critical: 'critical' }[sev] || 'normal');

export const sevBadge = (sev) => h('span', { class: `sev sev-${sev}` }, sev);

const pad = (n, w = 2) => String(n).padStart(w, '0');
export function fmtUTC(epoch) {
  if (epoch == null) return '—';
  const d = new Date(epoch * 1000);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}.${pad(d.getUTCMilliseconds(), 3)}Z`;
}
export function tzAbbr() {
  try {
    const p = new Intl.DateTimeFormat('en-US', { timeZoneName: 'short' }).formatToParts(new Date()).find((x) => x.type === 'timeZoneName');
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (tz === 'Asia/Calcutta' || tz === 'Asia/Kolkata') return 'IST';
    return p ? p.value : '';
  } catch { return ''; }
}
const TZ = tzAbbr();
export function fmtLocal(epoch, withDate = true) {
  if (epoch == null) return '—';
  const d = new Date(epoch * 1000);
  const t = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
  return withDate ? `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${t} ${TZ}` : `${t}`;
}
export function fmtSim(sec) {
  if (sec == null) return '—';
  const s = Math.max(0, sec);
  const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
  return `T+${pad(hh)}:${pad(mm)}:${ss.toFixed(1).padStart(4, '0')}`;
}
export function fmtDur(sec) {
  if (sec == null || isNaN(sec)) return '—';
  if (sec < 1) return `${(sec * 1000).toFixed(0)} ms`;
  if (sec < 120) return `${sec.toFixed(1)} s`;
  return `${Math.floor(sec / 60)} m ${Math.round(sec % 60)} s`;
}
export const fmtMs = (ms) => (ms == null ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${ms.toFixed(0)} ms`);
export const pct = (v, d = 1) => (v == null ? '—' : `${(v * 100).toFixed(d)} %`);
export const humanize = (x) => String(x ?? '').replace(/_/g, ' ');

export function inr(n) {
  if (!n) return '—';
  return '₹' + Number(n).toLocaleString('en-IN');
}

export function download(filename, text, type = 'text/plain') {
  const blob = new Blob([text], { type });
  const a = h('a', { href: URL.createObjectURL(blob), download: filename });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

// Shared floating tooltip.
let tipEl;
export function showTip(evt, html) {
  if (!tipEl) { tipEl = h('div', { class: 'tip hidden' }); document.body.append(tipEl); }
  tipEl.innerHTML = html;
  tipEl.classList.remove('hidden');
  const x = Math.min(window.innerWidth - 380, evt.clientX + 14), y = Math.min(window.innerHeight - tipEl.offsetHeight - 8, evt.clientY + 12);
  tipEl.style.left = `${x}px`; tipEl.style.top = `${y}px`;
}
export function hideTip() { tipEl?.classList.add('hidden'); }
export function tipOn(el, htmlFn) {
  el.addEventListener('mousemove', (e) => showTip(e, typeof htmlFn === 'function' ? htmlFn() : htmlFn));
  el.addEventListener('mouseleave', hideTip);
  return el;
}

export function clear(el) { while (el.firstChild) el.firstChild.remove(); return el; }
