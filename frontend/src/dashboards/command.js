// Module G/H — Command & Control dashboard.
import { api } from '../core/api.js';
import { deviceById, emit, on, select, sensorById, sortedEvents, state } from '../core/store.js';
import { SEV_RANK, clear, fmtLocal, fmtMs, fmtSim, fmtUTC, h, humanize, sevBadge } from '../core/util.js';
import { sparkline } from '../components/charts.js';
import { incidentCompact } from '../components/incident.js';
import { errorToast, modal, toast } from '../components/ui.js';
import { createMap } from '../simulation/mapView.js';

const THRESH = { fence: 0.3, temperature: 55, smoke: 2.0 };

export function commandView() {
  let unsubs = [], map, els = {}, timelineFilter = { sev: '', zone: '', sensor: '', q: '' }, bottomTab = 'timeline';

  function kpiCard(id, label, sub) {
    const v = h('div', { class: 'value' }, '—');
    const sb = h('div', { class: 'sub' }, sub || '');
    const card = h('div', { class: 'kpi', title: sub }, h('div', { class: 'label' }, label), v, sb);
    els[`kpi_${id}`] = { card, v, sb };
    return card;
  }

  function controls() {
    const st = () => state.sim?.state;
    const ctl = async (a) => {
      try {
        if (a === 'reset') {
          const chk = h('input', { type: 'checkbox' });
          modal('Reset simulation', h('div', { class: 'col' }, h('div', {}, 'Clears the simulated world (entities, faults, anomalies, sim clock). Incident history is kept unless you tick the box.'),
            h('label', { class: 'chk' }, chk, 'Also permanently delete stored incident history and logs for all sites')), [
            { label: 'Reset', cls: 'danger', onClick: async () => { try { await api.control('reset', chk.checked); if (chk.checked) { state.events.clear(); emit('events'); } } catch (e) { errorToast(e); } } }]);
          return;
        }
        await api.control(a);
      } catch (e) { errorToast(e); }
    };
    const inj = async (kind, target) => {
      try {
        const r = await api.inject(kind, target);
        toast(`Injected ${humanize(kind)} (${r.ref}) at ${fmtSim(r.sim_time)} — watch the data flow`);
      } catch (e) { errorToast(e); }
    };
    const b = {
      start: h('button', { class: 'btn primary', onclick: () => ctl('start') }, '▶ Start'),
      pause: h('button', { class: 'btn', onclick: () => ctl('pause') }, '❚❚ Pause'),
      resume: h('button', { class: 'btn', onclick: () => ctl('resume') }, '▶ Resume'),
      reset: h('button', { class: 'btn', onclick: () => ctl('reset') }, '↺ Reset'),
    };
    const speeds = [1, 2, 5].map((sp) => h('button', { class: 'btn sm', 'data-sp': sp, onclick: () => api.speed(sp).catch(errorToast) }, `${sp}×`));
    els.ctl = b; els.speeds = speeds;
    const injBtns = [
      ['Test event (intrusion)', 'test_intrusion', 'Simulated person approaches and climbs the fence → fence + thermal + optical'],
      ['Equipment failure', 'equipment_failure', 'Random device reports a self-test fault'],
      ['Comm. failure', 'comm_failure', 'An edge node loses its uplink for 25 s (heartbeat watchdog, store-and-forward)'],
      ['Env. anomaly', 'env_anomaly', 'Fire (smoke + heat) or liquid leak near an asset'],
      ['Power interruption', 'power_interruption', 'Mains loss for 90 s (sim); UPS carries the load'],
      ['Animal', 'animal', 'Wildlife brushes the fence — tests false-alarm suppression'],
      ['Wind gust', 'wind_gust', 'Fence vibration from wind — tests wind compensation'],
    ].map(([l, k, t]) => h('button', { class: `btn sm ${k === 'test_intrusion' ? 'primary' : ''}`, title: t, onclick: () => inj(k) }, l));
    els.inj = injBtns;
    const toggles = ['coverage', 'labels', 'wiring', 'packets'].map((k) => {
      const bt = h('button', { class: `btn sm ${map?.opts[k] !== false ? 'on' : ''}`, onclick: () => { map.setOption(k, !map.opts[k]); bt.classList.toggle('on', map.opts[k]); } }, k);
      if (k === 'wiring') bt.classList.remove('on');
      return bt;
    });
    return h('div', { class: 'controls' }, b.start, b.pause, b.resume, b.reset, h('span', { class: 'sep' }), h('span', { class: 'small muted' }, 'Speed'),
      h('span', { class: 'btn-group' }, ...speeds), h('span', { class: 'sep' }), ...injBtns, h('span', { class: 'spacer' }), h('span', { class: 'btn-group' }, ...toggles));
  }

  function refreshControls() {
    const st = state.sim?.state;
    if (!els.ctl) return;
    els.ctl.start.disabled = st === 'running';
    els.ctl.pause.disabled = st !== 'running';
    els.ctl.resume.disabled = st !== 'paused';
    els.speeds.forEach((b) => b.classList.toggle('on', +b.dataset.sp === state.sim?.speed));
    els.inj.forEach((b) => { b.disabled = st !== 'running'; });
  }

  // ------------------------------------------------------------- left panel
  function renderLeft() {
    const snap = state.snapshot, env = state.env;
    if (!snap || !env) return;
    // assets & zones
    const active = sortedEvents().filter((e) => e.severity !== 'info' && ['open', 'response_initiated'].includes(e.resolution_status));
    clear(els.zones);
    els.zones.append(h('div', { class: 'small dim', style: { padding: '4px 9px' } }, `${env.name} — ${env.subtitle}`));
    for (const z of env.zones) {
      const zs = active.filter((e) => e.zone === z.id);
      const top = zs.reduce((m, e) => (SEV_RANK[e.severity] > SEV_RANK[m] ? e.severity : m), 'info');
      const dot = { info: 'ok', low: 'warn', medium: 'warn', high: 'sus', critical: 'crit' }[top];
      const n = env.sensors.filter((s) => s.zone === z.id).length;
      els.zones.append(h('div', { class: 'item', title: z.name, onclick: () => zs[0] && select('event', zs[0].event_id) },
        h('span', { class: `dot ${dot}` }), h('span', { class: 'grow' }, z.name), h('span', { class: 'small muted mono' }, `${n} s · ${zs.length} inc`)));
    }
    // sensors grouped by type
    clear(els.sensors);
    const groups = {};
    env.sensors.forEach((s) => (groups[s.type_label] ||= []).push(s));
    for (const [label, list] of Object.entries(groups)) {
      els.sensors.append(h('div', { class: 'group' }, `${label} (${list.length})`));
      for (const s of list) {
        const st = snap.sensors[s.id] || {};
        const dot = { online: 'ok', fault: 'crit', unreachable: '', unpowered: '' }[st.status] ?? '';
        els.sensors.append(h('div', { class: `item ${state.selected?.id === s.id ? 'sel' : ''}`, onclick: () => select('sensor', s.id) },
          h('span', { class: `dot ${dot} ${st.active ? 'pulse' : ''}`, style: st.active ? { background: 'var(--warn)' } : {} }),
          h('span', { class: 'mono', style: { width: '52px' } }, s.id), h('span', { class: 'small muted' }, `Z${s.zone}`),
          h('span', { class: 'grow mono small dim', style: { textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, st.reading?.text ?? '—')));
      }
    }
    // device status (edge nodes + power)
    clear(els.devices);
    for (const n of env.nodes) {
      const ns = snap.nodes[n.id] || {};
      const dot = { online: 'ok', link_down: 'crit', unpowered: '' }[ns.status] ?? '';
      els.devices.append(h('div', { class: `item ${state.selected?.id === n.id ? 'sel' : ''}`, onclick: () => select('node', n.id), title: `${state.meta.node_models[n.model].label} via ${state.meta.links[n.link].label}` },
        h('span', { class: `dot ${dot}` }), h('span', { class: 'mono', style: { width: '52px' } }, n.id),
        h('span', { class: 'small dim grow' }, `${state.meta.node_models[n.model].label} · ${n.link}`),
        h('span', { class: 'mono small' }, ns.status === 'online' ? `${ns.latency_ms} ms` : humanize(ns.status)), ns.queue ? h('span', { class: 'tag' }, `buf ${ns.queue}`) : null));
    }
    const p = snap.power;
    els.devices.append(h('div', { class: 'item', onclick: () => { location.hash = '#/schematics/power'; } },
      h('span', { class: `dot ${p.mains ? 'ok' : 'warn pulse'}` }), h('span', { class: 'mono', style: { width: '52px' } }, 'UPS-1'),
      h('span', { class: 'small dim grow' }, p.mains ? 'Mains supply' : 'ON BATTERY (mains lost)'), h('span', { class: 'mono small' }, `${p.ups_pct.toFixed(0)} %`)));
  }

  // ------------------------------------------------------------ right panel
  function renderIncidents() {
    const list = sortedEvents().filter((e) => e.severity !== 'info' && e.resolution_status !== 'closed');
    els.incCount.textContent = `${list.length}`;
    clear(els.incList);
    if (!list.length) els.incList.append(h('div', { class: 'small muted', style: { padding: '8px' } }, 'No open incidents. Normal activity is logged in the timeline (info).'));
    list.sort((a, b) => SEV_RANK[b.severity] - SEV_RANK[a.severity] || b.created_epoch - a.created_epoch);
    for (const e of list.slice(0, 40)) {
      els.incList.append(h('div', { class: `inc-card sev-b-${e.severity} ${state.selected?.id === e.event_id ? 'sel' : ''}`, onclick: () => select('event', e.event_id) },
        h('div', { class: 't' }, sevBadge(e.severity), h('b', { class: 'mono' }, e.event_id), h('span', { class: 'spacer' }), h('span', { class: 'mono small muted' }, fmtLocal(e.created_epoch, false))),
        h('div', { class: 'd' }, `${e.category_label} · Zone ${e.zone} · ${humanize(e.verification_status)} · ${humanize(e.resolution_status)}`)));
    }
  }

  function renderInspector() {
    const sel = state.selected;
    clear(els.insp);
    if (!sel) {
      els.inspTitle.textContent = 'Inspector';
      els.insp.append(h('div', { class: 'small muted' }, 'Select an incident, a sensor on the map, or an edge node to inspect it. Try: click a thermal camera (TH-xx), then “Test event”.'));
      return;
    }
    if (sel.type === 'event') {
      const ev = state.events.get(sel.id);
      els.inspTitle.textContent = 'Incident';
      if (ev) els.insp.append(incidentCompact(ev));
      return;
    }
    if (sel.type === 'node') return renderNode(sel.id);
    renderSensor(sel.id);
  }

  function renderSensor(id) {
    const sn = sensorById(id);
    if (!sn) return;
    const st = state.snapshot?.sensors?.[id] || {};
    const dev = deviceById(sn.device);
    const node = state.env.nodes.find((n) => n.id === sn.node);
    const ns = state.snapshot?.nodes?.[sn.node] || {};
    els.inspTitle.textContent = 'Sensor';
    const related = sortedEvents().filter((e) => e.contributing?.some((c) => c.sensor_id === id)).slice(0, 5);
    els.insp.append(h('div', { class: 'col' },
      h('div', { class: 'row' }, h('b', { class: 'mono' }, sn.id), h('span', { class: 'dim' }, sn.type_label), h('span', { class: 'spacer' }), h('span', { class: `tag` }, st.status || '—')),
      h('div', { class: 'note info small' }, 'Simulated device — readings are synthetic, produced by SimulatedAdapter. A hardware adapter would replace it behind the same interface.'),
      h('h4', {}, 'Live simulated reading'),
      h('div', { class: 'mono', style: { fontSize: '16px' } }, st.reading?.text ?? '—'),
      sparkline(state.history[id] || [], { threshold: THRESH[sn.type] }),
      h('h4', {}, 'Device & engineering'),
      h('div', { class: 'kv' },
        h('div', {}, 'Device'), h('div', {}, dev ? `${dev.manufacturer} ${dev.model}` : sn.device),
        h('div', {}, 'Principle'), h('div', { style: { fontFamily: 'var(--sans)' } }, dev?.working_principle || '—'),
        h('div', {}, 'Zone'), h('div', {}, sn.zone),
        h('div', {}, 'Position'), h('div', {}, `(${sn.x.toFixed(0)}, ${sn.y.toFixed(0)}) m${sn.range ? ` · range ${sn.range} m` : ''}${sn.fov && sn.fov < 360 ? ` · FOV ${sn.fov}° @ ${sn.dir}°` : ''}`),
        h('div', {}, 'Physical link'), h('div', {}, sn.bus),
        h('div', {}, 'Edge node'), h('div', {}, `${node.id} — ${state.meta.node_models[node.model].label}`),
        h('div', {}, 'Uplink'), h('div', {}, `${state.meta.links[node.link].label} · ${ns.status} · ${ns.latency_ms ?? '—'} ms · skew ${ns.skew_ms} ms`)),
      h('div', { class: 'row wrap' },
        h('a', { class: 'btn sm', href: `#/devices/${sn.device}` }, 'Device profile ›'),
        h('a', { class: 'btn sm', href: `#/schematics/sensor?sensor=${sn.id}` }, 'Wiring schematic ›'),
        h('button', { class: 'btn sm danger', disabled: state.sim?.state !== 'running' || st.status !== 'online', onclick: () => api.inject('equipment_failure', sn.id).then(() => toast(`Fault injected on ${sn.id}`)).catch(errorToast) }, 'Inject fault on this sensor'),
        ['A', 'B', 'D'].includes(sn.zone) && ['fence', 'thermal', 'optical'].includes(sn.type)
          ? h('button', { class: 'btn sm primary', disabled: state.sim?.state !== 'running', onclick: () => api.inject('test_intrusion', sn.zone).then(() => toast(`Simulated intrusion toward zone ${sn.zone} — watch ${sn.id}`)).catch(errorToast) }, `Test intrusion in zone ${sn.zone}`) : null),
      h('h4', {}, 'Recent incidents involving this sensor'),
      related.length ? h('div', { class: 'list' }, related.map((e) => h('div', { class: 'item', onclick: () => select('event', e.event_id) }, sevBadge(e.severity), h('span', { class: 'mono' }, e.event_id), h('span', { class: 'small dim' }, e.category_label)))) : h('div', { class: 'small muted' }, 'none')));
  }

  function renderNode(id) {
    const n = state.env.nodes.find((x) => x.id === id);
    const ns = state.snapshot?.nodes?.[id] || {};
    const dev = deviceById(state.meta.node_models[n.model].device);
    els.inspTitle.textContent = 'Edge node';
    const sensors = state.env.sensors.filter((s) => s.node === id);
    els.insp.append(h('div', { class: 'col' },
      h('div', { class: 'row' }, h('b', { class: 'mono' }, id), h('span', { class: 'dim' }, state.meta.node_models[n.model].label), h('span', { class: 'spacer' }), h('span', { class: 'tag' }, ns.status)),
      h('div', { class: 'kv' },
        h('div', {}, 'Device'), h('div', {}, dev ? `${dev.manufacturer} ${dev.model}` : '—'),
        h('div', {}, 'Uplink'), h('div', {}, state.meta.links[n.link].label),
        h('div', {}, 'Last latency'), h('div', {}, `${ns.latency_ms} ms`),
        h('div', {}, 'Clock skew (sim)'), h('div', {}, `${ns.skew_ms} ms (estimated ${state.snapshot?.clock_offsets_ms?.[id] ?? '—'} ms by fusion)`),
        h('div', {}, 'Store-and-forward'), h('div', {}, `${ns.queue} buffered`),
        h('div', {}, 'Messages sent'), h('div', {}, ns.tx)),
      h('div', { class: 'row wrap' },
        h('button', { class: 'btn sm danger', disabled: state.sim?.state !== 'running' || ns.status !== 'online', onclick: () => api.inject('comm_failure', id).then(() => toast(`Uplink of ${id} cut for 25 s`)).catch(errorToast) }, 'Cut uplink (comm failure)'),
        h('a', { class: 'btn sm', href: '#/schematics/edge' }, 'Edge schematic ›'), dev ? h('a', { class: 'btn sm', href: `#/devices/${dev.id}` }, 'Device profile ›') : null),
      h('h4', {}, `Attached sensors (${sensors.length})`),
      h('div', { class: 'list' }, sensors.map((s) => h('div', { class: 'item', onclick: () => select('sensor', s.id) }, h('span', { class: 'mono' }, s.id), h('span', { class: 'small dim grow' }, s.bus), h('span', { class: 'small mono' }, state.snapshot?.sensors?.[s.id]?.status))))));
  }

  // ----------------------------------------------------------- bottom panel
  function renderBottom() {
    clear(els.bottomBody);
    if (bottomTab === 'timeline') return renderTimeline();
    if (bottomTab === 'logs') {
      for (const l of state.logs.slice(-200).reverse()) {
        els.bottomBody.append(h('div', { class: 'log-line' }, h('span', { class: 'muted' }, fmtUTC(l.ts_epoch).slice(11)), ' ', h('span', { class: `lv-${l.level}` }, l.level.toUpperCase().padEnd(5)), ' ', h('span', { class: 'dim' }, `[${l.source}]`), ' ', l.message));
      }
      return;
    }
    if (bottomTab === 'comms') {
      const snap = state.snapshot;
      els.bottomBody.append(h('table', {}, h('thead', {}, h('tr', {}, ['Node', 'Model', 'Uplink', 'Status', 'Last latency', 'Sim. latency range', 'Loss (sim)', 'Clock skew', 'Estimated offset', 'Buffered', 'Tx'].map((x) => h('th', {}, x)))),
        h('tbody', {}, state.env.nodes.map((n) => {
          const ns = snap.nodes[n.id]; const L = state.meta.links[n.link];
          return h('tr', {}, h('td', { class: 'mono' }, n.id), h('td', {}, state.meta.node_models[n.model].label), h('td', {}, L.label), h('td', {}, humanize(ns.status)),
            h('td', { class: 'mono' }, `${ns.latency_ms} ms`), h('td', { class: 'mono' }, `${L.latency[0]}–${L.latency[1]} ms`), h('td', { class: 'mono' }, `${(L.loss * 100).toFixed(1)} %`),
            h('td', { class: 'mono' }, `${ns.skew_ms} ms`), h('td', { class: 'mono' }, `${snap.clock_offsets_ms?.[n.id] ?? '—'} ms`), h('td', { class: 'mono' }, ns.queue), h('td', { class: 'mono' }, ns.tx));
        }))));
      return;
    }
    const k = state.snapshot?.kpis || {}, c = state.snapshot?.counters || {}, f = k.fusion || {};
    els.bottomBody.append(h('div', { class: 'grid3', style: { padding: '8px' } },
      h('div', { class: 'kv' }, ...['observations', 'delivered', 'buffered', 'dropped', 'retransmits', 'heartbeats'].flatMap((x) => [h('div', {}, `pipeline.${x}`), h('div', {}, c[x] ?? 0)])),
      h('div', { class: 'kv' }, ...['received', 'validated', 'rejected', 'late', 'correlated_sets', 'events', 'merged', 'suppressed_normal'].flatMap((x) => [h('div', {}, `fusion.${x}`), h('div', {}, f[x] ?? 0)])),
      h('div', { class: 'kv' }, h('div', {}, 'engine tick (mean)'), h('div', {}, `${k.tick_ms} ms`), h('div', {}, 'snapshot rate'), h('div', {}, `${state.meta.config.tick_hz} Hz`),
        h('div', {}, 'correlation window'), h('div', {}, `${state.meta.config.correlation_window_s} s`), h('div', {}, 'heartbeat timeout'), h('div', {}, `${state.meta.config.heartbeat_timeout_s} s`),
        h('div', {}, 'WS connected'), h('div', {}, String(state.connected)), h('div', {}, 'note'), h('div', { style: { fontFamily: 'var(--sans)' } }, 'Measured on this machine; simulated link latencies are model parameters, not field measurements.'))));
  }

  function renderTimeline() {
    const f = timelineFilter;
    const evs = sortedEvents().filter((e) => (!f.sev || e.severity === f.sev) && (!f.zone || e.zone === f.zone) && (!f.sensor || e.sensor_id === f.sensor || e.contributing?.some((c) => c.sensor_id === f.sensor)) && (!f.q || e.event_id.toLowerCase().includes(f.q.toLowerCase())));
    els.bottomBody.append(h('table', {}, h('thead', {}, h('tr', {}, ['Time (local, ms)', 'UTC', 'Sim', 'Event ID', 'Severity', 'Category', 'Sensor', 'Zone', 'Evidence', 'Status', 'Description'].map((x) => h('th', {}, x)))),
      h('tbody', {}, evs.slice(0, 150).map((e) => h('tr', { class: 'clickable', onclick: () => select('event', e.event_id) },
        h('td', { class: 'mono' }, fmtLocal(e.created_epoch, false)), h('td', { class: 'mono' }, fmtUTC(e.created_epoch).slice(11)), h('td', { class: 'mono' }, fmtSim(e.sim_time)),
        h('td', { class: 'mono' }, e.event_id), h('td', {}, sevBadge(e.severity)), h('td', {}, e.category_label), h('td', { class: 'mono' }, e.sensor_id), h('td', {}, e.zone),
        h('td', { class: 'mono' }, e.confidence.toFixed(2)), h('td', { class: 'small' }, `${humanize(e.acknowledgement_status)} · ${humanize(e.resolution_status)}`), h('td', { class: 'small dim' }, e.description))))));
  }

  function filterBar() {
    const sevSel = h('select', { onchange: (e) => { timelineFilter.sev = e.target.value; renderBottom(); } }, h('option', { value: '' }, 'all severities'), ...state.meta.severities.map((x) => h('option', { value: x }, x)));
    const zoneSel = h('select', { onchange: (e) => { timelineFilter.zone = e.target.value; renderBottom(); } }, h('option', { value: '' }, 'all zones'), ...state.env.zones.map((z) => h('option', { value: z.id }, `Zone ${z.id}`)));
    const senSel = h('select', { onchange: (e) => { timelineFilter.sensor = e.target.value; renderBottom(); } }, h('option', { value: '' }, 'all sensors'), ...state.env.sensors.map((s) => h('option', { value: s.id }, s.id)));
    const q = h('input', { type: 'search', placeholder: 'search event ID', size: 16, oninput: (e) => { timelineFilter.q = e.target.value; renderBottom(); } });
    return h('span', { class: 'row', id: 'tl-filters' }, sevSel, zoneSel, senSel, q);
  }

  function renderKPIs() {
    const k = state.snapshot?.kpis;
    if (!k) return;
    const set = (id, v, cls, sub) => { const e = els[`kpi_${id}`]; e.v.textContent = v; e.card.className = `kpi ${cls || ''}`; if (sub != null) e.sb.textContent = sub; };
    set('total', k.total_sensors, '', `${state.env.nodes.length} edge nodes`);
    set('online', k.online_sensors, k.online_sensors === k.total_sensors ? 'ok' : 'warn');
    set('offline', k.offline_sensors, k.offline_sensors ? 'crit' : 'ok');
    set('active', k.active_incidents, k.active_incidents ? 'warn' : 'ok');
    set('awaiting', k.awaiting_verification, k.awaiting_verification ? 'warn' : 'ok');
    set('det', k.mean_detection_latency_ms == null ? '—' : fmtMs(k.mean_detection_latency_ms), '', 'first obs → alert, this session');
    set('ack', k.mean_ack_time_s == null ? '—' : `${k.mean_ack_time_s.toFixed(1)} s`, '', 'alert → acknowledge, this session');
    set('avail', `${k.availability_pct.toFixed(2)} %`, k.availability_pct >= 99 ? 'ok' : 'warn', 'time-weighted sensor uptime');
  }

  function renderMapState() {
    const snap = state.snapshot;
    if (!snap) return;
    const c = snap.conditions;
    els.mapState.innerHTML = `${state.sim.state.toUpperCase()} · ${state.sim.speed}× · ${fmtSim(state.sim.sim_time)}<br>wind ${c.wind_ms} m/s${c.gust ? ' (gust)' : ''} · light ${c.light} · ${c.ambient_c} °C<br>power: ${snap.power.source}`;
  }

  return {
    mount(root) {
      const kpis = h('div', { class: 'kpis' },
        kpiCard('total', 'Total sensors'), kpiCard('online', 'Online sensors', 'reporting & reachable'), kpiCard('offline', 'Offline sensors', 'fault / unreachable / unpowered'),
        kpiCard('active', 'Active incidents', 'open or response initiated'), kpiCard('awaiting', 'Awaiting verification', 'need operator review'),
        kpiCard('det', 'Mean detection latency'), kpiCard('ack', 'Mean ack. time'), kpiCard('avail', 'System availability'));
      els.zones = h('div', { class: 'list' }); els.sensors = h('div', { class: 'list' }); els.devices = h('div', { class: 'list' });
      const left = h('div', { class: 'left' },
        h('section', { class: 'panel', style: { flex: '0 0 auto' } }, h('header', {}, h('h3', {}, 'Asset overview · zones')), els.zones),
        h('section', { class: 'panel col', style: { flex: '1 1 0', gap: 0 } }, h('header', {}, h('h3', {}, 'Sensor inventory')), h('div', { class: 'scroll grow' }, els.sensors)),
        h('section', { class: 'panel', style: { flex: '0 0 auto' } }, h('header', {}, h('h3', {}, 'Device status · edge & power')), els.devices));
      const mapHost = h('div', { class: 'map-host' });
      els.mapState = h('div', { class: 'map-state' });
      mapHost.append(h('div', { class: 'watermark' }, 'SIMULATED ENVIRONMENT — NOT LIVE OBSERVATIONS'), els.mapState);
      const legend = h('div', { class: 'map-legend' },
        ...[['#4caf7a', 'Normal'], ['#d8b13a', 'Warning'], ['#e0832f', 'Suspicious'], ['#d9473f', 'Critical']].map(([c, l]) => h('span', {}, h('span', { class: 'dot', style: { background: c } }), l)),
        h('span', {}, '▲ camera/thermal'), h('span', {}, '◆ fence'), h('span', {}, '● PIR/MW'), h('span', {}, '■ edge node'),
        h('span', {}, h('span', { class: 'dot', style: { background: '#cfd6de', border: '1px solid #4caf7a' } }), 'authorised'),
        h('span', {}, h('span', { class: 'dot', style: { background: '#e0832f' } }), 'unauthorised (sim)'),
        h('span', {}, h('span', { class: 'dot', style: { background: '#a58a5a' } }), 'animal'),
        h('span', {}, h('span', { class: 'dot', style: { background: '#d8b13a' } }), 'observation packet'));
      map = createMap(mapHost, { onSensor: (id) => select('sensor', id), onEvent: (id) => select('event', id), onNode: (id) => select('node', id) });
      const center = h('section', { class: 'panel mapwrap' }, controls(), mapHost, legend);
      els.incList = h('div', { class: 'scroll', style: { maxHeight: '220px' } });
      els.incCount = h('span', { class: 'tag' }, '0');
      els.insp = h('div', { class: 'body scroll grow' });
      els.inspTitle = h('h3', {}, 'Inspector');
      const right = h('div', { class: 'right' },
        h('section', { class: 'panel', style: { flex: '0 0 auto' } }, h('header', {}, h('h3', {}, 'Active incidents'), els.incCount, h('span', { class: 'spacer' }), h('a', { href: '#/incidents', class: 'small' }, 'All ›')), els.incList),
        h('section', { class: 'panel col', style: { flex: '1 1 0', gap: 0 } }, h('header', {}, els.inspTitle, h('span', { class: 'spacer' }), h('button', { class: 'btn sm', onclick: () => select(null) }, '×')), els.insp));
      els.bottomBody = h('div', { class: 'tab-body' });
      const tabs = h('div', { class: 'tabs' });
      for (const [k, l] of [['timeline', 'Event timeline'], ['logs', 'System logs'], ['comms', 'Communication status'], ['perf', 'Performance']]) {
        tabs.append(h('button', { class: k === bottomTab ? 'active' : '', onclick: (e) => { bottomTab = k; tabs.querySelectorAll('button').forEach((b) => b.classList.remove('active')); e.target.classList.add('active'); filters.style.display = k === 'timeline' ? '' : 'none'; renderBottom(); } }, l));
      }
      const filters = filterBar();
      tabs.append(h('span', { class: 'spacer' }), filters);
      const bottom = h('section', { class: 'panel bottom' }, tabs, els.bottomBody);
      root.append(h('div', { class: 'cmd' }, kpis, left, center, right, bottom));

      map.build(state.env);
      const full = () => { renderKPIs(); renderLeft(); renderIncidents(); renderInspector(); renderBottom(); refreshControls(); map.update(state.snapshot); map.setEvents(sortedEvents(), state.selected?.type === 'event' ? state.selected.id : null); renderMapState(); };
      full();
      let tick = 0;
      unsubs.push(on('snapshot', () => {
        tick++;
        map.update(state.snapshot); renderKPIs(); renderMapState(); refreshControls();
        if (tick % 2 === 0) { renderLeft(); if (state.selected && state.selected.type !== 'event') renderInspector(); }
        if (tick % 5 === 0 && bottomTab !== 'timeline') renderBottom();
      }));
      unsubs.push(on('events', () => { renderIncidents(); renderLeft(); map.setEvents(sortedEvents(), state.selected?.type === 'event' ? state.selected.id : null); if (bottomTab === 'timeline') renderBottom(); if (state.selected?.type === 'event') renderInspector(); }));
      unsubs.push(on('select', (sel) => { renderInspector(); renderIncidents(); map.setSelectedSensor(sel?.type === 'sensor' ? sel.id : null); map.setEvents(sortedEvents(), sel?.type === 'event' ? sel.id : null); }));
      unsubs.push(on('obs', (o) => map.flowObservation(o)));
      unsubs.push(on('log', () => { if (bottomTab === 'logs') renderBottom(); }));
      unsubs.push(on('sim', refreshControls));
    },
    unmount() { unsubs.forEach((u) => u()); unsubs = []; },
  };
}
