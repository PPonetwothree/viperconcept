// REST client. Throws Error with the server's `detail` message on failure.

async function req(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const ct = res.headers.get('content-type') || '';
  const data = ct.includes('json') ? await res.json() : await res.text();
  if (!res.ok) {
    let msg = typeof data === 'object' ? data.detail : data;
    if (Array.isArray(msg)) msg = msg.map((d) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ');
    throw new Error(msg || `${res.status} ${res.statusText}`);
  }
  return data;
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
