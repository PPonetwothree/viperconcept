// Data-flow packet animation. Packets are only spawned in response to real
// messages from the backend (observations, events, operator actions), so the
// animation always reflects application state.
import { s } from '../core/util.js';

const MAX_ACTIVE = 60;
let active = 0;

/** Move a dot along a polyline. points: [[x,y], ...]; duration scales with length. */
export function animatePath(layer, points, { color = '#7fa7c9', dur, speed = 0.55, r = 2.6, onDone } = {}) {
  if (!layer?.isConnected || points.length < 2 || active >= MAX_ACTIVE || document.hidden) return;
  const segs = [];
  let total = 0;
  for (let i = 1; i < points.length; i++) {
    const L = Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]);
    segs.push(L); total += L;
  }
  if (total < 1) return;
  const duration = dur ?? Math.min(1800, Math.max(350, total / speed));
  const dot = s('circle', { r, fill: color, class: 'pkt' });
  layer.append(dot);
  active++;
  const t0 = performance.now();
  const frame = (t) => {
    const k = Math.min(1, (t - t0) / duration);
    let d = k * total, i = 0;
    while (i < segs.length - 1 && d > segs[i]) { d -= segs[i]; i++; }
    const f = segs[i] ? d / segs[i] : 1;
    const [x0, y0] = points[i], [x1, y1] = points[i + 1];
    dot.setAttribute('cx', x0 + (x1 - x0) * f);
    dot.setAttribute('cy', y0 + (y1 - y0) * f);
    if (k < 1 && dot.isConnected) requestAnimationFrame(frame);
    else { dot.remove(); active--; onDone?.(); }
  };
  requestAnimationFrame(frame);
}
