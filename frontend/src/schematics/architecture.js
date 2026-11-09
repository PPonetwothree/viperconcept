// Module A — interactive layered architecture with live data-flow animation.
import { animatePath } from '../animations/flow.js';
import { LAYERS } from '../data/architecture.js';
import { on, state } from '../core/store.js';
import { clear, h, s } from '../core/util.js';

const X = 30, W = 470, BH = 60, GAP = 30, TOP = 20;
const yOf = (i) => TOP + i * (BH + GAP);

export function layerPanel(L) {
  const list = (title, arr) => [h('h4', {}, title), h('ul', { style: { margin: '2px 0 8px', paddingLeft: '18px' } }, arr.map((x) => h('li', {}, x)))];
  return h('div', { class: 'col' },
    h('h2', {}, L.name), h('div', { class: 'dim' }, L.purpose),
    h('h4', {}, 'Working principle'), h('div', {}, L.principle),
    h('div', { class: 'grid2' },
      h('div', {}, ...list('Hardware', L.hardware)), h('div', {}, ...list('Software', L.software)),
      h('div', {}, ...list('Input data', L.inputs)), h('div', {}, ...list('Output data', L.outputs))),
    h('div', { class: 'kv' }, h('div', {}, 'Communication interface'), h('div', { style: { fontFamily: 'var(--sans)' } }, L.interface),
      h('div', {}, 'Power requirements'), h('div', { style: { fontFamily: 'var(--sans)' } }, L.power)),
    h('div', { class: 'grid2' }, h('div', {}, ...list('Failure scenarios', L.failures)), h('div', {}, ...list('Engineering limitations', L.limitations)),
      h('div', {}, ...list('Components', L.components)), h('div', {}, ...list('Dependencies', L.dependencies))));
}

export function architectureView() {
  let unsubs = [];
  return {
    mount(root) {
      const panel = h('div', { class: 'panel body scroll', style: { maxHeight: 'calc(100vh - 150px)' } });
      const svg = s('svg', { viewBox: `0 0 560 ${yOf(LAYERS.length) + 10}`, width: '100%', style: { maxHeight: 'calc(100vh - 150px)' } });
      const cnt = {};
      const blocks = [];
      let selected = 0;
      const show = (i) => { selected = i; blocks.forEach((b, j) => b.classList.toggle('sel', j === i)); clear(panel).append(layerPanel(LAYERS[i])); };
      LAYERS.forEach((L, i) => {
        const y = yOf(i);
        if (i > 0) {
          svg.append(s('line', { x1: X + W / 2, y1: y - GAP, x2: X + W / 2, y2: y - 4, stroke: '#7f8994', 'stroke-width': 1.3, 'marker-end': 'url(#arr)' }));
        }
        const g = s('g', { class: 'arch-block', transform: `translate(${X},${y})` },
          s('rect', { width: W, height: BH, rx: 3 }),
          s('text', { x: 12, y: 18, class: 'sub' }, `L${i + 1}`),
          s('text', { x: 40, y: 25, style: 'font-size:14px;font-weight:600' }, L.name),
          s('text', { x: 40, y: 44, class: 'sub' }, L.short));
        cnt[L.id] = s('text', { x: W - 10, y: 25, 'text-anchor': 'end', class: 'cnt' }, '');
        g.append(cnt[L.id]);
        g.addEventListener('click', () => show(i));
        blocks.push(g);
        svg.append(g);
      });
      svg.prepend(s('defs', {}, s('marker', { id: 'arr', viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' }, s('path', { d: 'M 0 0 L 10 5 L 0 10 z', fill: '#7f8994' }))));
      // side annotation lanes
      svg.append(s('text', { x: X + W + 14, y: yOf(0) + 30, class: 'struct-label', style: 'writing-mode:vertical-rl;fill:#747b85;font-size:10px' }, 'field / site'));
      svg.append(s('text', { x: X + W + 14, y: yOf(4) + 30, class: 'struct-label', style: 'writing-mode:vertical-rl;fill:#747b85;font-size:10px' }, 'command centre'));
      const pk = s('g', {});
      svg.append(pk);
      const cx = X + W / 2;
      const flow = (from, to, color) => animatePath(pk, [[cx + (Math.random() - 0.5) * 120, yOf(from) + BH / 2], [cx + (Math.random() - 0.5) * 40, yOf(to) + BH / 2]], { color, speed: 0.5 });

      const counters = () => {
        const sn = state.snapshot; if (!sn) return;
        const evs = [...state.events.values()];
        cnt.physical.textContent = `${sn.entities.length} entities · ${sn.anomalies.length} anomalies`;
        cnt.sensing.textContent = `${sn.kpis.online_sensors}/${sn.kpis.total_sensors} online`;
        cnt.edge.textContent = `${sn.counters.observations} obs · ${sn.counters.buffered} buffered`;
        cnt.network.textContent = `${sn.counters.delivered} delivered · ${sn.counters.retransmits} retx`;
        cnt.fusion.textContent = `${sn.kpis.fusion.validated} valid · ${sn.kpis.fusion.rejected} rejected`;
        cnt.classify.textContent = `${sn.kpis.fusion.events} events · ${sn.kpis.fusion.merged} merged`;
        cnt.c2.textContent = `${sn.kpis.active_incidents} active`;
        cnt.human.textContent = `${evs.filter((e) => e.ack_epoch).length} ack · ${evs.filter((e) => e.verified_epoch).length} verified`;
        cnt.response.textContent = `${evs.filter((e) => e.response?.category).length} responses · ${evs.filter((e) => e.resolution_status === 'closed' && e.severity !== 'info').length} closed`;
      };
      counters();
      unsubs.push(on('snapshot', counters));
      unsubs.push(on('obs', (o) => flow(0, 5, o.kind === 'fault' || o.kind === 'power' ? '#d9473f' : '#d8b13a')));
      unsubs.push(on('event:new', (e) => { if (e.severity !== 'info') flow(5, 6, '#e0832f'); }));
      unsubs.push(on('event:update', (e) => {
        const last = e.lifecycle[e.lifecycle.length - 1]?.stage;
        if (last === 'acknowledged' || last === 'verified') flow(6, 7, '#4caf7a');
        if (last === 'response_initiated' || last === 'resolved' || last === 'closed') flow(7, 8, '#4caf7a');
      }));
      root.append(h('div', { class: 'page' },
        h('div', { class: 'page-head' }, h('h2', {}, 'System architecture'),
          h('p', {}, 'Click a layer for its engineering specification. Packets are spawned only by real messages from the running simulation: amber = observation (sensor → classification), orange = alert to C2, green = operator action. Counters update from the engine.')),
        h('div', { style: { display: 'grid', gridTemplateColumns: 'minmax(380px, 560px) 1fr', gap: '12px', alignItems: 'start' } },
          h('div', { class: 'panel', style: { padding: '6px' } }, svg), panel)));
      show(selected);
    },
    unmount() { unsubs.forEach((u) => u()); unsubs = []; },
  };
}
