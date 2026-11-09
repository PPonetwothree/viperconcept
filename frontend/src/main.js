// VIPER frontend entry: bootstraps state, WebSocket, router and top bar.
import { api } from './core/api.js';
import { emit, on, select, state, upsertEvent } from './core/store.js';
import { fmtLocal, fmtSim, fmtUTC, h } from './core/util.js';
import { connect } from './core/ws.js';
import { errorToast, toast } from './components/ui.js';
import { commandView } from './dashboards/command.js';
import { architectureView } from './schematics/architecture.js';
import { schematicsView } from './schematics/schematics.js';
import { devicesView } from './devices/devices.js';
import { fusionView } from './dashboards/fusion.js';
import { incidentsView, incidentPage } from './dashboards/incidents.js';
import { analyticsView } from './dashboards/analytics.js';
import { testingView } from './dashboards/testing.js';
import { docsView } from './dashboards/docs.js';

const ROUTES = [
  ['command', 'Command', commandView],
  ['architecture', 'Architecture', architectureView],
  ['schematics', 'Schematics', schematicsView],
  ['devices', 'Devices', devicesView],
  ['fusion', 'Fusion engine', fusionView],
  ['incidents', 'Incidents', incidentsView],
  ['analytics', 'Analytics', analyticsView],
  ['testing', 'Testing', testingView],
  ['docs', 'Docs', docsView],
];

let current = null;
let snapAt = performance.now();

async function loadEnvironment(envId) {
  state.envId = envId;
  state.env = await api.environment(envId);
  state.events.clear();
  state.history = {};
  const { events } = await api.events({ environment: envId, limit: 1000 });
  events.forEach((e) => state.events.set(e.event_id, e));
  document.getElementById('env-select').value = envId;
}

function onMessage(msg) {
  switch (msg.type) {
    case 'hello':
    case 'snapshot': {
      const snap = msg.snapshot;
      if (snap.sim.environment !== state.envId) return;     // stale snapshot during switch
      state.snapshot = snap;
      const prev = state.sim?.state + state.sim?.speed;
      state.sim = snap.sim;
      snapAt = performance.now();
      const t = snap.sim.sim_time;
      for (const [id, st] of Object.entries(snap.sensors)) {
        const arr = (state.history[id] ||= []);
        arr.push({ t, v: typeof st.reading?.value === 'number' ? st.reading.value : null });
        if (arr.length > 150) arr.shift();
      }
      emit('snapshot', snap);
      if (prev !== state.sim.state + state.sim.speed) emit('sim', state.sim);
      break;
    }
    case 'event':
      if (msg.event.environment !== state.envId) return;
      upsertEvent(msg.event);
      if (msg.event.severity !== 'info') {
        toast(`${msg.event.severity.toUpperCase()} · ${msg.event.event_id} · ${msg.event.category_label} — ${msg.event.description}`,
          { sev: msg.event.severity, onclick: () => { location.hash = '#/command'; select('event', msg.event.event_id); } });
      }
      break;
    case 'event_update':
      if (msg.event.environment !== state.envId) return;
      upsertEvent(msg.event);
      break;
    case 'observation':
      state.obsFeed.push({ ...msg.obs, rx: Date.now() / 1000 });
      if (state.obsFeed.length > 300) state.obsFeed.shift();
      emit('obs', msg.obs);
      break;
    case 'log':
      state.logs.push(msg.log);
      if (state.logs.length > 500) state.logs.shift();
      emit('log', msg.log);
      break;
    case 'environment':
      loadEnvironment(msg.environment).then(() => { emit('env', state.env); route(); }).catch(errorToast);
      break;
  }
}

function route() {
  const hash = location.hash.replace(/^#\/?/, '') || 'command';
  const [name, ...rest] = hash.split('/');
  const param = decodeURIComponent(rest.join('/'));
  document.querySelectorAll('#nav a').forEach((a) => a.classList.toggle('active', a.dataset.r === (name === 'incident' ? 'incidents' : name)));
  current?.unmount?.();
  const app = document.getElementById('app');
  app.innerHTML = '';
  const factory = name === 'incident' ? incidentPage : (ROUTES.find((r) => r[0] === name) || ROUTES[0])[2];
  current = factory();
  const view = h('div', { class: 'view' });
  app.append(view);
  current.mount(view, param);
}

function tickClock() {
  const now = Date.now() / 1000;
  document.getElementById('clock-local').textContent = fmtLocal(now, false).slice(0, 12);
  document.getElementById('clock-utc').textContent = `UTC ${fmtUTC(now).slice(11, 23)}`;
  if (state.sim) {
    const run = state.sim.state === 'running';
    const sim = state.sim.sim_time + (run ? ((performance.now() - snapAt) / 1000) * state.sim.speed : 0);
    document.getElementById('clock-sim').textContent = fmtSim(sim);
    document.getElementById('clock-sim-sub').textContent = `sim · ${state.sim.state} · ${state.sim.speed}×`;
  }
  const st = document.getElementById('sys-status');
  const k = state.snapshot?.kpis;
  const ok = state.connected && k && k.offline_sensors === 0;
  st.innerHTML = '';
  st.append(h('span', { class: `dot ${!state.connected ? 'crit' : ok ? 'ok' : 'warn'}` }),
    h('span', {}, !state.connected ? 'backend disconnected' : ok ? 'all systems nominal' : `${k?.offline_sensors ?? '?'} sensor(s) offline`));
}

async function boot() {
  const nav = document.getElementById('nav');
  for (const [id, label] of ROUTES) nav.append(h('a', { href: `#/${id}`, 'data-r': id }, label));
  const op = document.getElementById('operator');
  try { op.value = localStorage.getItem('viper.operator') || ''; } catch { /* storage blocked */ }
  op.addEventListener('change', () => { try { localStorage.setItem('viper.operator', op.value.trim()); } catch { /* ignore */ } });

  try {
    const [meta, envs, devices, snap] = await Promise.all([api.meta(), api.environments(), api.devices(), api.state()]);
    state.meta = meta; state.envs = envs; state.devices = devices.devices; state.rationale = devices.selection_rationale;
    const sel = document.getElementById('env-select');
    for (const e of envs) sel.append(h('option', { value: e.id }, e.name));
    sel.addEventListener('change', () => api.setEnv(sel.value).catch(errorToast));
    await loadEnvironment(snap.sim.environment);
    state.snapshot = snap; state.sim = snap.sim;
    state.logs = (await api.logs(150)).reverse();
  } catch (e) {
    document.getElementById('app').append(h('div', { class: 'page' }, h('div', { class: 'note' }, `Backend not reachable: ${e.message}. Start it with: python backend\\main.py`)));
    return;
  }
  connect(onMessage);
  on('connection', () => tickClock());
  window.addEventListener('hashchange', route);
  route();
  setInterval(tickClock, 100);
}

boot();
