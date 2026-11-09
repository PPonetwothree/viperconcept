// Module B — device inventory, technical profiles and selection rationale.
import { state } from '../core/store.js';
import { clear, h, inr } from '../core/util.js';

const CATS = ['Optical surveillance', 'Thermal surveillance', 'Perimeter sensors', 'Environmental sensors', 'Edge computing', 'Communication', 'Power systems'];

function profile(d) {
  const used = state.env.sensors.filter((s) => s.device === d.id).map((s) => s.id);
  const usedNodes = state.env.nodes.filter((n) => state.meta.node_models[n.model].device === d.id).map((n) => n.id);
  const row = (k, v) => [h('div', {}, k), h('div', { style: { fontFamily: 'var(--sans)' } }, v)];
  const list = (arr) => h('ul', { style: { margin: '2px 0', paddingLeft: '18px' } }, arr.map((x) => h('li', {}, x)));
  return h('div', { class: 'col' },
    h('div', { class: 'row wrap' }, h('h2', {}, d.name), h('span', { class: 'tag' }, d.category), h('span', { class: 'tag' }, d.subcategory)),
    h('div', { class: 'kv' },
      ...row('1 · Device name', d.name), ...row('2 · Manufacturer', d.manufacturer), ...row('3 · Model number', d.model), ...row('4 · Category', `${d.category} — ${d.subcategory}`)),
    h('h4', {}, '5 · Working principle'), h('div', {}, d.working_principle),
    h('h4', {}, '6 · Internal components'), list(d.internal_components),
    h('h4', {}, '7 · Technical specifications'),
    h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'Parameter'), h('th', {}, 'Value'), h('th', {}, 'Source'))),
      h('tbody', {}, d.specifications.map((s) => h('tr', {}, h('td', {}, s.param), h('td', { class: 'mono' }, s.value),
        h('td', {}, h('span', { class: `tag ${s.src === 'DS' ? 'ds' : 'est'}`, title: s.src === 'DS' ? 'Manufacturer-published figure (verify current datasheet revision)' : 'Illustrative estimate — not a manufacturer claim' }, s.src)))))),
    h('div', { class: 'kv' },
      ...row('8 · Operating voltage', d.operating_voltage), ...row('9 · Power consumption', d.power_consumption),
      ...row('10 · Communication', d.communication), ...row('11 · Operating temperature', d.operating_temperature),
      ...row('12 · Environmental limitations', d.environmental_limitations),
      ...row('13 · Approx. price (INR)', d.price_inr.high ? h('span', {}, `${inr(d.price_inr.low)} – ${inr(d.price_inr.high)} `, h('span', { class: 'tag est' }, 'EST')) : 'open source / n/a')),
    h('div', { class: 'grid2' }, h('div', {}, h('h4', {}, '14 · Advantages'), list(d.advantages)), h('div', {}, h('h4', {}, '15 · Disadvantages'), list(d.disadvantages))),
    h('h4', {}, '16 · Integration requirements'), h('div', {}, d.integration),
    h('h4', {}, '17 · Alternative components'), list(d.alternatives),
    h('h4', {}, 'Sources'), d.sources.length ? list(d.sources.map((s) => h('a', { href: s.url, target: '_blank', rel: 'noopener' }, s.label))) : h('div', { class: 'small muted' }, 'Generic / model to be selected — no single manufacturer source.'),
    h('h4', {}, `Used in current simulation (${state.env.name})`),
    h('div', { class: 'small mono' }, [...used, ...usedNodes].join(', ') || '— (catalogued alternative, not placed in this layout)'));
}

export function devicesView() {
  return {
    mount(root, param) {
      let current = state.devices.find((d) => d.id === param) || state.devices[0];
      let q = '';
      const listEl = h('div', { class: 'list' });
      const detail = h('div', { class: 'panel body scroll', style: { maxHeight: 'calc(100vh - 200px)' } });
      const show = (d) => { current = d; history.replaceState(null, '', `#/devices/${d.id}`); clear(detail).append(profile(d)); renderList(); };
      const renderList = () => {
        clear(listEl);
        for (const c of CATS) {
          const ds = state.devices.filter((d) => d.category === c && (!q || `${d.name} ${d.model} ${d.manufacturer}`.toLowerCase().includes(q)));
          if (!ds.length) continue;
          listEl.append(h('div', { class: 'group' }, c));
          ds.forEach((d) => listEl.append(h('div', { class: `item ${d.id === current.id ? 'sel' : ''}`, onclick: () => show(d) },
            h('span', { class: 'grow' }, h('div', {}, d.model), h('div', { class: 'small muted' }, `${d.manufacturer} · ${d.subcategory}`)))));
        }
      };
      const tableView = h('div', { class: 'col' }, state.rationale.map((t) => h('section', { class: 'panel' }, h('header', {}, h('h3', {}, t.title)),
        h('div', { class: 'body' }, h('table', {}, h('thead', {}, h('tr', {}, t.columns.map((c) => h('th', {}, c)))), h('tbody', {}, t.rows.map((r) => h('tr', {}, r.map((c) => h('td', {}, c)))))),
          h('div', { class: 'note info', style: { marginTop: '6px' } }, t.conclusion)))));
      const inv = h('div', { style: { display: 'grid', gridTemplateColumns: '300px 1fr', gap: '10px' } },
        h('section', { class: 'panel col', style: { gap: 0, maxHeight: 'calc(100vh - 200px)' } },
          h('header', {}, h('input', { type: 'search', placeholder: 'filter devices', style: { width: '100%' }, oninput: (e) => { q = e.target.value.toLowerCase(); renderList(); } })),
          h('div', { class: 'scroll' }, listEl)), detail);
      const cmp = h('div', { class: 'hidden' }, tableView);
      const tabs = h('div', { class: 'tabs' },
        h('button', { class: 'active', onclick: (e) => { inv.classList.remove('hidden'); cmp.classList.add('hidden'); e.target.classList.add('active'); e.target.nextSibling.classList.remove('active'); } }, `Inventory (${state.devices.length} profiles)`),
        h('button', { onclick: (e) => { cmp.classList.remove('hidden'); inv.classList.add('hidden'); e.target.classList.add('active'); e.target.previousSibling.classList.remove('active'); } }, 'Comparison & selection rationale'));
      root.append(h('div', { class: 'page' },
        h('div', { class: 'page-head' }, h('h2', {}, 'Device & hardware engineering'),
          h('p', {}, 'Technical profiles of commercial and development-grade components considered for VIPER. No hardware is connected in this demonstrator; simulated sensors reference these profiles.')),
        h('div', { class: 'note' }, h('b', {}, 'Provenance: '), h('span', { class: 'tag ds' }, 'DS'), ' = figure published by the manufacturer, compiled for this build — source documents were not re-fetched during development, so verify against the current datasheet revision before design-in. ',
          h('span', { class: 'tag est' }, 'EST'), ' = illustrative estimate. All INR prices are estimates (ex-GST, indicative ranges); obtain distributor quotations.'),
        tabs, inv, cmp));
      show(current);
    },
    unmount() {},
  };
}
