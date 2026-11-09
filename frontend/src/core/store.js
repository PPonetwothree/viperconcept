// Application state + tiny pub/sub. Views subscribe to topics and re-render
// from state; nothing animates unless state changed.

const subs = new Map();
export function on(topic, fn) {
  if (!subs.has(topic)) subs.set(topic, new Set());
  subs.get(topic).add(fn);
  return () => subs.get(topic).delete(fn);
}
export function emit(topic, data) {
  for (const fn of subs.get(topic) || []) {
    try { fn(data); } catch (e) { console.error(`[${topic}]`, e); }
  }
}

export const state = {
  meta: null,
  envs: [],
  envId: null,
  env: null,               // full layout of current environment
  devices: [],
  rationale: [],
  snapshot: null,
  sim: null,
  connected: false,
  events: new Map(),       // event_id → event payload (current environment)
  logs: [],
  obsFeed: [],             // recent observations (fusion view)
  history: {},             // sensor_id → [{t, v}]
  selected: null,          // {type:'event'|'sensor'|'node', id}
};

export function upsertEvent(ev) {
  const isNew = !state.events.has(ev.event_id);
  state.events.set(ev.event_id, ev);
  emit(isNew ? 'event:new' : 'event:update', ev);
  emit('events', ev);
}

export function sortedEvents() {
  return [...state.events.values()].sort((a, b) => b.created_epoch - a.created_epoch || (b.event_id > a.event_id ? 1 : -1));
}

export function select(type, id) {
  state.selected = id == null ? null : { type, id };
  emit('select', state.selected);
}

export function operatorName() {
  return document.getElementById('operator').value.trim();
}

export function sensorById(id) {
  return state.env?.sensors.find((s) => s.id === id);
}
export function deviceById(id) {
  return state.devices.find((d) => d.id === id);
}
