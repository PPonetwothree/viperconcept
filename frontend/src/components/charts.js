// Minimal SVG charts (no external library — runs offline). Values always come
// from recorded simulation data supplied by the caller.
import { s } from '../core/util.js';

const niceMax = (v) => {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((m) => m >= v);
};

/** Vertical bar chart. opts: {labels, values, colors?, height?, labelEvery?, unit?} */
export function barChart({ labels, values, colors, height = 170, labelEvery = 1, unit = '', title }) {
  const W = 560, H = height, L = 34, B = 22, T = 10, R = 6;
  const max = niceMax(Math.max(0, ...values));
  const n = values.length || 1;
  const bw = (W - L - R) / n;
  const svg = s('svg', { class: 'chart', viewBox: `0 0 ${W} ${H}`, width: '100%', role: 'img', 'aria-label': title || 'bar chart' });
  for (let i = 0; i <= 4; i++) {
    const y = T + (H - T - B) * (1 - i / 4);
    svg.append(s('line', { class: 'gridl', x1: L, x2: W - R, y1: y, y2: y }));
    svg.append(s('text', { x: L - 4, y: y + 3, 'text-anchor': 'end' }, +(max * i / 4).toFixed(2)));
  }
  values.forEach((v, i) => {
    const bh = (H - T - B) * (v / max);
    const x = L + i * bw + bw * 0.12, y = H - B - bh;
    const r = s('rect', { x, y, width: Math.max(1, bw * 0.76), height: Math.max(0, bh), fill: colors?.[i] || '#7fa7c9' });
    r.append(s('title', {}, `${labels[i]}: ${v}${unit}`));
    svg.append(r);
    if (i % labelEvery === 0) svg.append(s('text', { x: L + i * bw + bw / 2, y: H - 7, 'text-anchor': 'middle' }, labels[i]));
  });
  svg.append(s('line', { class: 'axis', x1: L, x2: W - R, y1: H - B, y2: H - B }));
  return svg;
}

/** Horizontal bars with labels on the left. rows: [{label, value, color?, text?}] */
export function hBars(rows, { max, unit = '', width = 560 } = {}) {
  const rh = 20, L = 190, R = 60;
  const H = rows.length * rh + 6;
  const m = max ?? niceMax(Math.max(0, ...rows.map((r) => r.value)));
  const svg = s('svg', { class: 'chart', viewBox: `0 0 ${width} ${H}`, width: '100%' });
  rows.forEach((r, i) => {
    const y = 3 + i * rh;
    svg.append(s('text', { x: L - 6, y: y + 13, 'text-anchor': 'end' }, r.label));
    svg.append(s('rect', { x: L, y: y + 3, width: width - L - R, height: rh - 7, fill: '#1b1e22' }));
    svg.append(s('rect', { x: L, y: y + 3, width: Math.max(0, (width - L - R) * (r.value / (m || 1))), height: rh - 7, fill: r.color || '#7fa7c9' }));
    svg.append(s('text', { x: width - R + 6, y: y + 13 }, r.text ?? `${r.value}${unit}`));
  });
  return svg;
}

/** Histogram of numeric samples. */
export function histogram(values, { bins = 12, unit = '', color = '#7fa7c9', height = 150 } = {}) {
  if (!values.length) return s('svg', { class: 'chart', viewBox: '0 0 560 40', width: '100%' }, s('text', { x: 10, y: 24 }, 'no samples yet'));
  const lo = Math.min(...values), hi = Math.max(...values);
  const w = (hi - lo) / bins || 1;
  const counts = Array(bins).fill(0);
  values.forEach((v) => { counts[Math.min(bins - 1, Math.floor((v - lo) / w))]++; });
  const labels = counts.map((_, i) => `${(lo + i * w).toFixed(0)}`);
  return barChart({ labels, values: counts, height, labelEvery: Math.ceil(bins / 6), colors: counts.map(() => color), title: `histogram ${unit}` });
}

/** Sparkline for live sensor history: points [{t, v}] */
export function sparkline(points, { w = 340, h = 60, color = '#7fa7c9', threshold } = {}) {
  const svg = s('svg', { class: 'chart', viewBox: `0 0 ${w} ${h}`, width: '100%', height: h });
  const vals = points.map((p) => p.v).filter((v) => v != null);
  if (vals.length < 2) { svg.append(s('text', { x: 6, y: h / 2 }, 'collecting samples…')); return svg; }
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (threshold != null) { lo = Math.min(lo, threshold); hi = Math.max(hi, threshold); }
  if (hi - lo < 1e-6) { hi += 0.5; lo -= 0.5; }
  const X = (i) => 2 + (i / (points.length - 1)) * (w - 40);
  const Y = (v) => h - 4 - ((v - lo) / (hi - lo)) * (h - 10);
  const d = points.map((p, i) => (p.v == null ? null : `${X(i).toFixed(1)},${Y(p.v).toFixed(1)}`)).filter(Boolean).join(' ');
  if (threshold != null) svg.append(s('line', { x1: 2, x2: w - 38, y1: Y(threshold), y2: Y(threshold), stroke: '#d8b13a', 'stroke-dasharray': '3 3' }));
  svg.append(s('polyline', { points: d, fill: 'none', stroke: color, 'stroke-width': 1.4 }));
  svg.append(s('text', { x: w - 34, y: 10 }, +hi.toFixed(2)));
  svg.append(s('text', { x: w - 34, y: h - 2 }, +lo.toFixed(2)));
  return svg;
}
