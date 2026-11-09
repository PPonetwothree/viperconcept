// Module J — analytics computed by the backend from recorded (simulated) events.
import { api } from '../core/api.js';
import { state } from '../core/store.js';
import { SEV_COLOR, clear, fmtDur, h, humanize, pct } from '../core/util.js';
import { barChart, hBars, histogram } from '../components/charts.js';
import { errorToast } from '../components/ui.js';

const METRICS = [
  ['Events per hour', 'N_h = |{ e : t_e ∈ [h, h+1) }|', 'Count of all recorded events (incl. normal activity) per local hour.', 'Same; report separately per site and per category; compare day/night.'],
  ['False-positive rate', 'FPR_op = N_FP / (N_genuine + N_FP + N_benign)', 'Share of operator-verified alerts that were marked false positive. Unverified alerts are excluded.', 'Every alert must be verified (camera/patrol); audit a sample. Distinguish FP (no real activity) from benign (real, harmless).'],
  ['Detection latency', 'L_det = t_alert − t_first_obs (corrected)', 'From the first contributing observation (sensor time, clock-corrected) to alert creation; includes edge, network and correlation window.', 'Staged red-team walk-tests with a GPS/NTP-synchronised reference clock (e.g. video with time overlay) at each fence segment, day and night.'],
  ['Acknowledgement latency', 'L_ack = t_ack − t_alert', 'Time from alert to operator acknowledgement.', 'Logged automatically; analyse by shift, alert load and severity.'],
  ['Resolution time', 'T_res = t_resolved − t_alert', 'Time from alert to resolution (response completed or FP/benign closed).', 'Logged automatically; exclude incidents awaiting external parties or report them separately.'],
  ['Sensor availability', 'A_s = Σ t_online / Σ t_observed', 'Time-weighted fraction during which the sensor was healthy, powered and reachable (this session).', 'Heartbeats + health telemetry over ≥ 30 days; planned maintenance reported separately.'],
  ['System availability', 'A_sys = Σ_s Σ t_online,s / Σ_s Σ t_observed,s', 'Mean of sensor availability weighted by time.', 'Also define end-to-end availability: the C2 receiving events within SLA.'],
];

export function analyticsView() {
  let timer;
  return {
    mount(root) {
      let scope = 'env';
      const body = h('div', { class: 'col' });
      async function load() {
        let a;
        try { a = await api.analytics(scope === 'env' ? state.envId : undefined); } catch (e) { errorToast(e); return; }
        const card = (label, v, sub) => h('div', { class: 'kpi' }, h('div', { class: 'label' }, label), h('div', { class: 'value' }, v), h('div', { class: 'sub' }, sub || ''));
        const sev = state.meta.severities;
        const catRows = Object.entries(a.by_category).map(([k, v]) => ({ label: state.meta.categories[k] || k, value: v }));
        const lastHour = Array.from({ length: 24 }, (_, i) => { const d = new Date(Date.now() - (23 - i) * 3600e3); return `${String(d.getHours()).padStart(2, '0')}h`; });
        const avail = [...a.sensor_availability].sort((x, y) => x.availability_pct - y.availability_pct);
        clear(body).append(
          h('div', { class: 'kpis' },
            card('Events recorded', a.total_events, `${a.total_incidents} non-info incidents`),
            card('False-positive rate', a.false_positive_rate == null ? '—' : pct(a.false_positive_rate), `${a.false_positive_count} FP of ${a.verified_count} verified`),
            card('Detection latency (mean)', a.detection_latency_ms.mean == null ? '—' : `${(a.detection_latency_ms.mean / 1000).toFixed(2)} s`, `p95 ${a.detection_latency_ms.p95 == null ? '—' : (a.detection_latency_ms.p95 / 1000).toFixed(2) + ' s'} · n=${a.detection_latency_ms.n}`),
            card('Ack latency (mean)', fmtDur(a.ack_latency_s.mean), `p95 ${fmtDur(a.ack_latency_s.p95)} · n=${a.ack_latency_s.n}`),
            card('Resolution time (mean)', fmtDur(a.resolution_time_s.mean), `p95 ${fmtDur(a.resolution_time_s.p95)} · n=${a.resolution_time_s.n}`),
            card('Sensor availability', `${a.session_availability_pct.toFixed(2)} %`, 'this session, time-weighted'),
            card('Observations', a.pipeline_counters.observations, `${a.fusion_stats.rejected} rejected · ${a.fusion_stats.late} late`),
            card('Normal records suppressed', a.fusion_stats.suppressed_normal, 'rate limiting (R1)')),
          h('div', { class: 'note' }, `Source: ${a.total_events} simulated event records (${a.environment === 'all' ? 'all sites' : state.env.name}) generated ${a.generated_utc}. These are simulation outputs — not validated performance results.`),
          h('div', { class: 'grid2' },
            h('section', { class: 'panel' }, h('header', {}, h('h3', {}, 'Events per hour (last 24 h, local)')), h('div', { class: 'body' }, barChart({ labels: lastHour, values: a.events_per_hour, labelEvery: 3 }))),
            h('section', { class: 'panel' }, h('header', {}, h('h3', {}, 'Events per minute (last 60 min)')), h('div', { class: 'body' }, barChart({ labels: a.events_per_minute.map((_, i) => `-${59 - i}`), values: a.events_per_minute, labelEvery: 10 }))),
            h('section', { class: 'panel' }, h('header', {}, h('h3', {}, 'Events by category')), h('div', { class: 'body' }, catRows.length ? hBars(catRows) : h('div', { class: 'muted small' }, 'no data'))),
            h('section', { class: 'panel' }, h('header', {}, h('h3', {}, 'Events by severity')), h('div', { class: 'body' }, barChart({ labels: sev, values: sev.map((s) => a.by_severity[s]), colors: sev.map((s) => SEV_COLOR[s]) }))),
            h('section', { class: 'panel' }, h('header', {}, h('h3', {}, 'Detection latency distribution (ms)')), h('div', { class: 'body' }, histogram(a.detection_latency_samples_ms || [], { unit: 'ms' }),
              h('div', { class: 'kv small' }, ...['mean', 'p50', 'p95', 'max'].flatMap((k) => [h('div', {}, k), h('div', {}, a.detection_latency_ms[k] == null ? '—' : `${a.detection_latency_ms[k]} ms`)])))),
            h('section', { class: 'panel' }, h('header', {}, h('h3', {}, 'Latency & resolution statistics')), h('div', { class: 'body' },
              h('table', {}, h('thead', {}, h('tr', {}, ['Metric', 'n', 'mean', 'p50', 'p95', 'max'].map((x) => h('th', {}, x)))),
                h('tbody', {}, [['Detection (ms)', a.detection_latency_ms], ['Acknowledgement (s)', a.ack_latency_s], ['Resolution (s)', a.resolution_time_s]].map(([n, st]) =>
                  h('tr', {}, h('td', {}, n), ...['n', 'mean', 'p50', 'p95', 'max'].map((k) => h('td', { class: 'mono' }, st[k] ?? '—')))))),
              h('h4', { style: { marginTop: '8px' } }, 'By category'),
              h('table', {}, h('thead', {}, h('tr', {}, ['Category', 'Count', 'False positives', 'Mean ack (s)', 'Mean evidence'].map((x) => h('th', {}, x)))),
                h('tbody', {}, a.by_category_table.map((r) => h('tr', {}, h('td', {}, state.meta.categories[r.category]), h('td', { class: 'mono' }, r.count), h('td', { class: 'mono' }, r.false_positive), h('td', { class: 'mono' }, r.mean_ack_s ?? '—'), h('td', { class: 'mono' }, r.mean_conf)))))))),
          h('section', { class: 'panel' }, h('header', {}, h('h3', {}, 'Sensor availability (this session)')), h('div', { class: 'body' },
            hBars(avail.slice(0, 40).map((x) => ({ label: `${x.sensor_id} (${x.type})`, value: x.availability_pct, color: x.availability_pct >= 99 ? '#4caf7a' : x.availability_pct >= 95 ? '#d8b13a' : '#d9473f', text: `${x.availability_pct.toFixed(2)} %` })), { max: 100 }))),
          h('section', { class: 'panel' }, h('header', {}, h('h3', {}, 'Metric definitions & real-world pilot measurement')), h('div', { class: 'body' },
            h('table', {}, h('thead', {}, h('tr', {}, ['Metric', 'Definition', 'In this demonstrator', 'How to measure in a pilot'].map((x) => h('th', {}, x)))),
              h('tbody', {}, METRICS.map(([n, f, d, p]) => h('tr', {}, h('td', {}, h('b', {}, n)), h('td', {}, h('span', { class: 'formula' }, f)), h('td', { class: 'small' }, d), h('td', { class: 'small' }, p))))),
            h('div', { class: 'note info', style: { marginTop: '8px' } }, 'A pilot should additionally measure probability of detection (P_d) per fence segment from scheduled walk/climb tests, and nuisance alarm rate (NAR) per km per day, with weather logged. No such validated figures exist for VIPER yet.'))));
      }
      const scopeSel = h('select', { onchange: (e) => { scope = e.target.value; load(); } }, h('option', { value: 'env' }, 'Current site'), h('option', { value: 'all' }, 'All sites'));
      root.append(h('div', { class: 'page' }, h('div', { class: 'page-head' }, h('h2', {}, 'Analytics & performance'),
        h('p', {}, 'All charts are computed from the recorded event history in SQLite (refreshes every 5 s).'), scopeSel, h('button', { class: 'btn sm', onclick: load }, 'Refresh')), body));
      load();
      timer = setInterval(load, 5000);
    },
    unmount() { clearInterval(timer); },
  };
}
