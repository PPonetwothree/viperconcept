// Module E — AI-assisted (rule-based) sensor fusion engine, made transparent.
import { on, sortedEvents, state } from '../core/store.js';
import { SEV_COLOR, clear, fmtUTC, h, humanize, s, sevBadge } from '../core/util.js';
import { api } from '../core/api.js';

const RULES = [
  ['V1/V2', 'Validation', 'Reject unknown sensor, faulted sensor, value outside physical range, timestamp > 1 s in the future, quality outside 0–1.'],
  ['T1', 'Time sync', 'corrected_ts = sensor_ts − offset(node); offset estimated from heartbeats (EMA, α = 0.2). Late (> 5 s) deliveries flagged, still correlated by sensor time.'],
  ['K1', 'Correlation', 'Same zone, within 6 s window; closes early when ≥ 3 independent modalities agree. Follow-ups within 45 s merge into the open incident (M1) and may escalate it.'],
  ['C1', 'Evidence score', 'E = 1 − Π(1 − wᵢ·qᵢ) over the best observation of each independent modality (optical, thermal, PIR, microwave, fence, radar, contact, smoke, temperature, leak).'],
  ['W', 'Context weights', 'Fence weight × 0.5 when wind ≥ 8 m/s at observation; optical weight × 0.6 when ambient light < 0.3.'],
  ['R1', 'Authorised presence', 'Access control reported authorised personnel/vehicle in the zone at observation time and no breach indicator → Normal activity (info, auto-closed, rate-limited 1/45 s/zone).'],
  ['R2', 'Wildlife vote', 'Confidence-weighted vote of edge labels = animal (≥ 60 %) and no breach → Environmental disturbance (low).'],
  ['R3', 'Wind compensation', 'Fence-only, peak < 0.8 g, wind ≥ 8 m/s → Environmental disturbance (low).'],
  ['R4', 'Unauthorised access point', 'Contact opened without credential → Potential perimeter anomaly (medium).'],
  ['R5', 'Single modality', 'One modality, no corroboration → Unverified movement (PIR/MW: low; others: medium).'],
  ['R6', 'Perimeter corroboration', '≥ 2 modalities incl. fence/contact/radar → Potential perimeter anomaly; critical if ≥ 3 and (E ≥ 0.8 or breach ≥ 0.8 g).'],
  ['R7', 'Interior corroboration', '≥ 2 interior modalities → Unverified movement (medium; high if ≥ 3).'],
  ['E1–E4', 'Environmental', 'Leak (medium; high at fuel facility) · smoke + temperature (high; critical if ≥ 8 %obs/m and ≥ 60 °C) · smoke only (medium) · temperature only (low).'],
  ['F1/P1/H1', 'System health', 'Device self-test fault → Equipment malfunction · mains loss → Equipment malfunction (power) · heartbeat > 7 s → Communication failure.'],
];

function timeSyncChart(ev) {
  const obs = ev.contributing;
  if (!obs.length) return h('div', { class: 'small muted' }, 'no observations (system-generated event)');
  const t0 = Math.min(...obs.map((o) => Math.min(o.sensor_ts, o.corrected_ts || o.sensor_ts)));
  const t1 = Math.max(...obs.map((o) => Math.max(o.sensor_ts, o.corrected_ts || o.sensor_ts, (o.ingest_ts || 0)))) ;
  const W = 640, L = 90, R = 20, rowH = 18, H = obs.length * rowH + 30;
  const X = (t) => L + ((t - t0) / Math.max(0.001, t1 - t0)) * (W - L - R);
  const svg = s('svg', { class: 'chart', viewBox: `0 0 ${W} ${H}`, width: '100%' });
  obs.forEach((o, i) => {
    const y = 12 + i * rowH;
    svg.append(s('text', { x: L - 6, y: y + 4, 'text-anchor': 'end' }, o.sensor_id));
    const raw = X(o.sensor_ts), cor = X(o.corrected_ts || o.sensor_ts), ing = o.ingest_ts ? X(o.ingest_ts) : null;
    svg.append(s('line', { x1: raw, x2: cor, y1: y, y2: y, stroke: '#9c8bd0', 'stroke-dasharray': '2 2' }));
    svg.append(s('circle', { cx: raw, cy: y, r: 3.5, fill: 'none', stroke: '#9c8bd0' }));
    svg.append(s('circle', { cx: cor, cy: y, r: 3.5, fill: '#7fa7c9' }));
    if (ing) svg.append(s('rect', { x: ing - 2, y: y - 4, width: 4, height: 8, fill: '#d8b13a' }));
  });
  svg.append(s('text', { x: L, y: H - 4 }, `0 = ${fmtUTC(t0).slice(11)}`), s('text', { x: W - R, y: H - 4, 'text-anchor': 'end' }, `+${((t1 - t0) * 1000).toFixed(0)} ms`));
  return h('div', {}, svg, h('div', { class: 'small muted' }, '○ raw edge-clock timestamp · ● corrected timestamp · ▮ ingest (arrival at fusion). Clock correction aligns nodes whose clocks drift by hundreds of ms.'));
}

function evidenceBars(ev) {
  if (!ev.evidence?.length) return h('div', { class: 'small muted' }, 'System-health event — evidence derived from device/heartbeat status, not modality fusion.');
  const rows = ev.evidence.map((x) => h('tr', {}, h('td', {}, x.modality), h('td', { class: 'mono' }, x.sensor_id), h('td', { class: 'mono' }, x.base_weight.toFixed(2)),
    h('td', { class: 'mono' }, x.weight.toFixed(3)), h('td', { class: 'mono' }, x.quality.toFixed(2)),
    h('td', {}, h('div', { class: 'bar', style: { width: '140px' } }, h('i', { style: { width: `${x.score * 100}%` } })), h('span', { class: 'mono small' }, x.score.toFixed(3))),
    h('td', { class: 'small dim' }, x.adjustment || '')));
  const terms = ev.evidence.map((x) => `(1 − ${x.score.toFixed(3)})`).join(' × ');
  return h('div', { class: 'col' }, h('table', {}, h('thead', {}, h('tr', {}, ['Modality', 'Best sensor', 'Base w', 'Adjusted w', 'Quality q', 'w·q', 'Adjustment'].map((x) => h('th', {}, x)))), h('tbody', {}, rows)),
    h('div', { class: 'formula' }, `E = 1 − ${terms} = ${ev.confidence.toFixed(3)}`));
}

function bayesPanel(ev) {
  const out = h('div', { class: 'stat-big' });
  const expl = h('div', { class: 'small dim' });
  const p = { base: 0.02, tpr: 0.9, fpr: 0.05 };
  const upd = () => {
    const ppv = (p.tpr * p.base) / (p.tpr * p.base + p.fpr * (1 - p.base));
    out.textContent = `${(ppv * 100).toFixed(1)} %`;
    expl.textContent = `P(genuine | alert) = TPR·π / (TPR·π + FPR·(1−π)) with π = ${p.base}, TPR = ${p.tpr}, FPR = ${p.fpr}. Out of 1 000 alert-worthy situations: ${(p.tpr * p.base * 1000).toFixed(1)} genuine detections vs ${(p.fpr * (1 - p.base) * 1000).toFixed(1)} false alarms.`;
  };
  const slider = (k, label, min, max, step) => h('label', { class: 'col', style: { gap: '2px' } }, h('span', { class: 'small' }, label),
    h('input', { type: 'range', min, max, step, value: p[k], oninput: (e) => { p[k] = +e.target.value; e.target.nextSibling.textContent = p[k]; upd(); } }), h('span', { class: 'mono small' }, p[k]));
  upd();
  return h('div', { class: 'col' },
    h('div', { class: 'note' }, h('b', {}, 'Evidence score ≠ probability of a threat. '), `This incident's evidence score is ${ev ? ev.confidence.toFixed(2) : '—'}. It measures how strongly independent sensors corroborate each other. The probability that an alert is a genuine threat also depends on how rare genuine threats are (base rate) and on the true detection/false-alarm rates — which can only be measured in a pilot.`),
    h('h4', {}, 'Illustrative calculator (assumed values, not measurements)'),
    slider('base', 'Base rate π (share of situations that are genuine)', 0.001, 0.5, 0.001),
    slider('tpr', 'Assumed detection rate (TPR)', 0.5, 0.99, 0.01),
    slider('fpr', 'Assumed false-alarm rate (FPR)', 0.001, 0.5, 0.001),
    h('div', { class: 'row' }, h('span', { class: 'small muted' }, 'Positive predictive value'), out), expl);
}

export function fusionView() {
  let unsubs = [];
  return {
    mount(root, param) {
      let selId = param || sortedEvents().find((e) => e.severity !== 'info' && e.contributing.length)?.event_id;
      const feed = h('div', { class: 'scroll', style: { maxHeight: '320px' } });
      const stats = h('div', { class: 'kv' });
      const pipeline = h('div', { class: 'col' });
      const right = h('div', { class: 'col' });
      const picker = h('select', { onchange: (e) => { selId = e.target.value; renderPipeline(); } });
      const fillPicker = () => {
        clear(picker);
        sortedEvents().filter((e) => e.category !== 'normal_activity' || e.event_id === selId).slice(0, 80).forEach((e) => picker.append(h('option', { value: e.event_id, selected: e.event_id === selId }, `${e.event_id} · ${e.severity} · ${e.category_label}`)));
        sortedEvents().filter((e) => e.category === 'normal_activity').slice(0, 10).forEach((e) => picker.append(h('option', { value: e.event_id, selected: e.event_id === selId }, `${e.event_id} · info · Normal activity`)));
      };
      const stage = (n, title, ...content) => h('section', { class: 'panel' }, h('header', {}, h('span', { class: 'tag' }, n), h('h3', {}, title)), h('div', { class: 'body' }, ...content));
      async function renderPipeline() {
        clear(pipeline); clear(right);
        let ev = selId && (state.events.get(selId) || await api.event(selId).catch(() => null));
        if (!ev) { pipeline.append(h('div', { class: 'note info' }, 'No incident yet. Go to Command and press “Test event (intrusion)”, then return here.')); right.append(bayesPanel(null)); return; }
        const pre = ev.rules.filter((r) => /^(V1|T1|K1|W:|C1)/.test(r));
        const cls = ev.rules.filter((r) => !/^(V1|T1|K1|W:|C1)/.test(r));
        const modal = [...new Set(ev.contributing.map((c) => c.sensor_type))];
        pipeline.append(
          stage('1', 'Sensor input', h('table', {}, h('thead', {}, h('tr', {}, ['Sensor', 'Type', 'Node', 'Kind', 'Value', 'Quality', 'Edge label'].map((x) => h('th', {}, x)))),
            h('tbody', {}, ev.contributing.map((c) => h('tr', {}, h('td', { class: 'mono' }, c.sensor_id), h('td', {}, c.sensor_type), h('td', { class: 'mono' }, c.node_id), h('td', {}, c.kind),
              h('td', { class: 'mono' }, `${+c.value.toFixed(2)} ${c.unit}`), h('td', { class: 'mono' }, c.quality.toFixed(2)), h('td', { class: 'mono small' }, c.details?.object_class ? `${c.details.object_class} (${c.details.class_conf})` : '—')))))),
          stage('2', 'Data validation', h('div', { class: 'mono small' }, pre.filter((r) => r.startsWith('V1')).join(' ') || 'system event — validated at ingest'),
            h('div', { class: 'small dim' }, `Flags: ${[...new Set(ev.contributing.flatMap((c) => c.flags || []))].join(', ') || 'none'}`)),
          stage('3', 'Timestamp synchronisation', h('div', { class: 'mono small' }, pre.filter((r) => r.startsWith('T1')).join(' ')), timeSyncChart(ev)),
          stage('4', 'Event correlation', h('div', { class: 'mono small' }, pre.filter((r) => r.startsWith('K1')).join(' ')), h('div', {}, `Zone ${ev.zone} · ${ev.contributing.length} observations · ${modal.length} sensor types: ${modal.join(', ')}`)),
          stage('5', 'Classification (rule trace)', rulesList(cls)),
          stage('6', 'Evidence score (confidence)', evidenceBars(ev), h('div', { class: 'small muted' }, pre.filter((r) => r.startsWith('W:')).join(' · '))),
          stage('7', 'Severity assignment & alert', h('div', { class: 'row' }, sevBadge(ev.severity), h('b', {}, ev.category_label), h('span', { class: 'dim' }, ev.classification)),
            h('div', { class: 'small dim' }, `Alert ${ev.severity === 'info' ? 'not raised (logged only)' : `raised ${fmtUTC(ev.alert_epoch)}`} · detection latency ${ev.latency.detection_ms} ms · status ${humanize(ev.verification_status)}`),
            h('a', { class: 'btn sm', href: `#/incident/${ev.event_id}` }, 'Open incident / operator actions ›')));
        right.append(bayesPanel(ev));
      }
      const rulesList = (rs) => h('ol', { class: 'small', style: { margin: 0, paddingLeft: '18px' } }, rs.map((r) => h('li', { class: 'mono' }, r)));
      const renderFeed = () => {
        clear(feed);
        for (const o of state.obsFeed.slice(-60).reverse()) {
          feed.append(h('div', { class: 'log-line' }, h('span', { class: 'muted' }, fmtUTC(o.rx).slice(11, 23)), ' ', h('span', { style: { color: o.kind === 'fault' ? SEV_COLOR.critical : '#d8b13a' } }, o.sensor_id.padEnd(7)), ` ${o.kind} ${typeof o.value === 'number' ? +o.value.toFixed(2) : ''} ${o.unit || ''} · Z${o.zone} · net ${o.network_ms} ms ${(o.flags || []).join(' ')}`));
        }
      };
      const renderStats = () => {
        const f = state.snapshot?.kpis?.fusion || {};
        clear(stats);
        for (const [k, v] of Object.entries(f)) stats.append(h('div', {}, humanize(k)), h('div', {}, v));
      };
      root.append(h('div', { class: 'page' },
        h('div', { class: 'page-head' }, h('h2', {}, 'Sensor fusion & classification engine'),
          h('p', {}, 'Transparent, deterministic rule engine — not a trained ML model. Select an incident to see exactly how its observations were validated, time-aligned, correlated, scored and classified.')),
        h('div', { class: 'row' }, h('span', { class: 'small muted' }, 'Incident'), picker),
        h('div', { style: { display: 'grid', gridTemplateColumns: '360px minmax(0,1fr) 380px', gap: '10px', alignItems: 'start' } },
          h('div', { class: 'col' },
            h('section', { class: 'panel' }, h('header', {}, h('h3', {}, 'Live observation stream')), feed),
            h('section', { class: 'panel' }, h('header', {}, h('h3', {}, 'Fusion counters (session)')), h('div', { class: 'body' }, stats)),
            h('section', { class: 'panel' }, h('header', {}, h('h3', {}, 'Rule book')), h('div', { class: 'body scroll', style: { maxHeight: '420px' } },
              h('table', {}, h('tbody', {}, RULES.map(([id, n, d]) => h('tr', {}, h('td', { class: 'mono' }, id), h('td', {}, h('b', {}, n), h('div', { class: 'small dim' }, d))))))))),
          pipeline, h('section', { class: 'panel body' }, right))));
      fillPicker(); renderPipeline(); renderFeed(); renderStats();
      unsubs.push(on('obs', renderFeed));
      unsubs.push(on('snapshot', renderStats));
      unsubs.push(on('event:new', () => fillPicker()));
      unsubs.push(on('event:update', (e) => { if (e.event_id === selId) renderPipeline(); }));
    },
    unmount() { unsubs.forEach((u) => u()); unsubs = []; },
  };
}
