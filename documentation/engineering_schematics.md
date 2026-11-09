# VIPER — Engineering Schematics

The seven schematics are interactive SVG in the app (**Schematics** tab). Hover any block for its identifier and description, and any connection for its purpose. Block identifiers appear top-left of each block (e.g. `JET`, `ISO`); connections are numbered `C01…` in drawing order. Layouts are **conceptual and non-site-specific** — they show engineering relationships, not the security configuration of any real facility.

Source: `frontend/src/schematics/schematics.js` (data + renderer). S4, S5 and S7 are live: their colours and labels are driven by the running simulation.

## S1 — Complete VIPER architecture

Field devices (cameras, thermal, fence nodes, point detectors, radar, environmental sensors, power) → edge nodes (Jetson ×4, Raspberry Pi 5 gate node, ESP32 environmental node) → network (PoE switch/fibre, Wi-Fi/LTE, LoRaWAN gateway, MQTT broker) → command-centre server (ingest & validation → timestamp sync → correlation → rule classifier → SQLite → REST/WebSocket; lifecycle state machine) → operators (console, response workflow, reports).

Key connections: RTSP/PoE camera links carry video to the GPU node *and* power the cameras from a UPS-backed switch; RS-485 carries fence alarms; supervised GPIO loops carry contact states; only *observations* (not video) leave the edge; every event is persisted before broadcast; operator actions return through the lifecycle state machine.

## S2 — Sensor integration

| From | To | Interface | Engineering purpose |
|---|---|---|---|
| Thermal / optical camera | PoE switch | Cat6, IEEE 802.3af/at | One cable for power and RTSP/ONVIF data; VLAN per device class |
| Radar | PoE switch | Ethernet | JSON track output |
| PoE switch | Jetson | GbE trunk | Aggregated streams to edge analytics |
| Fence nodes (ADXL355 + MCU) | Isolated RS-485 (ADM2587E) | RS-485 A/B, 120 Ω terminated both ends | Long multi-drop run along the fence; isolation against ground-potential differences and surges |
| Isolated RS-485 | Jetson | USB-UART | Modbus RTU master polling |
| PIR, microwave detectors | Opto-isolated input board | 12 V relay contacts | Isolation and level shifting to 3.3 V |
| Gate contact | Opto-isolated input board | End-of-line resistor loop | Distinguishes open / closed / cut / short (tamper) |
| Opto board | Raspberry Pi 5 | GPIO 3.3 V | Debounced digital inputs |
| Access-control reader | Raspberry Pi 5 | OSDP over RS-485 (or Wiegand) | Credential events → authorisation context (rule R1) |
| SHT31 | ESP32 | I²C (0x44) | Temperature/humidity |
| Smoke detector relay | ESP32 | GPIO dry contact | VIPER *monitors* the certified detector; it is not a fire alarm system |
| Leak controller | ESP32 | GPIO/ADC | Wet/dry status |
| ESP32 | RFM95W (SX1276) | SPI | LoRaWAN IN865 uplink |
| MPPT + battery | ESP32 | 3.3 V regulated | Mains-independent supply |

## S3 — Edge computing node

Inputs (camera streams, fence bus, radar tracks, cabinet sensors) → processing (NVDEC decode → DNN detection → multi-object tracker → ground-plane mapping; threshold & debounce for fence) → observation builder (edge timestamp, quality, label, position) → MQTT client (QoS 1, TLS) → GbE interface. Store-and-forward queue on NVMe when the link is down; heartbeat/watchdog every 2 s carrying clock sample and power health; NTP/PTP clock discipline; host firewall (outbound only); 19 V DC from a UPS-backed 12/24 V cabinet bus with INA219 monitoring.

In the demonstrator the DNN and tracker are **simulated** (object labels have deliberate 5–25 % error rates); edge processing latency is modelled at 22–45 ms (Jetson), 6–15 ms (Pi), 2–6 ms (ESP32).

## S4 — Communication architecture (live)

Each edge node → its uplink (fibre / Ethernet / Wi-Fi PtP / LTE via VPN / LoRaWAN via gateway + network server) → core switch & firewall (VLANs, ACLs) → MQTT broker (mutual TLS) → fusion service (heartbeat watchdog 7 s) → operator consoles (WebSocket). Link colours: green online, red link down, grey unpowered; the current one-way latency and store-and-forward buffer size are shown on each node.

## S5 — Power architecture (live)

Mains incomer → distribution board (MCB/RCD/SPD) → UPS-1 (with VRLA battery bank) → metered PDU → PoE switches, 12/24 V DC supplies (→ DC-DC point-of-load), C2 server. Separate solar chain: PV panel → MPPT controller → node battery → buck/LDO → ESP32 environmental node. Monitoring: UPS SNMP and VE.Direct/INA219 telemetry → C2. Live: mains state, UPS source and load, battery %. A mains failure raises a power event (rule P1); restoration is appended to the same incident.

## S6 — Software architecture

Adapters → simulation engine → delivery queue → validation → time sync → event processing (correlation/merge) → inference (rules) → runtime (alert generation) → SQLite → REST/WebSocket → frontend state store → dashboards/map → operator actions → REST → lifecycle → SQLite. Scenario harness and pytest drive a headless runtime. Each block names its source file.

## S7 — Complete incident lifecycle (live)

1 Sensor observation → 2 Edge detection → 3 Transmission → 4 Validation & sync → 5 Correlation → 6 Classification → 7 Alert + logging → 8 Acknowledge → 9 Verify → (genuine) 10 Authorised response → 11 Resolve → 12 Close → 13 Incident report; (false positive / benign) → 11 Resolve directly. Stages show the timestamps of the most recent non-informational incident.
