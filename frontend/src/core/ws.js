// WebSocket client with automatic reconnect.
import { emit, state } from './store.js';

let sock;
let retry = 0;

export function connect(onMessage) {
  const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`;
  sock = new WebSocket(url);
  sock.onopen = () => { retry = 0; state.connected = true; emit('connection', true); };
  sock.onclose = () => {
    state.connected = false; emit('connection', false);
    setTimeout(() => connect(onMessage), Math.min(5000, 500 * 2 ** retry++));
  };
  sock.onerror = () => sock.close();
  sock.onmessage = (m) => {
    let msg;
    try { msg = JSON.parse(m.data); } catch { return; }
    onMessage(msg);
  };
}
