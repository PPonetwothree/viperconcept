// Incident rendering + human-in-the-loop operator actions (Modules F & I).
import { api } from '../core/api.js';
import { operatorName, sensorById, state } from '../core/store.js';
import { fmtDur, fmtLocal, fmtMs, fmtSim, fmtUTC, h, humanize, sevBadge } from '../core/util.js';
import { errorToast, modal, toast } from './ui.js';

const STAGES = [
  ['Detection', ['detected']], ['Data processing', ['processed']], ['Classification', ['classified']],
  ['Alert', ['alerted']], ['Operator review', ['acknowledged', 'verified']],
  ['Response', ['response_initiated']], ['Resolution', ['resolved', 'closed']],
];

export function lifecycleBar(ev) {
  const have = new Map();
  for (const s of ev.lifecycle) if (!have.has(s.stage)) have.set(s.stage, s);
  const bar = h('div', { class: 'lifecycle' });
  let lastDone = -1;
  STAGES.forEach(([, keys], i) => { if (keys.some((k) => have.has(k))) lastDone = i; });
  const skipped = ev.category === 'normal_activity' || ['false_positive', 'verified_benign'].includes(ev.verification_status);
  STAGES.forEach(([label, keys], i) => {
    const hit = keys.map((k) => have.get(k)).filter(Boolean).pop();
    let cls = hit ? 'done' : '';
    if (!hit && i === lastDone + 1 && ev.resolution_status !== 'closed') cls = 'cur';
    if (!hit && skipped && i < lastDone) cls = 'done';
    bar.append(h('div', { class: `st ${cls}`, title: hit ? `${hit.stage} · ${hit.ts_utc} · ${hit.actor}: ${hit.note}` : (skipped && i < lastDone ? 'not required' : 'pending') },
      label, h('span', { class: 'ts' }, hit ? fmtLocal(hit.ts_epoch, false) : (skipped && i < lastDone ? 'n/a' : '—'))));
  });
  return bar;
}

function needOperator() {
  const op = operatorName();
  if (!op) {
    toast('Enter an operator name (top bar) — every action is attributed to a named person.', { err: true });
    document.getElementById('operator').focus();
    return null;
  }
  return op;
}

async function doAct(ev, action, extra = {}) {
  const operator = needOperator();
  if (!operator) return false;
  try {
    const res = await api.act(ev.event_id, action, { operator, ...extra });
    state.events.set(res.event_id, res);
    toast(`${ev.event_id}: ${humanize(action)} recorded (${operator})`);
    return true;
  } catch (e) { errorToast(e); throw e; }
}

function respondDialog(ev) {
  if (!needOperator()) return;
  const cats = state.meta.response_categories;
  let chosen = 'security_team';
  const radios = Object.entries(cats).map(([k, label]) => h('label', { class: 'chk' },
    h('input', { type: 'radio', name: 'rc', value: k, checked: k === chosen, onchange: () => { chosen = k; } }), label));
  const auth = h('input', { type: 'checkbox' });
  const note = h('textarea', { rows: 2, maxlength: 500, placeholder: 'Note (optional)' });
  modal(`Initiate response — ${ev.event_id}`, h('div', { class: 'col' },
    h('div', { class: 'note' }, 'Response categories are notifications only. VIPER performs no autonomous physical intervention; this action is recorded against your name.'),
    ...radios, note,
    h('label', { class: 'chk' }, auth, h('span', {}, `I, ${operatorName()}, authorise this response for a verified incident.`))), [
    { label: 'Authorise & initiate', cls: 'primary', onClick: () => {
      if (!auth.checked) { toast('Explicit authorisation is required.', { err: true }); return false; }
      return doAct(ev, 'respond', { category: chosen, authorized: true, note: note.value });
    } },
  ]);
}

export function actionsBar(ev) {
  const a = new Set(ev.actions || []);
  const bar = h('div', { class: 'row wrap' });
  const btn = (label, cls, enabled, fn, title) => h('button', { class: `btn sm ${cls}`, disabled: !enabled, title, onclick: fn }, label);
  bar.append(
    btn('Acknowledge', 'primary', a.has('acknowledge'), () => doAct(ev, 'acknowledge').catch(() => {}), 'Record that an operator has seen this alert'),
    btn('Verify genuine', 'ok', a.has('verify'), () => doAct(ev, 'verify', { outcome: 'verified_genuine' }).catch(() => {}), 'Operator confirms a genuine incident (enables response)'),
    btn('Benign', '', a.has('verify'), () => doAct(ev, 'verify', { outcome: 'verified_benign' }).catch(() => {}), 'Real activity, no threat'),
    btn('False positive', 'danger', a.has('false_positive'), () => doAct(ev, 'false-positive').catch(() => {}), 'No real activity — sensor/rule error. Resolves the incident.'),
    btn('Respond…', 'primary', a.has('respond'), () => respondDialog(ev), 'Select a response category (requires authorisation)'),
    btn('Resolve', 'ok', a.has('resolve'), () => doAct(ev, 'resolve').catch(() => {})),
    btn('Close', '', a.has('close'), () => doAct(ev, 'close').catch(() => {})),
  );
  return bar;
}

export function statusKV(ev) {
  const s = sensorById(ev.sensor_id);
  return h('div', { class: 'kv' },
    h('div', {}, 'Event ID'), h('div', {}, ev.event_id),
    h('div', {}, 'UTC'), h('div', {}, fmtUTC(ev.created_epoch)),
    h('div', {}, 'Local'), h('div', {}, fmtLocal(ev.created_epoch)),
    h('div', {}, 'Sim clock'), h('div', {}, fmtSim(ev.sim_time)),
    h('div', {}, 'Sensor'), h('div', {}, `${ev.sensor_id} · ${s?.type_label || humanize(ev.sensor_type)}`),
    h('div', {}, 'Zone'), h('div', {}, state.env?.zones.find((z) => z.id === ev.zone)?.name || ev.zone),
    h('div', {}, 'Category'), h('div', {}, ev.category_label),
    h('div', {}, 'Classification'), h('div', {}, ev.classification),
    h('div', {}, 'Evidence score'), h('div', { title: 'Rule-based noisy-OR evidence score. NOT the probability that a threat exists.' }, `${ev.confidence.toFixed(2)}  (not a threat probability)`),
    h('div', {}, 'Processing'), h('div', {}, humanize(ev.processing_status)),
    h('div', {}, 'Verification'), h('div', {}, humanize(ev.verification_status)),
    h('div', {}, 'Acknowledgement'), h('div', {}, humanize(ev.acknowledgement_status)),
    h('div', {}, 'Resolution'), h('div', {}, humanize(ev.resolution_status)),
    h('div', {}, 'Detection latency'), h('div', {}, fmtMs(ev.latency?.detection_ms)),
    h('div', {}, 'Ack time'), h('div', {}, ev.ack_epoch ? fmtDur(ev.ack_epoch - ev.alert_epoch) : '—'),
    ev.response?.label ? [h('div', {}, 'Response'), h('div', {}, `${ev.response.label} — authorised by ${ev.response.authorized_by}`)] : null,
  );
}

export function obsTable(ev) {
  return h('table', {},
    h('thead', {}, h('tr', {}, ['Obs', 'Sensor', 'Kind', 'Value', 'Q', 'Edge clock (UTC)', 'Corrected (UTC)', 'Edge ms', 'Net ms', 'Flags'].map((x) => h('th', {}, x)))),
    h('tbody', {}, ev.contributing.map((c) => h('tr', {},
      h('td', { class: 'mono' }, c.obs_id), h('td', { class: 'mono' }, c.sensor_id), h('td', {}, c.kind),
      h('td', { class: 'mono' }, `${+c.value.toFixed(2)} ${c.unit}`), h('td', { class: 'mono' }, c.quality.toFixed(2)),
      h('td', { class: 'mono' }, fmtUTC(c.sensor_ts).slice(11)), h('td', { class: 'mono' }, fmtUTC(c.corrected_ts || c.sensor_ts).slice(11)),
      h('td', { class: 'mono' }, c.edge_ms), h('td', { class: 'mono' }, c.network_ms),
      h('td', { class: 'mono small' }, [...(c.flags || []), c.details?.object_class ? `label:${c.details.object_class}` : null].filter(Boolean).join(' · ') || '—')))));
}

export function lifecycleTable(ev) {
  let prev = null;
  return h('table', {},
    h('thead', {}, h('tr', {}, ['Stage', 'UTC', 'Local', 'Δ from previous', 'Actor', 'Note'].map((x) => h('th', {}, x)))),
    h('tbody', {}, ev.lifecycle.map((s) => {
      const d = prev == null ? '—' : fmtDur(s.ts_epoch - prev); prev = s.ts_epoch;
      return h('tr', {}, h('td', {}, humanize(s.stage)), h('td', { class: 'mono' }, s.ts_utc), h('td', { class: 'mono' }, fmtLocal(s.ts_epoch)),
        h('td', { class: 'mono' }, d), h('td', { class: 'mono' }, s.actor), h('td', {}, s.note));
    })));
}

export function rulesList(ev, limit) {
  const r = limit ? ev.rules.slice(-limit) : ev.rules;
  return h('ol', { class: 'small', style: { margin: '4px 0', paddingLeft: '18px' } }, r.map((x) => h('li', { class: 'mono' }, x)));
}

/** Compact incident inspector for the command dashboard's right panel. */
export function incidentCompact(ev) {
  return h('div', { class: 'col' },
    h('div', { class: 'row' }, sevBadge(ev.severity), h('b', { class: 'mono' }, ev.event_id), h('span', { class: 'dim' }, ev.category_label),
      h('span', { class: 'spacer' }), h('a', { href: `#/incident/${ev.event_id}`, class: 'small' }, 'Full lifecycle ›')),
    h('div', {}, ev.description),
    lifecycleBar(ev), actionsBar(ev), statusKV(ev),
    h('h4', {}, 'Why this classification (rule trace)'), rulesList(ev, 6),
    h('h4', {}, `Contributing observations (${ev.contributing.length})`),
    h('div', { class: 'small mono dim' }, ev.contributing.slice(0, 8).map((c) =>
      h('div', {}, `${c.sensor_id} ${c.kind} ${+c.value.toFixed(2)}${c.unit ? ' ' + c.unit : ''} q${c.quality.toFixed(2)}${c.details?.object_class ? ' [' + c.details.object_class + ']' : ''}`))),
  );
}
