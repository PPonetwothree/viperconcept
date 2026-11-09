// Chooses how the frontend reaches the VIPER backend:
//  - 'server':  a running `python backend\main.py` (REST over fetch + /ws WebSocket)
//  - 'browser': no server found (static hosting such as Netlify), so the same
//               Python backend is run inside this tab with Pyodide (WebAssembly).
const PYODIDE_VERSION = '0.26.4';
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const ROOT = '/home/pyodide/viper';

let mode = null;
let bridge = null;
let sink = null;
const pending = [];

export const transportMode = () => mode;

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error(`could not load ${src}`));
    document.head.append(s);
  });
}

async function serverAvailable() {
  try {
    const res = await fetch('/api/health', { cache: 'no-store' });
    return res.ok && (res.headers.get('content-type') || '').includes('json');
  } catch {
    return false;
  }
}

async function startBrowserEngine(progress) {
  progress('Downloading Python runtime (Pyodide, first visit ≈ 10 MB)…');
  await loadScript(`${PYODIDE_URL}pyodide.js`);
  const py = await window.loadPyodide({ indexURL: PYODIDE_URL });
  progress('Loading SQLite…');
  await py.loadPackage('sqlite3');
  progress('Loading VIPER engine…');
  const res = await fetch('/py/viper.zip', { cache: 'no-cache' });
  if (!res.ok) throw new Error(`engine bundle missing (/py/viper.zip: HTTP ${res.status})`);
  py.unpackArchive(await res.arrayBuffer(), 'zip', { extractDir: ROOT });
  progress('Starting simulation…');
  py.runPython(`
import sys
sys.path.insert(0, "${ROOT}/backend")
import browser_bridge
_viper = browser_bridge.Bridge()
`);
  bridge = py.globals.get('_viper');
  const tickHz = py.runPython('import config; config.TICK_HZ');
  setInterval(() => bridge.tick(), 1000 / tickHz);
  // Deliver pushed messages asynchronously, like a socket would.
  bridge.connect((text) => {
    pending.push(text);
    if (pending.length === 1) queueMicrotask(flush);
  });
}

function flush() {
  // Messages wait in the queue until the UI subscribes (the hello arrives first).
  while (sink && pending.length) sink(pending.shift());
}

/** Decide the mode once at boot; resolves to 'server' or 'browser'. */
export async function initTransport(progress = () => {}) {
  if (mode) return mode;
  if (await serverAvailable()) {
    mode = 'server';
  } else {
    await startBrowserEngine(progress);
    mode = 'browser';
  }
  return mode;
}

/** One REST call. Resolves to {status, type, body(text)}. */
export async function request(method, path, body) {
  if (mode === 'browser') {
    return JSON.parse(bridge.handle(method, path, body ? JSON.stringify(body) : null));
  }
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: res.status, statusText: res.statusText, type: res.headers.get('content-type') || '', body: await res.text() };
}

/** Subscribe to pushed messages in browser mode (stands in for the WebSocket). */
export function subscribe(fn) {
  sink = fn;
  queueMicrotask(flush);
}
