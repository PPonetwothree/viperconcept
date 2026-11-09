// Module D — animated top-down site schematic driven entirely by backend snapshots.
import { animatePath } from '../animations/flow.js';
import { SEV_COLOR, SEV_RANK, STATUS_COLOR, clear, fmtLocal, s, sevToStatus, showTip, hideTip, esc, humanize } from '../core/util.js';
import { state } from '../core/store.js';

const IMAGING = new Set(['optical', 'lowlight', 'ptz', 'thermal']);
const COV_COLOR = { optical: '#7fa7c9', lowlight: '#9fb7c9', ptz: '#a7b2c9', thermal: '#e0832f', radar: '#9c8bd0', pir: '#c9b14a', microwave: '#c9b14a' };
const SENSOR_STATUS_COLOR = { online: '#4caf7a', fault: '#d9473f', unreachable: '#6b7078', unpowered: '#3c4046' };
const LINK_COLOR = { online: '#4caf7a', link_down: '#d9473f', unpowered: '#6b7078' };

function wedge(sn) {
  const r = sn.range, a0 = (sn.dir - sn.fov / 2) * Math.PI / 180, a1 = (sn.dir + sn.fov / 2) * Math.PI / 180;
  if (sn.fov >= 360) return `M ${sn.x - r} ${sn.y} a ${r} ${r} 0 1 0 ${2 * r} 0 a ${r} ${r} 0 1 0 ${-2 * r} 0`;
  const x0 = sn.x + r * Math.cos(a0), y0 = sn.y + r * Math.sin(a0), x1 = sn.x + r * Math.cos(a1), y1 = sn.y + r * Math.sin(a1);
  return `M ${sn.x} ${sn.y} L ${x0} ${y0} A ${r} ${r} 0 ${sn.fov > 180 ? 1 : 0} 1 ${x1} ${y1} Z`;
}

function sensorIcon(sn) {
  const t = sn.type;
  if (IMAGING.has(t)) {
    return s('path', { d: 'M -6 -4 L 5 0 L -6 4 Z', transform: `rotate(${sn.dir})`, class: 'body' });
  }
  if (t === 'radar') return s('path', { d: 'M -5 3 A 6 6 0 0 1 5 3 Z', transform: `rotate(${sn.dir + 90})`, class: 'body' });
  if (t === 'fence') return s('rect', { x: -3.5, y: -3.5, width: 7, height: 7, transform: 'rotate(45)', class: 'body' });
  if (t === 'contact') return s('rect', { x: -4, y: -4, width: 8, height: 8, class: 'body' });
  if (t === 'pir' || t === 'microwave') return s('circle', { r: 3.6, class: 'body' });
  const letter = { temperature: 'T', smoke: 'S', leak: 'W' }[t] || '?';
  return s('g', {}, s('circle', { r: 5, class: 'body' }), s('text', { y: 3, 'text-anchor': 'middle', style: 'fill:#111;font:bold 7px sans-serif' }, letter));
}

export function createMap(host, { onSensor, onEvent, onNode } = {}) {
  const svg = s('svg', { viewBox: '-20 -20 1040 660', preserveAspectRatio: 'xMidYMid meet' });
  host.append(svg);
  const layers = {};
  for (const n of ['grid', 'zones', 'struct', 'cov', 'wires', 'links', 'fence', 'nodes', 'sensors', 'anom', 'ents', 'markers', 'sel', 'pkts']) {
    layers[n] = s('g', { class: `l-${n}` });
    svg.append(layers[n]);
  }
  const opts = { coverage: true, labels: true, wiring: false, packets: true };
  let sensorEls = {}, nodeEls = {}, zoneEls = {}, fenceEls = {}, entEls = {}, gateEls = {}, covEls = {};
  let env = null;

  function build(e) {
    env = e;
    Object.values(layers).forEach(clear);
    sensorEls = {}; nodeEls = {}; zoneEls = {}; fenceEls = {}; entEls = {}; gateEls = {}; covEls = {};
    for (let x = 0; x <= 1000; x += 50) layers.grid.append(s('line', { x1: x, x2: x, y1: 0, y2: 620, stroke: 'rgba(255,255,255,0.035)' }));
    for (let y = 0; y <= 620; y += 50) layers.grid.append(s('line', { x1: 0, x2: 1000, y1: y, y2: y, stroke: 'rgba(255,255,255,0.035)' }));
    layers.grid.append(s('text', { x: 1000, y: 634, 'text-anchor': 'end', class: 'struct-label' }, 'grid 50 m · conceptual layout'));
    for (const z of e.zones) {
      const [x0, y0, x1, y1] = z.rect;
      const r = s('rect', { x: x0, y: y0, width: x1 - x0, height: y1 - y0, class: 'zone-rect', fill: STATUS_COLOR.normal, 'fill-opacity': 0.035, stroke: STATUS_COLOR.normal, 'stroke-opacity': 0.35 });
      r.addEventListener('mousemove', (ev) => showTip(ev, `<b>${esc(z.name)}</b>${z.kind} zone`));
      r.addEventListener('mouseleave', hideTip);
      layers.zones.append(r, s('text', { x: x0 + 5, y: y0 + 12, class: 'zone-label' }, `ZONE ${z.id}`));
      zoneEls[z.id] = r;
    }
    for (const st of e.structures) {
      if (st.shape === 'circle') layers.struct.append(s('circle', { cx: st.x, cy: st.y, r: st.r, class: `struct ${st.cls}` }));
      else layers.struct.append(s('rect', { x: st.x, y: st.y, width: st.w, height: st.h, class: `struct ${st.cls}` }));
      layers.struct.append(s('text', { x: st.shape === 'circle' ? st.x : st.x + st.w / 2, y: (st.shape === 'circle' ? st.y : st.y + st.h / 2) + 3, 'text-anchor': 'middle', class: 'struct-label' }, st.label));
    }
    const p = e.perimeter.map((q) => q.join(',')).join(' ');
    layers.fence.append(s('polygon', { points: p, class: 'fence-solid' }), s('polygon', { points: p, class: 'fence' }));
    const c2 = e.command_centre;
    layers.nodes.append(s('rect', { x: c2.x - 16, y: c2.y - 9, width: 32, height: 18, fill: '#2c4a63', stroke: '#7fa7c9' }),
      s('text', { x: c2.x, y: c2.y + 4, 'text-anchor': 'middle', style: 'fill:#e3e5e8;font:bold 9px var(--mono)' }, 'C2'));
    for (const cp of e.checkpoints) {
      const g = s('g', { transform: `translate(${cp.x},${cp.y})` }, s('rect', { x: -14, y: -3, width: 28, height: 6, fill: '#1b1e22', stroke: '#c9b14a' }), s('text', { y: 16, 'text-anchor': 'middle', class: 'struct-label' }, cp.id));
      gateEls[cp.id] = g.firstChild;
      layers.fence.append(g);
    }
    for (const n of e.nodes) {
      const line = s('line', { x1: n.x, y1: n.y, x2: c2.x, y2: c2.y, class: 'link-line', stroke: LINK_COLOR.online, 'stroke-opacity': 0.45 });
      layers.links.append(line);
      const g = s('g', { transform: `translate(${n.x},${n.y})`, class: 'sensor-g' },
        s('rect', { x: -6, y: -6, width: 12, height: 12, fill: '#33475a', stroke: '#7fa7c9' }),
        s('text', { y: -9, 'text-anchor': 'middle' }, n.id));
      g.addEventListener('click', () => onNode?.(n.id));
      g.addEventListener('mousemove', (ev) => {
        const ns = state.snapshot?.nodes?.[n.id] || {};
        showTip(ev, `<b>${n.id} — edge node</b>${esc(state.meta?.node_models?.[n.model]?.label || n.model)}<br>Uplink: ${esc(state.meta?.links?.[n.link]?.label || n.link)}<br>Status: ${ns.status || '—'} · last latency ${ns.latency_ms ?? '—'} ms<br>Clock skew (simulated): ${ns.skew_ms ?? '—'} ms · buffered: ${ns.queue ?? 0}`);
      });
      g.addEventListener('mouseleave', hideTip);
      layers.nodes.append(g);
      nodeEls[n.id] = { g, line };
    }
    for (const sn of e.sensors) {
      if (opts.coverage && (IMAGING.has(sn.type) || ['radar', 'pir', 'microwave'].includes(sn.type))) {
        const w = s('path', { d: wedge(sn), class: 'cov', fill: COV_COLOR[sn.type], 'fill-opacity': sn.type === 'radar' ? 0.012 : 0.022, stroke: COV_COLOR[sn.type], 'stroke-opacity': 0, 'data-s': sn.id });
        layers.cov.append(w);
        covEls[sn.id] = w;
      }
      const node = e.nodes.find((n) => n.id === sn.node);
      if (node) layers.wires.append(s('line', { x1: sn.x, y1: sn.y, x2: node.x, y2: node.y, stroke: '#7fa7c9', 'stroke-opacity': 0.25, 'stroke-width': 0.6 }));
      if (sn.type === 'fence') {
        const [x1, y1, x2, y2] = sn.segment;
        const seg = s('line', { x1, y1, x2, y2, stroke: '#4caf7a', 'stroke-opacity': 0.5, 'stroke-width': 3 });
        layers.fence.append(seg);
        fenceEls[sn.id] = seg;
      }
      const g = s('g', { class: 'sensor-g', transform: `translate(${sn.x},${sn.y})` }, s('circle', { r: 8, class: 'ring' }), sensorIcon(sn),
        opts.labels ? s('text', { x: 7, y: -6 }, sn.id) : null);
      g.addEventListener('click', (ev) => { ev.stopPropagation(); onSensor?.(sn.id); });
      g.addEventListener('mousemove', (ev) => {
        const st = state.snapshot?.sensors?.[sn.id];
        showTip(ev, `<b>${sn.id} — ${esc(sn.type_label)}</b>Zone ${sn.zone} · node ${sn.node} · ${esc(sn.bus)}<br>Status: ${st?.status || '—'}<br>Reading: ${esc(st?.reading?.text ?? '—')}<br><span class="muted">Click to inspect</span>`);
      });
      g.addEventListener('mouseleave', hideTip);
      layers.sensors.append(g);
      sensorEls[sn.id] = g;
    }
    layers.cov.style.display = opts.coverage ? '' : 'none';
    layers.wires.style.display = opts.wiring ? '' : 'none';
  }

  function update(snap) {
    if (!env || !snap) return;
    for (const [id, st] of Object.entries(snap.sensors)) {
      const g = sensorEls[id];
      if (!g) continue;
      const body = g.querySelector('.body') || g.querySelector('circle:not(.ring)');
      const col = SENSOR_STATUS_COLOR[st.status] || '#888';
      g.querySelectorAll('.body').forEach((b) => b.setAttribute('fill', col));
      if (body && !g.querySelector('.body')) body.setAttribute('fill', col);
      g.classList.toggle('active', !!st.active);
      if (fenceEls[id]) {
        const v = st.reading?.value ?? 0;
        fenceEls[id].setAttribute('stroke', st.status !== 'online' ? col : v >= 0.8 ? STATUS_COLOR.critical : v >= 0.3 ? STATUS_COLOR.warning : STATUS_COLOR.normal);
      }
    }
    for (const [id, ns] of Object.entries(snap.nodes)) {
      const n = nodeEls[id];
      if (!n) continue;
      n.line.setAttribute('stroke', LINK_COLOR[ns.status] || '#888');
      n.line.setAttribute('stroke-opacity', ns.status === 'online' ? 0.45 : 0.9);
      n.g.firstChild.setAttribute('stroke', LINK_COLOR[ns.status] || '#888');
    }
    for (const [gid, open] of Object.entries(snap.gates || {})) gateEls[gid]?.setAttribute('fill', open ? '#c9b14a' : '#1b1e22');
    // entities
    const seen = new Set();
    for (const e of snap.entities) {
      seen.add(e.id);
      let g = entEls[e.id];
      if (!g) {
        let shape;
        if (e.kind === 'vehicle') shape = s('rect', { x: -6, y: -3.5, width: 12, height: 7, fill: '#cfd6de', stroke: '#4caf7a' });
        else if (e.kind === 'intruder') shape = s('path', { d: 'M 0 -6 L 5 0 L 0 6 L -5 0 Z', fill: '#e0832f', stroke: '#fff', 'stroke-width': 0.8 });
        else if (e.kind === 'animal') shape = s('circle', { r: 3, fill: '#a58a5a' });
        else shape = s('circle', { r: 3.8, fill: '#cfd6de', stroke: '#4caf7a', 'stroke-width': 1.2 });
        g = s('g', { class: 'ent' }, shape);
        g.addEventListener('mousemove', (ev) => showTip(ev, `<b>${esc(e.label)}</b>${e.kind} · ${e.authorized ? 'authorised (access-control record)' : 'NOT authorised'}<br><span class="muted">Simulated entity — not a real observation</span>`));
        g.addEventListener('mouseleave', hideTip);
        layers.ents.append(g);
        entEls[e.id] = g;
      }
      g.style.transform = `translate(${e.x}px, ${e.y}px)`;
      g.setAttribute('opacity', e.state === 'climbing' ? 1 : 0.95);
    }
    for (const id of Object.keys(entEls)) if (!seen.has(id)) { entEls[id].remove(); delete entEls[id]; }
    clear(layers.anom);
    for (const a of snap.anomalies) {
      const r = a.kind === 'fire' ? 8 + 30 * a.intensity : 22;
      layers.anom.append(s('circle', { cx: a.x, cy: a.y, r, fill: a.kind === 'fire' ? '#d9473f' : '#5b9bd5', 'fill-opacity': 0.18, stroke: a.kind === 'fire' ? '#d9473f' : '#5b9bd5', 'stroke-dasharray': '3 2' }),
        s('text', { x: a.x, y: a.y - r - 3, 'text-anchor': 'middle', class: 'struct-label', style: `fill:${a.kind === 'fire' ? '#f0a39e' : '#9cc3e8'}` }, `SIM ${a.kind}`));
    }
  }

  function setEvents(events, selectedId) {
    clear(layers.markers); clear(layers.sel);
    const zoneSev = {};
    for (const ev of events) {
      if (ev.severity === 'info' || !['open', 'response_initiated'].includes(ev.resolution_status)) continue;
      if (SEV_RANK[ev.severity] > SEV_RANK[zoneSev[ev.zone] || 'info']) zoneSev[ev.zone] = ev.severity;
      const sn = env.sensors.find((x) => x.id === ev.sensor_id) || env.nodes.find((x) => x.id === ev.sensor_id);
      const z = env.zones.find((x) => x.id === ev.zone);
      const pos = ev.contributing?.find((c) => c.details?.position)?.details.position || (sn ? [sn.x, sn.y] : z ? [(z.rect[0] + z.rect[2]) / 2, (z.rect[1] + z.rect[3]) / 2] : [500, 600]);
      const m = s('g', { class: 'marker', transform: `translate(${pos[0]},${pos[1] - 14})` },
        s('path', { d: 'M 0 -7 L 7 0 L 0 7 L -7 0 Z', fill: SEV_COLOR[ev.severity], stroke: ev.event_id === selectedId ? '#fff' : '#111', 'stroke-width': ev.event_id === selectedId ? 2 : 1 }),
        s('text', { y: -10, 'text-anchor': 'middle', style: 'fill:#e3e5e8;font:9px var(--mono)' }, ev.event_id.slice(-4)));
      m.addEventListener('click', () => onEvent?.(ev.event_id));
      m.addEventListener('mousemove', (e) => showTip(e, `<b>${ev.event_id} · ${ev.severity.toUpperCase()}</b>${esc(ev.category_label)}<br>${esc(ev.description)}<br>${fmtLocal(ev.created_epoch)}`));
      m.addEventListener('mouseleave', hideTip);
      layers.markers.append(m);
      if (ev.event_id === selectedId) {
        for (const c of ev.contributing || []) {
          const cs = env.sensors.find((x) => x.id === c.sensor_id);
          if (cs) layers.sel.append(s('line', { x1: cs.x, y1: cs.y, x2: pos[0], y2: pos[1] - 14, stroke: SEV_COLOR[ev.severity], 'stroke-dasharray': '2 2', 'stroke-opacity': 0.8 }));
        }
      }
    }
    for (const [zid, el] of Object.entries(zoneEls)) {
      const col = STATUS_COLOR[sevToStatus(zoneSev[zid] || 'info')];
      el.setAttribute('fill', col); el.setAttribute('stroke', col);
      el.setAttribute('fill-opacity', zoneSev[zid] ? 0.12 : 0.035);
      el.setAttribute('stroke-opacity', zoneSev[zid] ? 0.85 : 0.35);
    }
  }

  function setSelectedSensor(id) {
    for (const [sid, g] of Object.entries(sensorEls)) g.classList.toggle('sel', sid === id);
    for (const [sid, w] of Object.entries(covEls)) {
      const on = sid === id;
      w.setAttribute('fill-opacity', on ? 0.13 : (w.dataset.base ??= w.getAttribute('fill-opacity')));
      w.setAttribute('stroke-opacity', on ? 0.7 : 0);
    }
    if (id && covEls[id]) layers.cov.style.display = '';
  }

  function flowObservation(o) {
    if (!opts.packets || !env) return;
    const sn = env.sensors.find((x) => x.id === o.sensor_id) || (o.sensor_id === 'UPS-1' ? env.command_centre : null);
    const node = env.nodes.find((x) => x.id === o.node_id);
    const c2 = env.command_centre;
    if (!sn) return;
    const pts = node ? [[sn.x, sn.y], [node.x, node.y], [c2.x, c2.y]] : [[sn.x, sn.y], [c2.x, c2.y]];
    const color = o.kind === 'fault' || o.kind === 'power' ? '#d9473f' : (o.flags || []).includes('late_delivery') ? '#9c8bd0' : '#d8b13a';
    animatePath(layers.pkts, pts, { color, speed: 0.6 });
  }

  function setOption(k, v) {
    opts[k] = v;
    if (k === 'coverage') layers.cov.style.display = v ? '' : 'none';
    if (k === 'wiring') layers.wires.style.display = v ? '' : 'none';
    if (k === 'labels') layers.sensors.querySelectorAll('text').forEach((t) => { t.style.display = v ? '' : 'none'; });
  }

  return { build, update, setEvents, setSelectedSensor, flowObservation, setOption, opts };
}
