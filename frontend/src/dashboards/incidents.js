// Module F — timestamp-based event engine views: live timeline + incident detail.
import { api } from '../core/api.js';
import { on, state } from '../core/store.js';
import { clear, fmtLocal, fmtMs, fmtSim, fmtUTC, h, humanize, sevBadge } from '../core/util.js';
import { actionsBar, lifecycleBar, lifecycleTable, obsTable, rulesList, statusKV } from '../components/incident.js';
import { errorToast } from '../components/ui.js';

export function incidentsView() {
  let unsubs = [];
  return {
    mount(root) {
      const f = { severity: new Set(), sensor_id: '', zone: '', category: '', status: '', q: '', scope: '' };
      const tbody = h('tbody', {});
      const count = h('span', { class: 'tag' }, '');
      let timer;
      async function load() {
        try {
          const res = await api.events({
            severity: [...f.severity].join(','), sensor_id: f.sensor_id, zone: f.zone, category: f.category, status: f.status, q: f.q,
            environment: f.scope === 'all' ? '' : state.envId, limit: 500, order: 'asc',
          });
          count.textContent = `${res.events.length} of ${res.total} (chronological, oldest first)`;
          clear(tbody);
          for (const e of res.events) {
            tbody.append(h('tr', { class: 'clickable', onclick: () => { location.hash = `#/incident/${e.event_id}`; } },
              h('td', { class: 'mono' }, e.event_id), h('td', { class: 'mono' }, fmtUTC(e.created_epoch)), h('td', { class: 'mono' }, fmtLocal(e.created_epoch)), h('td', { class: 'mono' }, fmtSim(e.sim_time)),
              h('td', { class: 'mono' }, e.sensor_id), h('td', {}, humanize(e.sensor_type)), h('td', {}, e.zone), h('td', {}, e.category_label), h('td', {}, sevBadge(e.severity)),
              h('td', { class: 'mono' }, e.confidence.toFixed(2)), h('td', { class: 'small' }, e.description),
              h('td', { class: 'small' }, humanize(e.processing_status)), h('td', { class: 'small' }, humanize(e.verification_status)),
              h('td', { class: 'small' }, humanize(e.acknowledgement_status)), h('td', { class: 'small' }, humanize(e.resolution_status))));
          }
          tbody.parentElement.parentElement.scrollTop = 1e9;
        } catch (e) { errorToast(e); }
      }
      const reload = () => { clearTimeout(timer); timer = setTimeout(load, 150); };
      const sevBox = h('span', { class: 'row' }, state.meta.severities.map((s) => h('label', { class: 'chk' }, h('input', { type: 'checkbox', onchange: (e) => { e.target.checked ? f.severity.add(s) : f.severity.delete(s); reload(); } }), sevBadge(s))));
      const sel = (key, opts, label) => h('select', { onchange: (e) => { f[key] = e.target.value; reload(); } }, h('option', { value: '' }, label), opts.map(([v, l]) => h('option', { value: v }, l)));
      root.append(h('div', { class: 'page' },
        h('div', { class: 'page-head' }, h('h2', {}, 'Incident timeline'),
          h('p', {}, 'Every event recorded by the engine, persisted in SQLite. Timestamps: UTC (storage, ms precision), host local time, and the separate simulation clock (T+). Updates automatically. Click a row for the full lifecycle.')),
        h('div', { class: 'panel body row wrap' }, h('span', { class: 'small muted' }, 'Severity'), sevBox,
          sel('sensor_id', state.env.sensors.map((s) => [s.id, s.id]), 'all sensors'),
          sel('zone', state.env.zones.map((z) => [z.id, z.name]), 'all zones'),
          sel('category', Object.entries(state.meta.categories), 'all categories'),
          sel('status', [['active', 'active (open/response)'], ['awaiting', 'awaiting verification'], ['unacknowledged', 'unacknowledged'], ['resolved', 'resolved'], ['closed', 'closed']], 'any status'),
          sel('scope', [['all', 'all sites']], 'current site'),
          h('input', { type: 'search', placeholder: 'search event ID / text', oninput: (e) => { f.q = e.target.value.trim(); reload(); } }),
          h('span', { class: 'spacer' }), count,
          h('a', { class: 'btn sm', href: '/api/export?format=csv', download: true }, 'Export CSV'),
          h('a', { class: 'btn sm', href: '/api/export?format=json', download: true }, 'Export JSON')),
        h('div', { class: 'panel scroll', style: { maxHeight: 'calc(100vh - 230px)' } },
          h('table', {}, h('thead', {}, h('tr', {}, ['Event ID', 'UTC timestamp', 'Local timestamp', 'Sim clock', 'Sensor', 'Type', 'Zone', 'Category', 'Severity', 'Evidence', 'Description', 'Processing', 'Verification', 'Ack', 'Resolution'].map((x) => h('th', {}, x)))), tbody))));
      load();
      unsubs.push(on('events', reload));
    },
    unmount() { unsubs.forEach((u) => u()); unsubs = []; },
  };
}

export function incidentPage() {
  let unsubs = [];
  return {
    async mount(root, id) {
      const body = h('div', { class: 'page' });
      root.append(body);
      async function render() {
        let ev = state.events.get(id);
        if (!ev) { try { ev = await api.event(id); } catch (e) { clear(body).append(h('div', { class: 'note' }, e.message)); return; } }
        const ack = ev.ack_epoch ? ev.ack_epoch - ev.alert_epoch : null;
        clear(body).append(
          h('div', { class: 'row wrap' }, h('a', { href: '#/incidents', class: 'btn sm' }, '‹ Timeline'), sevBadge(ev.severity), h('h2', { class: 'mono' }, ev.event_id), h('span', { class: 'dim' }, `${ev.category_label} · ${ev.classification}`),
            h('span', { class: 'spacer' }),
            h('a', { class: 'btn sm', href: `/api/events/${ev.event_id}/report?format=md`, download: true }, 'Incident report (.md)'),
            h('a', { class: 'btn sm', href: `/api/events/${ev.event_id}/report?format=json`, download: true }, 'Report (.json)'),
            h('a', { class: 'btn sm', href: `#/fusion/${ev.event_id}` }, 'Fusion analysis ›')),
          h('div', { class: 'note' }, 'Simulated incident. Evidence score is a rule-based measure of corroboration, not the probability that a real threat exists.'),
          h('section', { class: 'panel body' }, h('h3', {}, 'Lifecycle — Detection → Data processing → Classification → Alert → Operator review → Response → Resolution'), lifecycleBar(ev), actionsBar(ev)),
          h('div', { class: 'grid2' },
            h('section', { class: 'panel' }, h('header', {}, h('h3', {}, 'Record')), h('div', { class: 'body' }, h('div', {}, ev.description), h('br'), statusKV(ev))),
            h('section', { class: 'panel' }, h('header', {}, h('h3', {}, 'Timing')), h('div', { class: 'body kv' },
              h('div', {}, 'Detection latency'), h('div', {}, `${fmtMs(ev.latency.detection_ms)}  (first observation, corrected sensor time → alert)`),
              h('div', {}, 'Edge processing (mean)'), h('div', {}, fmtMs(ev.latency.edge_ms)),
              h('div', {}, 'Network (max)'), h('div', {}, fmtMs(ev.latency.network_ms)),
              h('div', {}, 'Fusion compute'), h('div', {}, `${ev.latency.fusion_ms} ms (measured)`),
              h('div', {}, 'Alert → acknowledge'), h('div', {}, ack == null ? '—' : `${ack.toFixed(3)} s`),
              h('div', {}, 'Alert → resolve'), h('div', {}, ev.resolved_epoch ? `${(ev.resolved_epoch - ev.alert_epoch).toFixed(3)} s` : '—'),
              h('div', {}, 'Alert → close'), h('div', {}, ev.closed_epoch ? `${(ev.closed_epoch - ev.alert_epoch).toFixed(3)} s` : '—'),
              h('div', {}, 'Wall clock vs sim'), h('div', {}, `${fmtUTC(ev.created_epoch)} ↔ ${fmtSim(ev.sim_time)}`)),
              h('div', { class: 'body' }, h('h4', {}, 'Rule trace'), rulesList(ev)))),
          h('section', { class: 'panel' }, h('header', {}, h('h3', {}, 'Lifecycle record (UTC storage, local display)')), h('div', { class: 'body scroll' }, lifecycleTable(ev))),
          h('section', { class: 'panel' }, h('header', {}, h('h3', {}, `Contributing observations (${ev.contributing.length}) — raw edge clock vs corrected time`)), h('div', { class: 'body scroll' }, obsTable(ev))));
      }
      await render();
      unsubs.push(on('events', (e) => { if (e?.event_id === id) render(); }));
    },
    unmount() { unsubs.forEach((u) => u()); unsubs = []; },
  };
}
