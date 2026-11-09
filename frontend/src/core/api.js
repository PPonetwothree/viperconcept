// REST client. Throws Error with the server's `detail` message on failure.

import { request } from './transport.js';

async function req(method, path, body) {
  const res = await request(method, path, body);
  const data = res.type.includes('json') ? JSON.parse(res.body) : res.body;
  if (res.status < 200 || res.status >= 300) {
    let msg = typeof data === 'object' ? data.detail : data;
    if (Array.isArray(msg)) msg = msg.map((d) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ');
    throw new Error(msg || `${res.status} ${res.statusText || ''}`.trim());
  }
  return data;
}

/** Fetch an API resource and save it as a file (works with or without a server). */
export async function downloadApi(path, filename) {
  const res = await request('GET', path);
  if (res.status !== 200) throw new Error(`download failed (HTTP ${res.status})`);
  const url = URL.createObjectURL(new Blob([res.body], { type: res.type.split(';')[0] || 'application/octet-stream' }));
  const a = Object.assign(document.createElement('a'), { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const qs = (o) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o || {})) if (v != null && v !== '') p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const api = {
  meta: () => req('GET', '/api/meta'),
  health: () => req('GET', '/api/health'),
  environments: () => req('GET', '/api/environments'),
  environment: (id) => req('GET', `/api/environments/${id}`),
  devices: () => req('GET', '/api/devices'),
  state: () => req('GET', '/api/sim/state'),
  control: (action, clear_history = false) => req('POST', '/api/sim/control', { action, clear_history }),
  speed: (speed) => req('POST', '/api/sim/speed', { speed }),
  setEnv: (environment_id) => req('POST', '/api/sim/environment', { environment_id }),
  inject: (kind, target) => req('POST', '/api/sim/inject', { kind, target }),
  events: (params) => req('GET', `/api/events${qs(params)}`),
  event: (id) => req('GET', `/api/events/${encodeURIComponent(id)}`),
  act: (id, action, body) => req('POST', `/api/events/${encodeURIComponent(id)}/${action}`, body),
  analytics: (environment) => req('GET', `/api/analytics${qs({ environment })}`),
  logs: (limit = 200) => req('GET', `/api/logs?limit=${limit}`),
  scenarios: () => req('GET', '/api/tests/scenarios'),
  runTests: (scenarios) => req('POST', '/api/tests/run', { scenarios }),
  latestTests: () => req('GET', '/api/tests/latest'),
  docs: () => req('GET', '/api/docs'),
  doc: (name) => req('GET', `/api/docs/${encodeURIComponent(name)}`),
};
