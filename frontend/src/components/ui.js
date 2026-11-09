// Toasts and modal dialogs.
import { h } from '../core/util.js';

export function toast(text, { sev, err, onclick, ttl = 6000 } = {}) {
  const host = document.getElementById('toasts');
  const t = h('div', { class: `toast ${sev ? `sev-t-${sev}` : ''} ${err ? 'err' : ''}` }, text);
  t.addEventListener('click', () => { onclick?.(); t.remove(); });
  host.prepend(t);
  while (host.children.length > 5) host.lastChild.remove();
  setTimeout(() => t.remove(), ttl);
}

export function errorToast(e) {
  toast(`⚠ ${e.message || e}`, { err: true, ttl: 8000 });
}

/** Modal dialog. actions: [{label, cls, onClick}] — onClick may return false (or a
 * rejected promise) to keep the dialog open. */
export function modal(title, body, actions) {
  const bg = h('div', { class: 'modal-bg' });
  const close = () => bg.remove();
  const footer = h('footer', {});
  for (const a of actions) {
    footer.append(h('button', {
      class: `btn ${a.cls || ''}`,
      onclick: async () => {
        try {
          const r = await a.onClick?.();
          if (r !== false) close();
        } catch (e) { /* caller reported */ }
      },
    }, a.label));
  }
  footer.prepend(h('button', { class: 'btn', onclick: close }, 'Cancel'));
  bg.append(h('div', { class: 'modal' }, h('header', {}, title), h('div', { class: 'body' }, body), footer));
  bg.addEventListener('click', (e) => { if (e.target === bg) close(); });
  document.body.append(bg);
  return close;
}
