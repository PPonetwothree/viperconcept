// Module L — scenario test environment and report.
import { api } from '../core/api.js';
import { clear, download, fmtMs, h } from '../core/util.js';
import { errorToast, toast } from '../components/ui.js';

function reportMd(r) {
  const L = ['# VIPER — Scenario test report', '', `Run (UTC): ${r.run_utc}  `, `Clock: ${r.clock}  `, `Result: **${r.passed}/${r.total} passed** in ${r.duration_ms} ms`, '',
    '> Simulation-based functional tests. They verify the software logic of VIPER, not field performance of any hardware.', '',
    '| # | Scenario | Expected behaviour | Actual simulated behaviour | Event timestamp (UTC) | Processing latency | System status | Result |', '|---|---|---|---|---|---|---|---|'];
  r.results.forEach((x, i) => {
    const st = x.system_status || {};
    L.push(`| ${i + 1} | ${x.title} | ${x.expected} | ${String(x.actual).replace(/\|/g, '/')} | ${x.event_timestamp_utc || '—'} | ${x.processing_latency_ms ?? '—'} ms | ${st.online_sensors ?? '?'}/${st.total_sensors ?? '?'} sensors, ${st.nodes_online ?? '?'}/${st.nodes_total ?? '?'} nodes, ${st.power ?? '?'} | ${x.result} |`);
  });
  return L.join('\n') + '\n';
}

export function testingView() {
  return {
    async mount(root) {
      const tbody = h('tbody', {});
      const summary = h('div', { class: 'row' });
      let last = null;
      const render = (r) => {
        last = r;
        clear(tbody); clear(summary);
        if (!r?.results) { summary.append(h('span', { class: 'muted' }, 'No test run yet.')); return; }
        summary.append(h('span', { class: r.passed === r.total ? 'pass' : 'fail' }, `${r.passed}/${r.total} PASS`), h('span', { class: 'small muted' }, `${r.run_utc} · ${r.clock} · ${r.duration_ms} ms`),
          h('span', { class: 'spacer' }),
          h('button', { class: 'btn sm', onclick: () => download('viper_test_report.md', reportMd(last), 'text/markdown') }, 'Download report (.md)'),
          h('button', { class: 'btn sm', onclick: () => download('viper_test_report.json', JSON.stringify(last, null, 2), 'application/json') }, 'Download (.json)'));
        r.results.forEach((x, i) => {
          const st = x.system_status || {};
          tbody.append(h('tr', {}, h('td', { class: 'mono' }, i + 1), h('td', {}, h('b', {}, x.title), h('div', { class: 'small muted mono' }, x.id)),
            h('td', { class: 'small' }, x.expected), h('td', { class: 'small' }, x.actual, x.notes ? h('div', { class: 'muted' }, x.notes) : null),
            h('td', { class: 'mono small' }, x.event_timestamp_utc || '—', h('div', { class: 'muted' }, (x.event_ids || []).slice(0, 3).join(' '))),
            h('td', { class: 'mono small' }, x.processing_latency_ms == null ? '—' : fmtMs(x.processing_latency_ms), h('div', { class: 'muted' }, `fusion ${x.fusion_ms ?? '—'} ms`)),
            h('td', { class: 'small mono' }, st.total_sensors ? `${st.online_sensors}/${st.total_sensors} sensors · ${st.nodes_online}/${st.nodes_total} nodes · ${st.power} ${st.ups_pct}%` : '—'),
            h('td', { class: x.result === 'PASS' ? 'pass' : 'fail' }, x.result, h('div', { class: 'small muted' }, `${x.wall_runtime_ms} ms`)),
            h('td', {}, h('button', { class: 'btn sm', onclick: () => run([x.id]) }, 'Re-run'))));
        });
      };
      async function run(names) {
        toast(names ? `Running ${names.join(', ')}…` : 'Running all scenarios…');
        try {
          const r = await api.runTests(names);
          if (names && last?.results) {
            const merged = { ...last, run_utc: r.run_utc, results: last.results.map((x) => r.results.find((y) => y.id === x.id) || x) };
            merged.passed = merged.results.filter((x) => x.result === 'PASS').length;
            render(merged);
          } else render(r);
        } catch (e) { errorToast(e); }
      }
      root.append(h('div', { class: 'page' },
        h('div', { class: 'page-head' }, h('h2', {}, 'Testing & validation'),
          h('p', {}, 'Predefined scenarios run in an isolated headless runtime with a virtual (fast-forwarded) clock and fixed seeds, so results are repeatable and the live incident history is untouched. The same scenarios run in the automated pytest suite.')),
        h('div', { class: 'note info' }, 'Key property demonstrated: sensor activation ≠ threat. Normal operations, wind and wildlife must not produce high-severity alerts; genuine multi-sensor intrusions must — and even then, a human must verify before any response.'),
        h('div', { class: 'row' }, h('button', { class: 'btn primary', onclick: () => run(null) }, '▶ Run all scenarios'), summary),
        h('section', { class: 'panel scroll' }, h('table', {}, h('thead', {}, h('tr', {}, ['#', 'Scenario', 'Expected behaviour', 'Actual simulated behaviour', 'Event timestamp (UTC)', 'Processing latency', 'System status', 'Result', ''].map((x) => h('th', {}, x)))), tbody)),
        h('div', { class: 'small muted' }, 'To exercise the same scenarios on the live system, use the Command view controls (Test event, Equipment/Comm. failure, Env. anomaly, Power interruption, Animal, Wind gust).')));
      try { render(await api.latestTests()); } catch (e) { errorToast(e); }
    },
    unmount() {},
  };
}
