// Module C — interactive engineering schematics (SVG). Every component and
// every connection carries an identifier and an explanation of its purpose.
// Layouts are conceptual and deliberately non-site-specific.
import { on, sensorById, sortedEvents, state } from '../core/store.js';
import { clear, esc, fmtLocal, h, hideTip, humanize, s, showTip } from '../core/util.js';

const n = (id, x, y, w, h_, label, sub, tip, extra = {}) => ({ id, x, y, w, h: h_, label, sub, tip, ...extra });
const g = (id, x, y, w, h_, label) => ({ id, x, y, w, h: h_, label, group: true });
const e = (from, to, label, tip, opts = {}) => ({ from, to, label, tip, ...opts });

const SCHEMATICS = {
  architecture: {
    title: 'S1 — Complete VIPER architecture',
    desc: 'Relationship between all hardware and software modules, from field devices to operators.',
    w: 1100, h: 610,
    nodes: [
      g('G1', 15, 30, 365, 565, 'Field site (per perimeter side / gate / env. cluster)'), g('G2', 395, 30, 175, 565, 'Network'),
      g('G3', 585, 30, 305, 565, 'Command-centre server'), g('G4', 905, 30, 180, 565, 'Operators'),
      n('cams', 30, 60, 160, 44, 'Optical / PTZ / low-light', 'CAM·PTZ·LLC', 'IP cameras streaming H.265 over RTSP; ONVIF for control and events.'),
      n('therm', 30, 125, 160, 44, 'Thermal cameras', 'TH-xx', 'Uncooled LWIR cameras for darkness/long range; analytics on edge.'),
      n('fence', 30, 190, 160, 44, 'Fence vibration nodes', 'FV-xx', 'MEMS accelerometer nodes per fence segment, Modbus RTU over RS-485.'),
      n('det', 30, 255, 160, 44, 'PIR · microwave · contacts', 'PIR·MW·MC', 'Point detectors and gate contacts — supervised dry-contact inputs.'),
      n('radar', 30, 320, 160, 44, 'Perimeter radar', 'RAD-xx', 'Range/velocity tracks of approaching objects outside the fence.'),
      n('env', 30, 400, 160, 44, 'Environmental sensors', 'TMP·SMK·WL', 'Temperature/humidity, smoke relay, leak cable.'),
      n('pwr', 30, 520, 160, 44, 'Power: mains · UPS · PV', 'UPS-1 · PV-1', 'Mains with UPS for cabinets/C2; solar + battery for remote env nodes.'),
      n('jet', 215, 110, 150, 70, 'Jetson Orin Nano ×4', 'EN-N / E / S / W', 'GPU edge nodes: DNN detection + tracking on camera streams, fence alarm aggregation.'),
      n('rpi', 215, 250, 150, 50, 'Raspberry Pi 5', 'EN-G (gate)', 'Gate node: dry contacts, access-control feed, gate camera analytics.'),
      n('esp', 215, 400, 150, 50, 'ESP32 + SX1276', 'EN-ENV', 'Low-power environmental node, LoRaWAN uplink.'),
      n('sw', 410, 110, 145, 50, 'PoE switch / fibre', 'NET-SW', 'Powers cameras and carries data; fibre uplink for distances > 100 m.'),
      n('wl', 410, 220, 145, 50, 'Wi-Fi PtP / 4G LTE', 'NET-WL', 'Wireless uplinks where trenching is impractical; VPN-protected.'),
      n('mq', 410, 320, 145, 50, 'MQTT broker', 'QoS 1 · TLS', 'Publish/subscribe transport for observations and heartbeats (simulated by DeliveryQueue).'),
      n('lora', 410, 400, 145, 50, 'LoRaWAN gateway', 'IN865', 'Receives env node uplinks; network server forwards to MQTT.'),
      n('ing', 600, 60, 275, 44, 'Ingest & validation', 'fusion.ingest() V1–V2', 'Rejects unknown/unhealthy sensors, implausible values, future timestamps.'),
      n('sync', 600, 125, 275, 44, 'Timestamp synchronisation', 'heartbeat offset T1', 'Corrects each node\'s clock skew using NTP-style offset estimates from heartbeats.'),
      n('cor', 600, 190, 275, 44, 'Correlation', 'zone × 6 s window K1', 'Groups observations by zone and time; merges follow-ups into open incidents.'),
      n('cls', 600, 255, 275, 44, 'Rule-based classifier', 'classify() R1–R7 E1–E4', 'Deterministic rules → category, evidence score, severity, rule trace.'),
      n('db', 600, 340, 275, 44, 'SQLite event store', 'events · lifecycle · logs', 'Persistent UTC-timestamped incident history.'),
      n('api', 600, 420, 275, 44, 'REST + WebSocket API', 'FastAPI · /api · /ws', 'History/actions over REST; live push of snapshots, events, logs.'),
      n('lc', 600, 500, 275, 44, 'Lifecycle state machine', 'lifecycle.py', 'Validates every operator transition; rejects out-of-order actions.'),
      n('ui', 920, 160, 150, 60, 'Operator console', 'this web UI', 'Map, alerts, inspector, timeline, analytics.'),
      n('resp', 920, 330, 150, 50, 'Response workflow', 'human-authorised', 'Notification categories only; no autonomous physical action.'),
      n('rep', 920, 470, 150, 50, 'Reports & exports', 'MD · JSON · CSV', 'Incident reports and history export.'),
    ],
    edges: [
      e('cams', 'jet', 'RTSP/PoE', 'Video streams to GPU analytics; PoE supplies camera power from the UPS-backed switch.'),
      e('therm', 'jet', 'RTSP/PoE', 'Thermal streams for detection in darkness.'),
      e('fence', 'jet', 'RS-485', 'Isolated Modbus RTU bus collects per-segment vibration alarms.'),
      e('radar', 'jet', 'Ethernet', 'Radar tracks (JSON) for approach detection.', { fromSide: 'r', toSide: 'b' }),
      e('det', 'rpi', 'GPIO (EOL)', 'Supervised dry contacts: open/short/cut distinguishable.'),
      e('env', 'esp', 'I²C / ADC', 'Environmental measurements sampled by the MCU.'),
      e('pwr', 'esp', 'PV + battery', 'Solar-assisted supply for remote env node.', { fromSide: 'r', toSide: 'b' }),
      e('jet', 'sw', 'GbE', 'Edge node uplink carrying observations only (not raw video).'),
      e('rpi', 'wl', 'Ethernet/Wi-Fi', 'Gate node uplink.'),
      e('esp', 'lora', 'LoRa RF', 'Compact env telemetry over LoRaWAN (high latency, low power).'),
      e('sw', 'mq', 'MQTT/TLS', 'Observations + heartbeats published to the broker.', { fromSide: 'b', toSide: 't' }),
      e('lora', 'mq', 'NS → MQTT', 'LoRaWAN network server republishes to MQTT.', { fromSide: 't', toSide: 'b' }),
      e('wl', 'mq', 'MQTT', 'Wireless uplinks terminate at the broker.', { fromSide: 'b', toSide: 't' }),
      e('mq', 'ing', 'subscribe', 'Fusion service subscribes to all observation topics.', { fromSide: 'r', toSide: 'l' }),
      e('ing', 'sync', '', 'Validated observations are time-corrected.'),
      e('sync', 'cor', '', 'Corrected timestamps enable cross-node correlation.'),
      e('cor', 'cls', '', 'Correlated sets are classified.'),
      e('cls', 'db', 'Event', 'Every event persisted before broadcast.'),
      e('db', 'api', '', 'API reads history, filters, exports.'),
      e('api', 'ui', 'WS push', 'Live snapshots/events to the console (< 250 ms on LAN).', { fromSide: 'r', toSide: 'l' }),
      e('ui', 'lc', 'actions', 'Operator actions (ack/verify/respond/resolve/close) via REST.', { fromSide: 'b', toSide: 'r' }),
      e('lc', 'db', '', 'Transitions recorded with UTC timestamps and actor.', { fromSide: 't', toSide: 'b' }),
      e('ui', 'resp', 'authorise', 'Response only after verification and explicit authorisation.'),
      e('api', 'rep', 'report', 'Report generator reads the full lifecycle.', { fromSide: 'r', toSide: 'l' }),
      e('pwr', 'sw', 'UPS AC', 'UPS-backed supply for switches, edge nodes and C2.', { fromSide: 'r', toSide: 'b', dashed: true }),
    ],
  },
  sensor: {
    title: 'S2 — Sensor integration',
    desc: 'How representative sensors connect electrically and logically to edge devices. Select a sensor on the Command map to highlight its path.',
    w: 1100, h: 610,
    nodes: [
      g('GA', 15, 30, 520, 300, 'Perimeter side cabinet (EN-x)'), g('GB', 15, 345, 520, 250, 'Gate cabinet (EN-G)'), g('GC', 555, 30, 530, 300, 'Environmental node (EN-ENV)'),
      n('th', 30, 60, 140, 44, 'Thermal camera', 'TH-xx · PoE PD', 'LWIR camera; RTSP H.264/H.265 stream + ONVIF analytics events.', { types: ['thermal'] }),
      n('cam', 30, 120, 140, 44, 'Optical camera', 'CAM-xx · PoE PD', '4 MP IP camera; RTSP stream.', { types: ['optical'] }),
      n('rad', 30, 180, 140, 44, 'Radar', 'RAD-xx', 'mmWave/perimeter radar — tracks over Ethernet.', { types: ['radar'] }),
      n('fv', 30, 250, 140, 54, 'Fence nodes FV-xx', 'ADXL355 + MCU', 'Accelerometer + MCU per segment computing g-RMS; Modbus RTU slave.', { types: ['fence'] }),
      n('poe', 210, 90, 120, 60, 'PoE switch', '802.3af/at · VLAN', 'Supplies 48 V PoE to cameras; VLAN isolates camera traffic.'),
      n('iso', 210, 250, 120, 54, 'Isolated RS-485', 'ADM2587E · 120 Ω', 'Galvanic isolation (2.5 kV) protects node from fence-line ground potential/lightning; bus terminated 120 Ω both ends.'),
      n('jet', 380, 140, 140, 90, 'Jetson Orin Nano', 'GbE · USB-UART · NVMe', 'Decodes streams, runs detection/tracking, polls RS-485 bus, emits observations.', { types: ['optical', 'thermal', 'fence', 'radar'] }),
      n('pir', 30, 375, 140, 40, 'PIR detector', 'PIR-xx · 12 V', 'Pyroelectric motion detector; relay output.', { types: ['pir'] }),
      n('mw', 30, 425, 140, 40, 'Microwave detector', 'MW-xx · 12 V', 'Doppler detector; relay output.', { types: ['microwave'] }),
      n('mc', 30, 475, 140, 40, 'Gate contact', 'MC-xx · reed', 'Reed contact with EOL resistor (supervised loop).', { types: ['contact'] }),
      n('acr', 30, 535, 140, 44, 'Access-control reader', 'OSDP / Wiegand', 'Badge credential events — authorisation context for fusion rule R1.'),
      n('opto', 210, 420, 120, 60, 'Opto-isolated input board', '12 V → 3.3 V', 'Optocouplers translate 12 V detector relays to Pi GPIO levels and isolate field wiring.'),
      n('pi', 380, 440, 140, 70, 'Raspberry Pi 5', 'GPIO · Ethernet', 'Debounces inputs, measures EOL loop state, correlates badge events with gate opening.', { types: ['pir', 'microwave', 'contact', 'lowlight', 'ptz'] }),
      n('tmp', 570, 60, 140, 44, 'Temp/RH sensor', 'SHT31 · I²C 0x44', 'Factory-calibrated digital T/RH sensor.', { types: ['temperature'] }),
      n('smk', 570, 120, 140, 44, 'Smoke detector relay', 'certified detector', 'VIPER reads the certified detector\'s alarm relay — it does not replace the fire panel.', { types: ['smoke'] }),
      n('wl', 570, 180, 140, 44, 'Leak cable controller', 'relay / analog', 'Conductive (or hydrocarbon) sensing cable controller.', { types: ['leak'] }),
      n('esp', 760, 100, 140, 90, 'ESP32-WROOM-32E', 'I²C · GPIO · ADC · SPI', 'Samples sensors, applies thresholds, deep-sleeps between samples.', { types: ['temperature', 'smoke', 'leak'] }),
      n('rfm', 940, 120, 130, 50, 'RFM95W (SX1276)', 'LoRa IN865', 'LoRa radio over SPI; LoRaWAN uplink to gateway.'),
      n('pv', 760, 240, 140, 50, 'MPPT + battery', 'PV-1 · 12 V', 'Solar-assisted supply with LDO to 3.3 V.'),
    ],
    edges: [
      e('th', 'poe', 'Cat6 PoE', 'Single cable for power (PoE) and data (RTSP/ONVIF).'),
      e('cam', 'poe', 'Cat6 PoE', 'Same as thermal; per-camera VLAN membership.'),
      e('rad', 'poe', 'Ethernet', 'Radar track output (JSON/TCP).'),
      e('poe', 'jet', 'GbE trunk', 'Aggregated camera/radar traffic to the edge node.'),
      e('fv', 'iso', 'RS-485 A/B', 'Twisted pair, daisy-chained segment nodes, terminated at both ends.'),
      e('iso', 'jet', 'USB-UART', 'Isolated transceiver to node UART (Modbus RTU master).'),
      e('pir', 'opto', '12 V relay', 'Normally-closed alarm relay contact.'),
      e('mw', 'opto', '12 V relay', 'Normally-closed alarm relay contact.'),
      e('mc', 'opto', 'EOL loop', 'End-of-line resistor lets the node tell open, closed, cut and short apart.'),
      e('opto', 'pi', 'GPIO 3.3 V', 'Isolated logic levels to Pi GPIO with software debounce.'),
      e('acr', 'pi', 'OSDP RS-485', 'Credential events for authorisation context.', { fromSide: 'r', toSide: 'b' }),
      e('tmp', 'esp', 'I²C', 'SDA/SCL with pull-ups; short cable run.'),
      e('smk', 'esp', 'GPIO', 'Dry-contact alarm input.'),
      e('wl', 'esp', 'GPIO/ADC', 'Relay or analog leak signal.'),
      e('esp', 'rfm', 'SPI', 'Radio control and payload.'),
      e('pv', 'esp', '3.3 V', 'Regulated supply from battery.', { fromSide: 't', toSide: 'b' }),
    ],
  },
  edge: {
    title: 'S3 — Edge computing node (Jetson Orin Nano, perimeter side)',
    desc: 'Sensor inputs, processing pipeline, local storage, network interface and power supply of a perimeter edge node.',
    w: 1100, h: 560,
    nodes: [
      g('IN', 15, 30, 200, 515, 'Sensor inputs'), g('PU', 235, 30, 520, 360, 'Processing unit (Jetson Orin Nano module)'), g('PS', 235, 405, 520, 140, 'Power supply'), g('NI', 775, 30, 310, 360, 'Network & time'),
      n('i1', 30, 70, 170, 44, 'Camera streams', 'RTSP over GbE (×2–6)', 'H.264/H.265 streams from optical/thermal cameras.'),
      n('i2', 30, 140, 170, 44, 'Fence bus', 'RS-485 via USB-UART', 'Modbus RTU polling of FV nodes every 100 ms.'),
      n('i3', 30, 210, 170, 44, 'Radar tracks', 'Ethernet JSON', 'Track list with range/bearing/velocity.'),
      n('i4', 30, 280, 170, 44, 'Cabinet sensors', 'INA219 · door tamper', 'Rail voltage/current, cabinet door switch.'),
      n('dec', 250, 70, 140, 44, 'HW video decode', 'NVDEC', 'Hardware decoding keeps CPU free.'),
      n('dnn', 410, 70, 160, 44, 'DNN detection', 'TensorRT (GPU)', 'Object detection (person/vehicle/animal) per frame — simulated in this build.'),
      n('trk', 590, 70, 150, 44, 'Multi-object tracker', 'IoU / Kalman', 'Assigns track IDs so one person = one observation per 30 s, not one per frame.'),
      n('thr', 250, 160, 140, 44, 'Threshold & debounce', 'fence 0.3 g, 6 s', 'Turns continuous signals into discrete alarms.'),
      n('geo', 410, 160, 160, 44, 'Ground-plane mapping', 'pixel → map (m)', 'Calibrated camera homography/radar geometry places objects into zones.'),
      n('obs', 590, 160, 150, 44, 'Observation builder', 'JSON + edge timestamp', 'Packs sensor, kind, value, quality, object class, position, edge clock time.'),
      n('sf', 410, 260, 160, 54, 'Store-and-forward queue', 'NVMe · max 500', 'Buffers observations while uplink is down; flushes on restore with original timestamps.'),
      n('hb', 590, 260, 150, 54, 'Heartbeat / watchdog', '2 s interval', 'Liveness + clock sample; missing for 7 s ⇒ communication failure at C2.'),
      n('st', 250, 260, 140, 54, 'Local storage', 'NVMe SSD', 'OS, models, queue, short video ring buffer for verification.'),
      n('nic', 790, 70, 140, 50, 'GbE interface', '802.1Q VLAN', 'Uplink to switch/fibre.'),
      n('mq', 790, 150, 140, 50, 'MQTT client', 'QoS 1 · TLS 1.3', 'Publishes observations and heartbeats; mutual-TLS certificates.'),
      n('ntp', 790, 240, 140, 50, 'NTP / PTP client', 'clock discipline', 'Keeps node clock within ms; residual skew corrected centrally.'),
      n('fw', 950, 150, 120, 50, 'Host firewall', 'outbound only', 'No inbound services except management VPN.'),
      n('dc', 250, 445, 150, 50, 'DC input 19 V', 'from 24 V bus via DC-DC', 'Isolated DC-DC from cabinet bus.'),
      n('ups', 430, 445, 150, 50, 'Cabinet UPS / battery', '12 V 7 Ah ×2', 'Rides through mains loss; monitored.'),
      n('mon', 600, 445, 140, 50, 'Power monitor', 'INA219 → I²C', 'Reports rail health with heartbeats.'),
    ],
    edges: [
      e('i1', 'dec', 'RTSP', 'Compressed video.'), e('dec', 'dnn', 'frames', 'Decoded frames to GPU.'), e('dnn', 'trk', 'detections', 'Boxes + class + confidence.'),
      e('trk', 'geo', 'tracks', 'Track positions to map coordinates.', { fromSide: 'b', toSide: 'r' }), e('geo', 'obs', 'zone, pos', 'Located detections.'),
      e('i2', 'thr', 'g-RMS', 'Fence vibration samples.'), e('i3', 'geo', 'tracks', 'Radar tracks to map.', { fromSide: 'r', toSide: 'b' }),
      e('thr', 'obs', 'alarm', 'Threshold crossings.', { fromSide: 't', toSide: 't', via: 140 }),
      e('obs', 'sf', 'if link down', 'Queue when uplink unavailable.', { fromSide: 'b', toSide: 't' }),
      e('obs', 'mq', 'publish', 'Normal path.', { fromSide: 'r', toSide: 'l' }), e('sf', 'mq', 'flush', 'On restore.', { fromSide: 'r', toSide: 'l' }),
      e('hb', 'mq', 'heartbeat', 'Liveness + clock sample.', { fromSide: 'r', toSide: 'l' }), e('mq', 'nic', '', 'TCP/TLS over Ethernet.', { fromSide: 't', toSide: 'b' }),
      e('ntp', 'hb', 'time', 'Disciplined clock for stamping.', { fromSide: 'l', toSide: 'r' }), e('st', 'sf', '', 'Queue persisted on NVMe.'),
      e('i4', 'mon', 'I²C', 'Cabinet telemetry.', { fromSide: 'b', toSide: 'l' }), e('ups', 'dc', '12 V', 'Battery-backed bus.', { fromSide: 'l', toSide: 'r' }),
      e('mon', 'hb', 'health', 'Power status included in heartbeat.', { fromSide: 't', toSide: 'b' }), e('mq', 'fw', '', 'Outbound connections only.'),
    ],
  },
  comms: {
    title: 'S4 — Communication architecture (live)',
    desc: 'How observations reach the central platform. Link colour and latency are live from the running simulation.',
    w: 1100, h: 560, dynamic: 'comms',
  },
  power: {
    title: 'S5 — Power architecture (live)',
    desc: 'Mains, conversion, UPS, batteries, solar and monitoring. Source, battery % and load update from the simulation.',
    w: 1100, h: 560,
    nodes: [
      n('mains', 30, 70, 150, 54, 'Mains incomer', '415 V 3φ (sim)', 'Utility supply. Simulated failure via “Power interruption”.', { live: 'mains' }),
      n('mcb', 220, 70, 140, 54, 'Distribution board', 'MCB / RCD / SPD', 'Protection: breakers, residual-current devices, surge protection on outgoing feeders.'),
      n('ups', 400, 60, 170, 74, 'UPS-1', 'line-interactive 1500 VA', 'Transfers critical loads to battery within milliseconds on mains loss; SNMP status to C2.', { live: 'ups' }),
      n('bat', 400, 190, 170, 54, 'UPS battery bank', 'VRLA', 'Energy store; % shown live (simulated drain 0.35 %/s sim).', { live: 'bat' }),
      n('pdu', 620, 70, 150, 54, 'PDU', 'metered', 'Distributes UPS output to racks/cabinets.'),
      n('poe', 820, 30, 150, 44, 'PoE switches', '48 V PSE', 'Power cameras over Ethernet.'),
      n('psu', 820, 100, 150, 44, '12/24 V DC PSUs', 'LRS-100 class', 'Cabinet DC bus for edge nodes and detectors.'),
      n('c2', 820, 170, 150, 44, 'C2 server & consoles', 'VIPER host', 'Command-centre computing.'),
      n('dcdc', 990, 100, 100, 44, 'DC-DC', '19 V / 5 V', 'Point-of-load conversion for Jetson/Pi.'),
      n('pv', 30, 360, 150, 54, 'PV panel', '≈ 50 W (EST)', 'Solar generation for remote env node.'),
      n('mppt', 220, 360, 140, 54, 'MPPT controller', 'SmartSolar 75/15', 'Maximum power point tracking charge controller.'),
      n('lbat', 400, 360, 170, 54, 'Node battery', '12 V', 'Overnight/monsoon autonomy; % shown live.', { live: 'pvbat' }),
      n('ldo', 620, 360, 150, 54, 'Buck + LDO', '12 → 3.3 V', 'Efficient conversion for ESP32 + radio.'),
      n('esp', 820, 360, 150, 54, 'EN-ENV (ESP32)', 'independent of mains', 'Keeps reporting environmental data during mains outages.'),
      n('mon', 400, 470, 370, 54, 'Power monitoring', 'UPS SNMP · INA219 rails · MPPT VE.Direct', 'Telemetry → C2. Mains loss raises an equipment-malfunction (power) event — rule P1.', { live: 'mon' }),
    ],
    edges: [
      e('mains', 'mcb', 'AC', 'Utility feed into protection.'), e('mcb', 'ups', 'AC', 'Protected feeder to UPS input.', { live: 'mainsline' }),
      e('ups', 'pdu', 'AC (protected)', 'Conditioned / battery-backed output.'), e('bat', 'ups', 'DC', 'Battery to inverter.', { fromSide: 't', toSide: 'b' }),
      e('pdu', 'poe', '', 'Switch power.', { fromSide: 'r', toSide: 'l' }), e('pdu', 'psu', '', 'Cabinet DC supplies.'), e('pdu', 'c2', '', 'Server/console power.', { fromSide: 'r', toSide: 'l' }),
      e('psu', 'dcdc', 'DC bus', 'To point-of-load converters.'),
      e('pv', 'mppt', 'PV DC', 'Panel to controller.'), e('mppt', 'lbat', 'charge', 'Charging current.'), e('lbat', 'ldo', '12 V', 'Battery to regulator.'), e('ldo', 'esp', '3.3 V', 'Node supply.'),
      e('ups', 'mon', 'SNMP', 'UPS status, runtime, alarms.', { fromSide: 'b', toSide: 't', dashed: true, via: 160 }),
      e('lbat', 'mon', 'VE.Direct', 'Battery/PV telemetry.', { fromSide: 'b', toSide: 't', dashed: true }),
    ],
  },
  software: {
    title: 'S6 — Software architecture',
    desc: 'Data ingestion → validation → event processing → inference (rules) → database → alert generation → dashboard. File references point to the source code.',
    w: 1100, h: 560,
    nodes: [
      g('B', 15, 30, 760, 515, 'Backend (Python · FastAPI · one asyncio loop)'), g('F', 795, 30, 290, 515, 'Frontend (vanilla ES modules · SVG)'),
      n('ad', 30, 70, 170, 54, 'Sensor adapters', 'simulation/adapters.py', 'SensorAdapter interface; SimulatedAdapter today, hardware adapters later.'),
      n('eng', 30, 160, 170, 54, 'Simulation engine', 'simulation/engine.py', 'World model, edge analytics, links, power — produces observations.'),
      n('dq', 30, 250, 170, 54, 'Delivery queue', 'engine._transmit/_deliver', 'Per-link latency, loss/retransmit, store-and-forward (MQTT stand-in).'),
      n('val', 240, 70, 160, 54, 'Data validation', 'fusion.ingest · V1/V2', 'Known/healthy sensor, plausible range, timestamp sanity.'),
      n('ts', 240, 160, 160, 54, 'Time sync', 'fusion._heartbeat · T1', 'Clock-offset estimation and correction.'),
      n('cor', 240, 250, 160, 54, 'Event processing', 'correlation buckets · merge', 'Zone/time correlation and incident merging.'),
      n('inf', 440, 70, 160, 54, 'Inference (rules)', 'fusion.classify()', 'Deterministic classification with rule trace. Not an ML model.'),
      n('lc', 440, 160, 160, 54, 'Lifecycle', 'event_engine/lifecycle.py', 'Operator transitions; HTTP 409 on invalid ones.'),
      n('db', 440, 250, 160, 54, 'Database', 'database/store.py · SQLite', 'events, lifecycle, logs, test_runs.'),
      n('rt', 240, 360, 360, 54, 'Runtime / alert generation', 'simulation/runtime.py', 'Ticks engine at 5 Hz, saves events, emits alerts/snapshots/logs to listeners; KPIs & analytics.'),
      n('rest', 620, 70, 140, 54, 'REST API', 'api/routes.py', 'Pydantic-validated requests; exports, reports, tests, docs.'),
      n('ws', 620, 250, 140, 54, 'WebSocket', 'api/ws.py', 'Push channel; drops snapshots before events if a client is slow.'),
      n('sc', 30, 450, 200, 54, 'Scenario harness', 'simulation/scenarios.py', 'Headless runtime + virtual clock for Module L tests.'),
      n('tests', 260, 450, 200, 54, 'Automated tests', 'backend/tests (pytest)', 'Rules, fusion, lifecycle, store, API, scenarios.'),
      n('st', 810, 70, 260, 54, 'State store', 'core/store.js', 'Single source of UI state; pub/sub topics.'),
      n('dash', 810, 160, 260, 54, 'Dashboard & views', 'dashboards/*, schematics/*', 'Command, architecture, schematics, devices, fusion, incidents, analytics, testing, docs.'),
      n('map', 810, 250, 260, 54, 'Map & animations', 'simulation/mapView.js · animations/flow.js', 'Rendered only from snapshots; packets only from real observations.'),
      n('act', 810, 360, 260, 54, 'Operator actions', 'components/incident.js', 'Ack/verify/respond/resolve/close with operator identity.'),
    ],
    edges: [
      e('ad', 'eng', 'read()', 'Readings from adapters.', { fromSide: 'b', toSide: 't' }), e('eng', 'dq', 'Observation', 'Edge observations into transport.', { fromSide: 'b', toSide: 't' }),
      e('dq', 'val', 'ingest', 'Delivered observations.', { fromSide: 'r', toSide: 'l', via: 220 }), e('val', 'ts', '', 'Valid observations.', { fromSide: 'b', toSide: 't' }), e('ts', 'cor', '', 'Corrected timestamps.', { fromSide: 'b', toSide: 't' }),
      e('cor', 'inf', 'set', 'Correlated set to classifier.', { fromSide: 'r', toSide: 'l', via: 420 }), e('inf', 'rt', 'Event', 'New/updated events.', { fromSide: 'b', toSide: 't', via: 620 }),
      e('rt', 'db', 'save', 'Persist before broadcast.', { fromSide: 't', toSide: 'b' }), e('rt', 'ws', 'emit', 'Alert/snapshot push.', { fromSide: 'r', toSide: 'b' }),
      e('db', 'rest', 'query', 'History, analytics, export.', { fromSide: 'r', toSide: 'l', via: 610 }), e('rest', 'lc', 'action', 'Operator transitions.', { fromSide: 'b', toSide: 'r' }), e('lc', 'db', '', 'Save transition.', { fromSide: 'b', toSide: 't' }),
      e('ws', 'st', 'messages', 'snapshot · event · event_update · observation · log', { fromSide: 'r', toSide: 'l', via: 785 }), e('rest', 'st', 'fetch', 'Initial load, filters.', { fromSide: 'r', toSide: 'l' }),
      e('st', 'dash', '', 'Subscriptions.', { fromSide: 'b', toSide: 't' }), e('dash', 'map', '', 'Live rendering.', { fromSide: 'b', toSide: 't' }), e('act', 'rest', 'POST', 'Operator action requests.', { fromSide: 'l', toSide: 'b', via: 690 }),
      e('sc', 'rt', 'headless', 'Isolated runtime with VirtualClock.', { fromSide: 't', toSide: 'l' }), e('tests', 'sc', '', 'pytest runs scenarios.', { fromSide: 'l', toSide: 'r' }),
    ],
  },
  lifecycle: {
    title: 'S7 — Complete incident lifecycle (live)',
    desc: 'From sensor observation to human verification, logging and response coordination. Timestamps come from the most recent non-informational incident; select another on the Incidents page.',
    w: 1100, h: 520,
    nodes: [
      n('l1', 20, 60, 130, 50, '1 · Sensor observation', 'physical → signal', 'A sensor responds to a phenomenon.', { stage: 'detected' }),
      n('l2', 170, 60, 130, 50, '2 · Edge detection', 'track / threshold', 'Edge node emits an observation with its clock time.'),
      n('l3', 320, 60, 130, 50, '3 · Transmission', 'MQTT QoS 1', 'Network delivery (latency recorded).'),
      n('l4', 470, 60, 130, 50, '4 · Validation & sync', 'V1–V2, T1', 'Validated and clock-corrected.', { stage: 'processed' }),
      n('l5', 620, 60, 130, 50, '5 · Correlation', 'zone × window', 'Grouped with other modalities.'),
      n('l6', 770, 60, 130, 50, '6 · Classification', 'rules → severity', 'Category, evidence, severity, rule trace.', { stage: 'classified' }),
      n('l7', 920, 60, 160, 50, '7 · Alert + logging', 'SQLite · WebSocket', 'Persisted and pushed to C2.', { stage: 'alerted' }),
      n('l8', 920, 190, 160, 50, '8 · Acknowledge', 'operator', 'Operator acknowledges (ack latency).', { stage: 'acknowledged' }),
      n('l9', 700, 180, 170, 70, '9 · Verify', 'genuine? FP? benign?', 'Human decision using cameras / PTZ / patrol.', { stage: 'verified' }),
      n('l10', 470, 190, 170, 50, '10 · Authorised response', 'notification only', 'Named operator authorises a response category.', { stage: 'response_initiated' }),
      n('lfp', 700, 330, 170, 50, 'False positive / benign', 'no response', 'Recorded as FP/benign — feeds false-positive rate.'),
      n('l11', 470, 330, 170, 50, '11 · Resolve', 'operator', 'Incident resolved.', { stage: 'resolved' }),
      n('l12', 240, 330, 170, 50, '12 · Close', 'operator', 'Record closed; no further changes.', { stage: 'closed' }),
      n('l13', 20, 330, 170, 50, '13 · Incident report', 'MD / JSON', 'Complete timestamped report generated from the stored lifecycle.'),
    ],
    edges: [
      e('l1', 'l2', '', 'Raw signal to edge analytics.'), e('l2', 'l3', '', 'Observation published.'), e('l3', 'l4', '', 'Delivered to fusion.'), e('l4', 'l5', '', 'Validated observations.'),
      e('l5', 'l6', '', 'Correlated set.'), e('l6', 'l7', '', 'Event created.'), e('l7', 'l8', 'alert', 'Operator notified.', { fromSide: 'b', toSide: 't' }),
      e('l8', 'l9', '', 'Operator reviews evidence.', { fromSide: 'l', toSide: 'r' }), e('l9', 'l10', 'genuine', 'Verified genuine → response allowed.', { fromSide: 'l', toSide: 'r' }),
      e('l9', 'lfp', 'FP / benign', 'No threat → no response.', { fromSide: 'b', toSide: 't' }), e('lfp', 'l11', '', 'Resolve directly.', { fromSide: 'l', toSide: 'r' }),
      e('l10', 'l11', '', 'After response.', { fromSide: 'b', toSide: 't' }), e('l11', 'l12', '', 'Close.', { fromSide: 'l', toSide: 'r' }), e('l12', 'l13', '', 'Report.', { fromSide: 'l', toSide: 'r' }),
    ],
  },
};

function commsSpec() {
  const env = state.env;
  const nodes = [g('F', 15, 30, 330, 515, 'Field edge nodes'), g('T', 365, 30, 300, 515, 'Transport'), g('C', 685, 30, 400, 515, 'Command centre LAN')];
  const edges = [];
  env.nodes.forEach((nd, i) => {
    const y = 60 + i * 78;
    const L = state.meta.links[nd.link];
    nodes.push(n(nd.id, 30, y, 150, 54, nd.id, state.meta.node_models[nd.model].label, `Edge node in zone ${nd.zone}. Sensors: ${env.sensors.filter((x) => x.node === nd.id).map((x) => x.id).join(', ')}`, { live: 'node' }));
    nodes.push(n(`L-${nd.id}`, 390, y, 150, 54, L.label, `${L.latency[0]}–${L.latency[1]} ms · loss ${(L.loss * 100).toFixed(1)} %`, `Simulated ${L.label}: one-way latency ${L.latency[0]}–${L.latency[1]} ms, loss ${(L.loss * 100).toFixed(1)} % (retransmitted at QoS 1).`));
    edges.push(e(nd.id, `L-${nd.id}`, '', `Uplink from ${nd.id}. Live latency shown on the link.`, { live: nd.id }));
    edges.push(e(`L-${nd.id}`, nd.link === 'lorawan' ? 'gw' : nd.link === 'lte' ? 'vpn' : 'core', '', 'Transport into the command-centre LAN.', { fromSide: 'r', toSide: 'l' }));
  });
  nodes.push(n('gw', 560, 470, 95, 54, 'LoRaWAN GW', '+ network server', 'Terminates LoRa radio; republishes to MQTT.'));
  nodes.push(n('vpn', 560, 380, 95, 54, 'VPN', 'IPsec/WG', 'Cellular links enter through an encrypted tunnel.'));
  nodes.push(n('core', 700, 160, 150, 60, 'Core switch + firewall', 'VLANs · ACLs', 'Segregates camera, sensor, management and C2 networks.'));
  nodes.push(n('mq', 700, 290, 150, 54, 'MQTT broker', 'mutual TLS', 'Authenticates every node by certificate; topic ACL per node.'));
  nodes.push(n('fu', 900, 290, 170, 54, 'Fusion service', 'heartbeat watchdog 7 s', 'Consumes observations; raises communication failure on missing heartbeats.'));
  nodes.push(n('ui', 900, 160, 170, 54, 'Operator consoles', 'WebSocket', 'Live push.'));
  edges.push(e('gw', 'mq', 'MQTT', 'LoRaWAN NS → broker.', { fromSide: 'r', toSide: 'b' }), e('vpn', 'core', '', 'Decrypted into LAN.', { fromSide: 'r', toSide: 'b' }),
    e('core', 'mq', '', 'Sensor VLAN to broker.', { fromSide: 'b', toSide: 't' }), e('mq', 'fu', 'subscribe', 'Observation topics.'), e('fu', 'ui', 'WS', 'Events to operators.', { fromSide: 't', toSide: 'b' }));
  return { ...SCHEMATICS.comms, nodes, edges };
}

// ---------------------------------------------------------------- renderer
function anchor(nd, side) {
  return { l: [nd.x, nd.y + nd.h / 2], r: [nd.x + nd.w, nd.y + nd.h / 2], t: [nd.x + nd.w / 2, nd.y], b: [nd.x + nd.w / 2, nd.y + nd.h] }[side];
}
function autoSides(a, b) {
  const dx = (b.x + b.w / 2) - (a.x + a.w / 2), dy = (b.y + b.h / 2) - (a.y + a.h / 2);
  if (Math.abs(dx) * 0.6 >= Math.abs(dy)) return dx >= 0 ? ['r', 'l'] : ['l', 'r'];
  return dy >= 0 ? ['b', 't'] : ['t', 'b'];
}
function route(a, b, ed) {
  const [fs, ts] = ed.fromSide && ed.toSide ? [ed.fromSide, ed.toSide] : autoSides(a, b);
  const p = anchor(a, fs), q = anchor(b, ts);
  const horiz = (x) => 'lr'.includes(x);
  let pts;
  if (horiz(fs) && horiz(ts)) {
    const mx = ed.via ?? (p[0] + q[0]) / 2;
    pts = Math.abs(p[1] - q[1]) < 1 ? [p, q] : [p, [mx, p[1]], [mx, q[1]], q];
  } else if (!horiz(fs) && !horiz(ts)) {
    const my = ed.via ?? (p[1] + q[1]) / 2;
    pts = Math.abs(p[0] - q[0]) < 1 ? [p, q] : [p, [p[0], my], [q[0], my], q];
  } else if (horiz(fs)) pts = [p, [q[0], p[1]], q];
  else pts = [p, [p[0], q[1]], q];
  return pts;
}

function render(spec, host, highlightTypes) {
  const svg = s('svg', { viewBox: `0 0 ${spec.w} ${spec.h}`, width: '100%', style: { maxHeight: 'calc(100vh - 210px)', background: '#1b1e22' } });
  svg.append(s('defs', {}, s('marker', { id: 'sa', viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: 'auto-start-reverse' }, s('path', { d: 'M 0 0 L 10 5 L 0 10 z', fill: '#7f8994' }))));
  for (let x = 0; x < spec.w; x += 20) svg.append(s('line', { x1: x, x2: x, y1: 0, y2: spec.h, stroke: 'rgba(255,255,255,0.025)' }));
  for (let y = 0; y < spec.h; y += 20) svg.append(s('line', { x1: 0, x2: spec.w, y1: y, y2: y, stroke: 'rgba(255,255,255,0.025)' }));
  const byId = Object.fromEntries(spec.nodes.map((x) => [x.id, x]));
  const els = { nodes: {}, edges: [] };
  for (const nd of spec.nodes.filter((x) => x.group)) {
    svg.append(s('g', { class: 'sch-node group' }, s('rect', { x: nd.x, y: nd.y, width: nd.w, height: nd.h, rx: 3 }), s('text', { x: nd.x + 8, y: nd.y + 14 }, nd.label)));
  }
  const edgeLayer = s('g', {}); svg.append(edgeLayer);
  spec.edges.forEach((ed, i) => {
    const a = byId[ed.from], b = byId[ed.to];
    if (!a || !b) return;
    const pts = route(a, b, ed);
    const d = 'M ' + pts.map((p) => p.join(' ')).join(' L ');
    const mid = pts[Math.floor((pts.length - 1) / 2)], mid2 = pts[Math.floor((pts.length - 1) / 2) + 1];
    const lx = (mid[0] + mid2[0]) / 2, ly = (mid[1] + mid2[1]) / 2;
    const id = `C${String(i + 1).padStart(2, '0')}`;
    const path = s('path', { d, 'marker-end': 'url(#sa)', 'stroke-dasharray': ed.dashed ? '4 3' : null });
    const grp = s('g', { class: 'sch-edge' }, s('path', { d, class: 'hit' }), path,
      ed.label ? s('text', { x: lx + 3, y: ly - 3 }, ed.label) : null);
    grp.addEventListener('mousemove', (ev) => showTip(ev, `<b>${id} · ${esc(a.label)} → ${esc(b.label)}</b>${ed.label ? `<span class="mono">${esc(ed.label)}</span><br>` : ''}${esc(ed.tip)}`));
    grp.addEventListener('mouseleave', hideTip);
    edgeLayer.append(grp);
    els.edges.push({ ed, path, grp, lx, ly });
  });
  for (const nd of spec.nodes.filter((x) => !x.group)) {
    const hl = highlightTypes && nd.types?.some((t) => highlightTypes.includes(t));
    const grp = s('g', { class: `sch-node ${hl ? 'hl' : ''}` },
      s('rect', { x: nd.x, y: nd.y, width: nd.w, height: nd.h, rx: 2, 'stroke-width': hl ? 2 : 1 }),
      s('text', { x: nd.x + 7, y: nd.y + 11, class: 'idt' }, nd.id.toUpperCase()),
      s('text', { x: nd.x + 7, y: nd.y + nd.h / 2 + 4, style: 'font-weight:600' }, nd.label),
      nd.sub ? s('text', { x: nd.x + 7, y: nd.y + nd.h - 6, class: 'sub' }, nd.sub) : null);
    const liveText = s('text', { x: nd.x + nd.w - 6, y: nd.y + 11, 'text-anchor': 'end', class: 'idt', style: 'fill:#d8b13a' }, '');
    grp.append(liveText);
    grp.addEventListener('mousemove', (ev) => showTip(ev, `<b>${nd.id.toUpperCase()} · ${esc(nd.label)}</b>${nd.sub ? `<span class="mono">${esc(nd.sub)}</span><br>` : ''}${esc(nd.tip)}${grp.dataset.live ? `<br><span style="color:#d8b13a">${esc(grp.dataset.live)}</span>` : ''}`));
    grp.addEventListener('mouseleave', hideTip);
    svg.append(grp);
    els.nodes[nd.id] = { nd, grp, rect: grp.querySelector('rect'), liveText };
  }
  host.append(svg);
  return els;
}

function liveUpdate(key, els, param) {
  const snap = state.snapshot;
  if (!snap) return;
  const setLive = (id, text, color) => {
    const x = els.nodes[id]; if (!x) return;
    x.liveText.textContent = text; x.grp.dataset.live = text;
    if (color) x.rect.setAttribute('stroke', color);
  };
  if (key === 'comms') {
    for (const nd of state.env.nodes) {
      const ns = snap.nodes[nd.id];
      const col = { online: '#4caf7a', link_down: '#d9473f', unpowered: '#6b7078' }[ns.status];
      setLive(nd.id, ns.status === 'online' ? `${ns.latency_ms} ms` : ns.status.toUpperCase(), col);
      const edge = els.edges.find((x) => x.ed.live === nd.id);
      if (edge) { edge.path.style.stroke = col; edge.path.style.strokeDasharray = ns.status === 'online' ? '' : '4 3'; }
      if (ns.queue) setLive(nd.id, `buffer ${ns.queue}`, col);
    }
  }
  if (key === 'power') {
    const p = snap.power;
    setLive('mains', p.mains ? 'LIVE' : 'FAILED', p.mains ? '#4caf7a' : '#d9473f');
    setLive('ups', `${p.source} · load ${p.load_w} W`, p.mains ? '#4caf7a' : '#d8b13a');
    setLive('bat', `${p.ups_pct.toFixed(1)} %`, p.ups_pct > 30 ? '#4caf7a' : '#d9473f');
    setLive('pvbat', `${p.pv_battery_pct.toFixed(0)} %`);
    setLive('lbat', `${p.pv_battery_pct.toFixed(0)} %`);
    setLive('mon', p.mains ? 'normal' : 'MAINS LOSS EVENT');
    const ml = els.edges.find((x) => x.ed.live === 'mainsline');
    if (ml) ml.path.style.stroke = p.mains ? '' : '#d9473f';
  }
  if (key === 'sensor' && param) {
    const sn = sensorById(param); const st = snap.sensors[param];
    if (sn && st) for (const x of Object.values(els.nodes)) if (x.nd.types?.includes(sn.type)) setLive(x.nd.id, `${param}: ${st.reading?.text ?? st.status}`);
  }
  if (key === 'lifecycle') {
    const ev = sortedEvents().find((x) => x.severity !== 'info');
    if (!ev) return;
    const have = Object.fromEntries(ev.lifecycle.map((x) => [x.stage, x]));
    for (const x of Object.values(els.nodes)) {
      const st = x.nd.stage && have[x.nd.stage];
      if (x.nd.stage) setLive(x.nd.id, st ? fmtLocal(st.ts_epoch, false) : '—', st ? '#4caf7a' : null);
    }
    setLive('l13', ev.event_id);
  }
}

export function schematicsView() {
  let unsubs = [];
  return {
    mount(root, param) {
      const [keyRaw, query] = (param || 'architecture').split('?');
      const key = SCHEMATICS[keyRaw] ? keyRaw : 'architecture';
      const sensorId = new URLSearchParams(query || '').get('sensor') || (state.selected?.type === 'sensor' ? state.selected.id : null);
      const tabs = h('div', { class: 'row wrap' }, Object.entries(SCHEMATICS).map(([k, v]) => h('a', { class: `btn sm ${k === key ? 'on' : ''}`, href: `#/schematics/${k}` }, v.title.split(' — ')[0] + ' ' + v.title.split(' — ')[1].replace(' (live)', ''))));
      const spec = key === 'comms' ? commsSpec() : SCHEMATICS[key];
      const host = h('div', { class: 'panel', style: { padding: '6px' } });
      const sn = sensorId ? sensorById(sensorId) : null;
      root.append(h('div', { class: 'page' },
        h('div', { class: 'page-head' }, h('h2', {}, spec.title), h('p', {}, spec.desc)),
        tabs,
        sn && key === 'sensor' ? h('div', { class: 'note info' }, `Highlighted path for ${sn.id} (${sn.type_label}) → ${sn.node} via ${sn.bus}. Live reading shown top-right of highlighted blocks.`) : null,
        host,
        h('div', { class: 'small muted' }, 'Hover any block or connection for its identifier and engineering purpose. Block IDs (top-left) and connection IDs (C01…) are referenced in documentation/engineering_schematics.md. Conceptual, non-site-specific layouts.')));
      const els = render(spec, host, sn && key === 'sensor' ? [sn.type] : null);
      liveUpdate(key, els, sensorId);
      unsubs.push(on('snapshot', () => liveUpdate(key, els, sensorId)));
      unsubs.push(on('events', () => liveUpdate(key, els, sensorId)));
    },
    unmount() { unsubs.forEach((u) => u()); unsubs = []; },
  };
}

export { SCHEMATICS };
