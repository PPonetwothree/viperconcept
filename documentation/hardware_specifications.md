# VIPER — Hardware Specifications

> Provenance key: **DS** = manufacturer-published figure compiled for this demonstrator (source documents were **not re-fetched during the build** — verify against the current datasheet revision before design-in). **EST** = illustrative engineering estimate. All INR prices are EST (ex-GST indicative ranges).

No hardware is connected to this demonstrator. Simulated sensors reference these profiles.

## 1. Hardware architecture

Each site is divided into four perimeter sectors (A–D, each spanning an outside approach strip and an inside strip) and interior zones (E–F). Each perimeter side has one GPU edge node (Jetson Orin Nano) serving one optical camera, one thermal camera and two fence-vibration segments; two corner radars cover the approaches; the main gate has a Raspberry Pi 5 node with contact, PIR, microwave, PTZ and low-light cameras; environmental sensors report through a solar ESP32 LoRaWAN node. All edge nodes except the solar node are UPS-backed.

| Edge node | Model | Uplink | Simulated edge processing |
|---|---|---|---|
| jetson | Jetson Orin Nano | per layout | 22–45 ms |
| rpi5 | Raspberry Pi 5 | per layout | 6–15 ms |
| esp32 | ESP32 + SX1276 | per layout | 2–6 ms |

## 2. Communication architecture

Edge nodes publish observations and 2 s heartbeats (MQTT QoS 1, mutual TLS in deployment). The demonstrator models each uplink with a latency range and loss probability; lost publishes are retransmitted. A heartbeat missing for 7 s raises a communication failure. During outages nodes buffer up to 500 observations (store-and-forward) and flush them on restoration with original timestamps.

| Link | One-way latency (sim) | Loss (sim) |
|---|---|---|
| Fibre Ethernet | 1–3 ms | 0.0 % |
| Ethernet (Cat6) | 1–4 ms | 0.0 % |
| Wi-Fi PtP bridge | 4–25 ms | 0.5 % |
| 4G LTE | 40–140 ms | 1.0 % |
| LoRaWAN IN865 | 400–1600 ms | 2.0 % |

Figures are simulation parameters chosen to be representative; they are not measurements.

## 3. Power management

- Mains → distribution board (MCB/RCD/SPD) → UPS-1 (line-interactive) → PDU → PoE switches, cabinet DC supplies, C2.
- Cabinet DC bus with point-of-load DC-DC converters; rail telemetry via INA219.
- Remote environmental node: PV panel → MPPT controller → 12 V battery → buck/LDO → ESP32 (independent of mains).
- Power events: the UPS reports mains loss via SNMP → equipment-malfunction (power) incident (rule P1); restoration is appended to the same incident. Simulated UPS drain: 0.35 %/s (sim); nodes shed below 8 %.

### Indicative power budget per perimeter side (EST)

| Load | Qty | Typical W (EST) | Subtotal W |
|---|---|---|---|
| Optical camera (PoE) | 1 | 7 | 7 |
| Thermal camera (PoE) | 1 | 8 | 8 |
| Jetson Orin Nano (15 W mode) | 1 | 15 | 15 |
| Fence nodes (2) + RS-485 | 2 | 0.5 | 1 |
| PoE switch overhead | 1 | 10 | 10 |
| **Total** | | | **≈ 41 W** |

At ≈ 41 W, a 12 V 2 × 7 Ah cabinet battery (≈ 168 Wh, ≈ 50 % usable for VRLA longevity) gives ≈ 2 h ride-through before inverter losses — size per site risk assessment.

## 4. Device profiles

### Optical surveillance

#### 4 MP fixed bullet IP camera (AcuSense) — Hikvision DS-2CD2043G2-I

- **Category:** Optical surveillance / IP CCTV camera
- **Working principle:** CMOS image sensor behind a fixed lens converts light to pixels; an on-board SoC encodes H.264/H.265 and runs basic human/vehicle classification. 850 nm IR LEDs illuminate the scene at night (monochrome).
- **Internal components:** 1/3" progressive-scan CMOS sensor; Fixed lens (2.8/4/6 mm options); Video SoC (encoder + analytics); IR LED array + IR-cut filter; PoE PD controller; IP67 housing
- **Operating voltage:** 12 VDC ± 25 % or PoE IEEE 802.3af (DS)
- **Power consumption:** ≤ 8 W max per datasheet class (verify revision) (DS)
- **Communication:** Ethernet 10/100, RTSP, ONVIF (Profile S/G/T), ISAPI (DS)
- **Operating temperature:** −30 °C to +60 °C (DS)
- **Environmental limitations:** Fog, heavy rain and direct sun glare degrade detection; IR reflections from fences/spider webs cause nuisance motion.
- **Approx. price:** ₹7,000 – ₹12,000 (EST)
- **Advantages:** Low cost per channel; ONVIF standard integration; PoE single-cable install
- **Disadvantages:** Fixed field of view; Monochrome at night; Analytics limited vs. edge GPU
- **Integration:** PoE switch on UPS; RTSP stream pulled by Jetson edge node; time-sync via NTP; VLAN-isolated.
- **Alternatives:** Axis P14 series; Hanwha Wisenet X; CP Plus (India)

| Specification | Value | Source |
|---|---|---|
| Resolution | 2688 × 1520 (4 MP) | DS |
| Compression | H.265+/H.265/H.264+/H.264 | DS |
| IR range | up to 40 m | DS |
| Ingress protection | IP67 | DS |
| Human detection range at perimeter (sim) | ≈ 60–120 m with 6 mm lens — scene dependent | EST |

Sources: [Hikvision product page](https://www.hikvision.com/en/products/IP-Products/Network-Cameras/)

#### 4 MP ColorVu fixed bullet camera (low-light, wide-angle) — Hikvision DS-2CD2047G2-L

- **Category:** Optical surveillance / Low-light / wide-angle camera
- **Working principle:** Large-aperture lens (F1.0 class) and high-sensitivity sensor keep colour imaging in very low light; supplemental warm-white LED instead of IR. Short focal length (2.8 mm option) gives a wide field of view for gates.
- **Internal components:** High-sensitivity CMOS sensor; F1.0 fixed lens; White-light LEDs; Video SoC; PoE PD
- **Operating voltage:** 12 VDC / PoE 802.3af (DS)
- **Power consumption:** ≈ 6–9 W with LEDs on (EST)
- **Communication:** Ethernet, RTSP, ONVIF (DS)
- **Operating temperature:** −30 °C to +60 °C (EST — verify)
- **Environmental limitations:** Visible white light may be undesirable (light pollution, airside rules); wide lens reduces pixels on target.
- **Approx. price:** ₹7,000 – ₹12,000 (EST)
- **Advantages:** Colour evidence at night; Wide coverage at access points
- **Disadvantages:** Short effective detection range; Visible illumination
- **Integration:** Mounted at checkpoint; feeds the gate node (Raspberry Pi 5) for ANPR/presence; same PoE/NTP design.
- **Alternatives:** Dahua Full-color series; Axis Lightfinder cameras

| Specification | Value | Source |
|---|---|---|
| Resolution | 4 MP | DS |
| Lens aperture | F1.0 | DS |
| Horizontal FOV (2.8 mm) | ≈ 100° | EST |
| Supplemental light range | ≈ 40 m | EST |

Sources: [Hikvision ColorVu](https://www.hikvision.com/en/products/IP-Products/Network-Cameras/)

#### 4 MP 25× IR PTZ dome — Hikvision DS-2DE4425IW-DE

- **Category:** Optical surveillance / PTZ camera
- **Working principle:** Motorised pan/tilt head with 25× optical zoom lens; operator or rule-based presets slew the camera to an alarm location for visual verification. IR illuminator for night.
- **Internal components:** CMOS sensor; 25× zoom lens; Pan/tilt motors + encoders; IR illuminator; Heater/fan; PoE+ PD
- **Operating voltage:** 12 VDC / PoE+ (802.3at) (DS)
- **Power consumption:** ≈ 15–25 W with IR + heater (EST)
- **Communication:** Ethernet, ONVIF PTZ, ISAPI (DS)
- **Operating temperature:** −30 °C to +65 °C (EST — verify)
- **Environmental limitations:** Moving parts need maintenance; wind-induced shake at full zoom.
- **Approx. price:** ₹35,000 – ₹70,000 (EST)
- **Advantages:** Long-range visual verification; One camera covers many alarm points
- **Disadvantages:** Sees one place at a time; Higher power and cost
- **Integration:** Slaved to alarms by the C2 software (ONVIF absolute move to preset) — always operator-confirmed.
- **Alternatives:** Axis Q60 series; Hanwha XNP series

| Specification | Value | Source |
|---|---|---|
| Resolution | 4 MP | DS |
| Optical zoom | 25× | DS |
| IR range | up to 100 m | DS |
| Preset slew time | ≈ 1–2 s | EST |

Sources: [Hikvision PTZ cameras](https://www.hikvision.com/en/products/IP-Products/PTZ-Cameras/)

### Thermal surveillance

#### Fixed thermal bullet camera (perimeter class) — Various (model to be selected) e.g. Hikvision DS-2TD26xx / Axis Q19xx / Teledyne FLIR FC-Series

- **Category:** Thermal surveillance / Thermal imaging camera
- **Working principle:** Uncooled VOx microbolometer focal-plane array absorbs 8–14 µm long-wave IR; pixel resistance changes with absorbed heat. Detection works in total darkness and through light smoke; analytics flag human/vehicle-sized warm blobs.
- **Internal components:** Uncooled VOx microbolometer FPA (e.g. 384 × 288); Germanium lens; Shutter for NUC; ISP + analytics SoC; Heater; PoE PD
- **Operating voltage:** 12–24 VDC / PoE (EST)
- **Power consumption:** ≈ 5–12 W (EST)
- **Communication:** Ethernet, RTSP, ONVIF (EST)
- **Operating temperature:** ≈ −40 °C to +65 °C (EST)
- **Environmental limitations:** Thermal crossover (dawn/dusk) lowers contrast; heavy rain/fog attenuate LWIR; export-control rules may apply.
- **Approx. price:** ₹1,20,000 – ₹4,00,000 (EST)
- **Advantages:** Works in darkness; Long range, few nuisance alarms from light changes
- **Disadvantages:** High cost; Low resolution vs visible; Export licensing for some lenses/frame rates
- **Integration:** Pair with an optical camera on the same field of view for identification; analytics on edge node.
- **Alternatives:** FLIR Lepton 3.5 (dev-grade); Bi-spectrum cameras (thermal + visible in one housing)

| Specification | Value | Source |
|---|---|---|
| Spectral band | 8–14 µm LWIR (typical for VOx uncooled) | EST |
| Resolution | 384 × 288 typical perimeter class | EST |
| NETD | ≤ 40–50 mK typical | EST |
| Human detection range | ≈ 300–600 m depending on lens (vendor DRI tables) | EST |

Sources: [Teledyne FLIR security thermal](https://www.flir.com/security/)

#### Radiometric LWIR thermal camera module — Teledyne FLIR Lepton 3.5

- **Category:** Thermal surveillance / Thermal imaging module
- **Working principle:** Miniature uncooled microbolometer core with integrated shutter; outputs a radiometric (temperature-calibrated) 160 × 120 image over SPI, controlled over I²C (CCI).
- **Internal components:** 160 × 120 VOx microbolometer; Integrated shutter; Wafer-level optics; On-module ISP
- **Operating voltage:** ≈ 2.8 V / 1.2 V / I/O 2.5–3.1 V core rails (via breakout board) (DS)
- **Power consumption:** ≈ 150 mW typical (DS)
- **Communication:** SPI (VoSPI) video, I²C control (DS)
- **Operating temperature:** −10 °C to +80 °C (DS)
- **Environmental limitations:** Short human-detection range (tens of metres); requires weatherproof window (germanium/chalcogenide).
- **Approx. price:** ₹18,000 – ₹30,000 (EST)
- **Advantages:** Low power; Radiometric — good for hotspot/fire detection; Easy to prototype on Pi/ESP32-S3
- **Disadvantages:** Low resolution; Short range; < 9 Hz
- **Integration:** Breakout board → Raspberry Pi 5 SPI/I²C; useful for gate/equipment hotspot monitoring in a pilot.
- **Alternatives:** Melexis MLX90640; Panasonic Grid-EYE AMG8833; Seek Thermal Mosaic cores

| Specification | Value | Source |
|---|---|---|
| Resolution | 160 × 120 | DS |
| Spectral range | 8–14 µm | DS |
| Thermal sensitivity | < 50 mK | DS |
| HFOV | 57° | DS |
| Frame rate | < 9 Hz (export compliant) | DS |
| Radiometric | Yes | DS |

Sources: [Lepton product page](https://www.flir.com/products/lepton/)

#### 32 × 24 far-infrared thermopile array — Melexis MLX90640

- **Category:** Thermal surveillance / Infrared sensor
- **Working principle:** Array of 768 thermopile pixels; each pixel's thermoelectric voltage is proportional to incident IR flux. Host computes per-pixel temperature using calibration EEPROM.
- **Internal components:** 768 thermopile pixels; Calibration EEPROM; ADC; I²C interface
- **Operating voltage:** 3.3 V (DS)
- **Power consumption:** ≈ 23 mA (DS)
- **Communication:** I²C (DS)
- **Operating temperature:** −40 °C to +85 °C (DS)
- **Environmental limitations:** Very coarse imagery; detects presence/hotspots only at short range.
- **Approx. price:** ₹4,500 – ₹8,000 (EST)
- **Advantages:** Inexpensive; Simple I²C
- **Disadvantages:** Not an imaging camera; Range ≈ a few metres for people
- **Integration:** ESP32 or Pi I²C bus; good for equipment-room hotspot detection.
- **Alternatives:** AMG8833; Lepton 3.5

| Specification | Value | Source |
|---|---|---|
| Resolution | 32 × 24 | DS |
| FOV | 55° × 35° or 110° × 75° | DS |
| Interface | I²C (up to 1 MHz) | DS |
| Refresh rate | 0.5–64 Hz | DS |

Sources: [Melexis MLX90640](https://www.melexis.com/en/product/MLX90640/Far-Infrared-Thermal-Sensor-Array)

#### 8 × 8 infrared array sensor (Grid-EYE) — Panasonic AMG8833

- **Category:** Thermal surveillance / Infrared sensor
- **Working principle:** 64 thermopile elements on a MEMS die with silicon lens; outputs an 8 × 8 temperature grid.
- **Internal components:** 8 × 8 thermopile array; Silicon lens; I²C interface; Interrupt output
- **Operating voltage:** 3.3 V or 5 V variants (DS)
- **Power consumption:** ≈ 4.5 mA (DS)
- **Communication:** I²C (DS)
- **Operating temperature:** 0 °C to +80 °C (DS)
- **Environmental limitations:** Indoor-oriented; poor outdoors in sun.
- **Approx. price:** ₹2,500 – ₹4,500 (EST)
- **Advantages:** Cheap occupancy sensing
- **Disadvantages:** Very low resolution
- **Integration:** Indoor rooms (battery room/control room) occupancy cross-check.
- **Alternatives:** MLX90640

| Specification | Value | Source |
|---|---|---|
| Resolution | 8 × 8 | DS |
| Viewing angle | 60° | DS |
| Human detection distance | up to ≈ 7 m | DS |
| Frame rate | 1 or 10 fps | DS |

Sources: [Panasonic Grid-EYE](https://industrial.panasonic.com/ww/products/pt/grid-eye)

### Perimeter sensors

#### PIR motion sensor module — Generic (BISS0001-based) HC-SR501

- **Category:** Perimeter sensors / PIR sensor
- **Working principle:** Dual-element pyroelectric sensor behind a Fresnel lens; a moving warm body creates a differential signal that the BISS0001 IC thresholds into a digital output pulse.
- **Internal components:** Pyroelectric dual-element detector; Fresnel lens; BISS0001 signal processor; Sensitivity & delay pots
- **Operating voltage:** 4.5–20 VDC (DS)
- **Power consumption:** Quiescent < 65 µA (DS)
- **Communication:** GPIO digital output (DS)
- **Operating temperature:** −15 °C to +70 °C (DS)
- **Environmental limitations:** Hobby-grade; sunlight, heaters and animals cause false triggers; not weatherproof. Use an outdoor-rated dual-tech detector in deployment.
- **Approx. price:** ₹60 – ₹150 (EST)
- **Advantages:** Very cheap; Very low power
- **Disadvantages:** Short range; No localisation; Not outdoor-rated
- **Integration:** ESP32/Pi GPIO with debounce; enclosure required; supervised (EOL) wiring in production.
- **Alternatives:** Panasonic PaPIRs EKMC series; Outdoor dual-technology (PIR + microwave) detectors

| Specification | Value | Source |
|---|---|---|
| Detection range | up to ≈ 7 m (adjustable) | DS |
| Detection angle | < 120° cone | DS |
| Output | 3.3 V TTL high on motion | DS |
| Delay | ≈ 0.3 s – 5 min adjustable | DS |

#### Microwave Doppler motion sensor module — Generic (RCWL) RCWL-0516

- **Category:** Perimeter sensors / Microwave motion sensor
- **Working principle:** Single-transistor oscillator around 3.2 GHz radiates continuously; motion Doppler-shifts the reflection, and the mixer output is amplified and thresholded by the RCWL-9196 IC.
- **Internal components:** ≈ 3.2 GHz oscillator / PCB antenna; RCWL-9196 processor; 3.3 V regulator
- **Operating voltage:** 4–28 VDC (DS)
- **Power consumption:** ≈ 2.8 mA (DS)
- **Communication:** GPIO digital output (DS)
- **Operating temperature:** −20 °C to +80 °C (EST)
- **Environmental limitations:** Penetrates thin walls/plastic (can detect beyond the intended area); RF regulatory status must be checked.
- **Approx. price:** ₹50 – ₹150 (EST)
- **Advantages:** Cheap, works through enclosures; Insensitive to temperature
- **Disadvantages:** Omnidirectional — poor area control; Hobby-grade
- **Integration:** Cross-validate with PIR (dual-tech AND logic) at the gate.
- **Alternatives:** 24 GHz K-band radar modules; Dual-tech detectors

| Specification | Value | Source |
|---|---|---|
| Detection range | ≈ 5–7 m | DS |
| Output | 3.3 V TTL | DS |
| Frequency | ≈ 3.18 GHz | EST |

Sources: [RCWL-0516 community documentation](https://github.com/jdesbonnet/RCWL-0516)

#### Fence-mounted vibration node (low-noise MEMS accelerometer) — Analog Devices ADXL355

- **Category:** Perimeter sensors / Fence vibration sensor
- **Working principle:** 3-axis MEMS accelerometer clamped to fence fabric senses climbing/cutting vibration; the node computes RMS and spectral features and raises an alarm above a threshold (simulated threshold 0.3 g).
- **Internal components:** 3-axis MEMS accelerometer; 20-bit ADC; Digital filters / FIFO; SPI/I²C interface
- **Operating voltage:** 2.25–3.6 V (DS)
- **Power consumption:** ≈ 200 µA (DS)
- **Communication:** SPI / I²C → local MCU, RS-485 Modbus RTU to edge (EST design)
- **Operating temperature:** −40 °C to +125 °C (DS)
- **Environmental limitations:** Wind, rain and passing traffic excite the fence — requires wind compensation (VIPER rule R3) and per-segment tuning.
- **Approx. price:** ₹3,500 – ₹6,000 (EST)
- **Advantages:** Very sensitive; Cheap per segment for a pilot
- **Disadvantages:** DIY integration; commercial fence processors are far more mature
- **Integration:** One node per fence segment, daisy-chained on isolated RS-485 to the side edge node.
- **Alternatives:** Senstar FlexZone (commercial sensor cable); Fibre-optic fence sensing (DAS)

| Specification | Value | Source |
|---|---|---|
| Noise density | ≈ 22.5 µg/√Hz | DS |
| Range | ±2 / ±4 / ±8 g | DS |
| ADC | 20-bit | DS |

Sources: [ADXL355 product page](https://www.analog.com/en/products/adxl355.html); [Senstar FlexZone](https://senstar.com/products/fence-sensors/)

#### Surface magnetic door/gate contact — Generic MC-38

- **Category:** Perimeter sensors / Magnetic contact sensor
- **Working principle:** Reed switch closes when the paired magnet is within the gap distance; opening the gate separates the magnet and opens the loop.
- **Internal components:** Glass reed switch; Permanent magnet; ABS housing
- **Operating voltage:** Passive (loop powered by input, e.g. 3.3–12 V) (EST)
- **Power consumption:** Negligible
- **Communication:** Dry contact (EST)
- **Operating temperature:** ≈ −10 °C to +50 °C (EST)
- **Environmental limitations:** Hobby-grade contacts are easily defeated with a magnet; use heavy-duty supervised contacts with EOL resistors.
- **Approx. price:** ₹80 – ₹250 (EST)
- **Advantages:** Simple, reliable state signal
- **Disadvantages:** No tamper resistance (hobby grade)
- **Integration:** Wired to gate node with end-of-line resistor so cut/short is distinguishable from open (fault detection).
- **Alternatives:** Heavy-duty steel-door contacts (industrial); Gate operator limit switches

| Specification | Value | Source |
|---|---|---|
| Contact type | Normally closed (with magnet) | EST |
| Operating gap | ≈ 15–25 mm | EST |

#### 60–64 GHz mmWave radar sensor — Texas Instruments IWR6843

- **Category:** Perimeter sensors / Radar-based detection
- **Working principle:** FMCW chirps from 3 TX antennas are received on 4 RX; range from beat frequency, velocity from Doppler, angle from phase across antennas. On-chip DSP builds a point cloud and tracks.
- **Internal components:** 60–64 GHz RF front end (3 TX / 4 RX); ARM Cortex-R4F; C674x DSP; Hardware accelerator
- **Operating voltage:** 3.3 V / 1.8 V / 1.2 V rails (eval board from 5 V) (DS)
- **Power consumption:** ≈ 1–2 W board level (EST)
- **Communication:** UART / SPI / CAN (DS)
- **Operating temperature:** −40 °C to +105 °C (junction) (DS)
- **Environmental limitations:** Short range for perimeter use; multipath from fences; commercial perimeter radars reach hundreds of metres.
- **Approx. price:** ₹15,000 – ₹35,000 (EST)
- **Advantages:** Works in dark/fog; Gives range and velocity
- **Disadvantages:** Short range dev part; Needs tuning
- **Integration:** Prototype only; production would use a commercial perimeter radar with ONVIF/JSON track output.
- **Alternatives:** Navtech / SpotterRF / Magos perimeter radars; Infineon BGT60 series

| Specification | Value | Source |
|---|---|---|
| Frequency band | 60–64 GHz | DS |
| Antennas | 3 TX, 4 RX | DS |
| People detection range (eval board) | ≈ tens of metres | EST |
| Simulated perimeter radar range | 260 m — represents a commercial ground-surveillance radar | EST |

Sources: [TI IWR6843](https://www.ti.com/product/IWR6843)

### Environmental sensors

#### Digital temperature & humidity sensor — Sensirion SHT31

- **Category:** Environmental sensors / Temperature / humidity
- **Working principle:** CMOSens chip with capacitive humidity element and band-gap temperature sensor; factory calibrated, digital output.
- **Internal components:** Capacitive RH sensor; Band-gap temperature sensor; ADC + calibration memory; I²C
- **Operating voltage:** 2.15–5.5 V (DS)
- **Power consumption:** ≈ 2 µW average at 1 Hz (EST)
- **Communication:** I²C (DS)
- **Operating temperature:** −40 °C to +125 °C (DS)
- **Environmental limitations:** Needs a radiation shield outdoors; condensation affects RH.
- **Approx. price:** ₹300 – ₹700 (EST)
- **Advantages:** Accurate; Low power
- **Disadvantages:** I²C distance limits
- **Integration:** ESP32 I²C; reported over LoRaWAN every 60 s (sim reports every tick for visualisation).
- **Alternatives:** Bosch BME280; Maxim DS18B20 (temperature only)

| Specification | Value | Source |
|---|---|---|
| Temperature accuracy | ±0.2 °C typical (0–90 °C) | DS |
| RH accuracy | ±2 %RH typical | DS |
| Interface | I²C (0x44/0x45) | DS |

Sources: [Sensirion SHT3x](https://sensirion.com/products/catalog/SHT31-DIS-B)

#### Temperature, humidity & pressure sensor — Bosch Sensortec BME280

- **Category:** Environmental sensors / Environmental anomaly sensor
- **Working principle:** MEMS pressure sensor, capacitive humidity sensor and temperature sensor in one package.
- **Internal components:** Piezo-resistive pressure; Capacitive humidity; Temperature diode; I²C/SPI
- **Operating voltage:** 1.71–3.6 V (DS)
- **Power consumption:** ≈ 3.6 µA at 1 Hz (H, T) (DS)
- **Communication:** I²C / SPI (DS)
- **Operating temperature:** −40 °C to +85 °C (DS)
- **Environmental limitations:** Self-heating in enclosures.
- **Approx. price:** ₹250 – ₹600 (EST)
- **Advantages:** Three measurands, tiny
- **Disadvantages:** Lower RH accuracy than SHT31
- **Integration:** Shares the ESP32 I²C bus.
- **Alternatives:** SHT31

| Specification | Value | Source |
|---|---|---|
| Pressure range | 300–1100 hPa | DS |
| Humidity accuracy | ±3 %RH | DS |
| Interface | I²C / SPI | DS |

Sources: [Bosch BME280](https://www.bosch-sensortec.com/products/environmental-sensors/humidity-sensors-bme280/)

#### 1-Wire digital thermometer — Analog Devices (Maxim) DS18B20

- **Category:** Environmental sensors / Temperature sensor
- **Working principle:** Band-gap temperature sensor with 9–12-bit ADC on a 1-Wire bus; many sensors share one data line.
- **Internal components:** Temperature sensor; ADC; 64-bit ROM ID; 1-Wire interface
- **Operating voltage:** 3.0–5.5 V (DS)
- **Power consumption:** ≈ 1 mA during conversion (DS)
- **Communication:** 1-Wire (DS)
- **Operating temperature:** −55 °C to +125 °C (DS)
- **Environmental limitations:** Cable length limits on 1-Wire.
- **Approx. price:** ₹80 – ₹200 (EST)
- **Advantages:** Waterproof probes available; Multi-drop
- **Disadvantages:** Slow (750 ms @12-bit)
- **Integration:** Transformer/cable-trench surface temperature in a pilot.
- **Alternatives:** PT100 with MAX31865

| Specification | Value | Source |
|---|---|---|
| Range | −55 °C to +125 °C | DS |
| Accuracy | ±0.5 °C (−10 to +85 °C) | DS |
| Resolution | 9–12 bit | DS |

Sources: [DS18B20](https://www.analog.com/en/products/ds18b20.html)

#### Conventional photoelectric smoke detector — Various — must be EN 54-7 / UL 268 certified Model to be selected

- **Category:** Environmental sensors / Smoke detection
- **Working principle:** IR LED and photodiode in a dark labyrinth chamber; smoke particles scatter light onto the photodiode.
- **Internal components:** Optical chamber; IR LED + photodiode; Detector ASIC; Base with alarm relay/current step
- **Operating voltage:** Typically 12–24 VDC loop (EST)
- **Power consumption:** ≈ < 100 µA standby (EST)
- **Communication:** Conventional zone loop / relay (EST)
- **Operating temperature:** ≈ −10 °C to +55 °C (EST)
- **Environmental limitations:** Dust, steam and insects cause nuisance alarms; outdoor tank farms need flame/heat detection instead.
- **Approx. price:** ₹600 – ₹2,500 (EST)
- **Advantages:** Certified life-safety device
- **Disadvantages:** Not suitable for open outdoor areas
- **Integration:** VIPER only monitors the fire panel/relay status; it never replaces the certified fire alarm system.
- **Alternatives:** Aspirating smoke detection (VESDA); UV/IR flame detectors for tank farms

| Specification | Value | Source |
|---|---|---|
| Alarm threshold (simulated) | 2.0 %obs/m | EST |
| Certification | EN 54-7 / UL 268 required | EST |

#### Water / liquid leak-detection cable — Various (e.g. TTK, RLE) Model to be selected

- **Category:** Environmental sensors / Water leakage detection
- **Working principle:** Two conductors separated by a porous braid; liquid bridges them and the controller measures the change in resistance (some locate the leak position).
- **Internal components:** Sensing cable; Controller with relay/Modbus output
- **Operating voltage:** 12–24 VDC controller (EST)
- **Power consumption:** < 2 W (EST)
- **Communication:** Relay / Modbus RTU (EST)
- **Operating temperature:** ≈ 0 °C to +50 °C (EST)
- **Environmental limitations:** Standard cables do not detect non-conductive hydrocarbons — use hydrocarbon-sensing cable at fuel facilities.
- **Approx. price:** ₹3,000 – ₹15,000 (EST)
- **Advantages:** Covers long runs
- **Disadvantages:** Specific liquid types only
- **Integration:** Relay into ESP32 input or Modbus to edge node.
- **Alternatives:** Spot float switches; Hydrocarbon-sensing cable

| Specification | Value | Source |
|---|---|---|
| Detection | Conductive liquids (hydrocarbon variants exist) | EST |

### Edge computing

#### Edge AI computer — NVIDIA Jetson Orin Nano 8 GB (Developer Kit)

- **Category:** Edge computing / GPU edge AI module
- **Working principle:** Ampere GPU with tensor cores runs DNN object detection (e.g. YOLO-class models via TensorRT) on several camera streams; ARM CPUs run tracking, MQTT client and store-and-forward buffer.
- **Internal components:** 6-core Arm Cortex-A78AE CPU; 1024-core Ampere GPU, 32 tensor cores; 8 GB LPDDR5; NVMe via M.2
- **Operating voltage:** Dev kit 19 VDC barrel (DS)
- **Power consumption:** 7–25 W (DS)
- **Communication:** Gigabit Ethernet, M.2 Wi-Fi, USB, CSI (DS)
- **Operating temperature:** Module −25 °C to +80 °C (DS); dev kit is not ruggedised
- **Environmental limitations:** Needs a sealed, thermally managed enclosure outdoors; SD/NVMe wear.
- **Approx. price:** ₹25,000 – ₹40,000 (EST)
- **Advantages:** Real-time multi-camera DNN inference; Mature SDK (JetPack, DeepStream)
- **Disadvantages:** Higher power than Pi; Cost
- **Integration:** One per perimeter side; PoE switch, UPS-backed 19 V supply, NTP client, MQTT/TLS uplink.
- **Alternatives:** Jetson Orin NX; Hailo-8 accelerator on Raspberry Pi 5; Industrial MIC-711

| Specification | Value | Source |
|---|---|---|
| AI performance | 40 TOPS (up to 67 TOPS with JetPack 6.2 'Super' mode) | DS |
| Memory | 8 GB 128-bit LPDDR5 | DS |
| Power modes | 7 W – 15 W (25 W Super) | DS |
| Camera streams (1080p detection) | ≈ 4–8 depending on model | EST |

Sources: [NVIDIA Jetson Orin Nano Developer Kit](https://developer.nvidia.com/embedded/learn/get-started-jetson-orin-nano-devkit)

#### Single-board computer — Raspberry Pi Ltd Raspberry Pi 5 (4/8 GB)

- **Category:** Edge computing / General-purpose edge node
- **Working principle:** Quad-core ARM SoC runs Linux; aggregates GPIO dry contacts (gate contact, PIR, microwave), the access-control feed and one or two camera streams with light analytics.
- **Internal components:** Broadcom BCM2712 quad Cortex-A76 @ 2.4 GHz; VideoCore VII GPU; LPDDR4X; RP1 I/O controller; PCIe 2.0 ×1
- **Operating voltage:** 5 V / 5 A USB-C PD (DS)
- **Power consumption:** ≈ 3–12 W (EST)
- **Communication:** Ethernet, Wi-Fi, GPIO, I²C, SPI, UART (DS)
- **Operating temperature:** 0 °C to +50 °C ambient (DS)
- **Environmental limitations:** Commercial temperature range; needs active cooling and conformal protection outdoors.
- **Approx. price:** ₹6,500 – ₹10,000 (EST)
- **Advantages:** Low cost; Huge ecosystem; GPIO for dry contacts
- **Disadvantages:** Limited AI without accelerator; Commercial temp range
- **Integration:** Gate node: GPIO with opto-isolation; optional Hailo-8L AI HAT+ for ANPR.
- **Alternatives:** Jetson Orin Nano; Industrial Pi-based CM5 carriers

| Specification | Value | Source |
|---|---|---|
| CPU | 4 × Cortex-A76 @ 2.4 GHz | DS |
| Networking | Gigabit Ethernet, dual-band Wi-Fi 5, BT 5.0 | DS |
| Interfaces | 40-pin GPIO, 2 × MIPI CSI/DSI, PCIe 2.0 ×1 | DS |

Sources: [Raspberry Pi 5](https://www.raspberrypi.com/products/raspberry-pi-5/)

#### Wi-Fi/BT microcontroller module — Espressif ESP32-WROOM-32E

- **Category:** Edge computing / Low-power sensor node
- **Working principle:** Dual-core MCU reads I²C/1-Wire/ADC sensors, applies thresholds and transmits compact readings via an SX1276 LoRa radio (LoRaWAN) or Wi-Fi; deep-sleeps between samples on solar/battery power.
- **Internal components:** Xtensa dual-core LX6 up to 240 MHz; 520 KB SRAM; 4–16 MB flash; Wi-Fi 802.11 b/g/n; Bluetooth v4.2 + BLE
- **Operating voltage:** 3.0–3.6 V (DS)
- **Power consumption:** ≈ 80–240 mA active Wi-Fi TX peaks; µA in deep sleep (EST)
- **Communication:** Wi-Fi, BLE, UART, SPI, I²C (DS)
- **Operating temperature:** −40 °C to +85 °C (DS)
- **Environmental limitations:** Clock drift ±(tens of ppm) — VIPER corrects node clock offset at ingest.
- **Approx. price:** ₹400 – ₹900 (EST)
- **Advantages:** Very cheap; Low power
- **Disadvantages:** No heavy analytics; Limited security without secure boot/flash encryption configured
- **Integration:** Environmental nodes with SHT31/smoke relay/leak input + RFM95W (SX1276) LoRa radio on IN865.
- **Alternatives:** ESP32-S3; STM32WL (integrated LoRa)

| Specification | Value | Source |
|---|---|---|
| CPU | Dual-core 32-bit LX6, up to 240 MHz | DS |
| Wi-Fi | 802.11 b/g/n 2.4 GHz | DS |
| Deep-sleep current | ≈ 10 µA class (module dependent) | EST |

Sources: [ESP32-WROOM-32E datasheet](https://www.espressif.com/en/products/modules/esp32)

#### Industrial fanless AI edge computer — Advantech MIC-711 (Jetson-based)

- **Category:** Edge computing / Industrial edge computer
- **Working principle:** Jetson Orin module in a fanless, wide-temperature, industrially certified chassis with isolated I/O.
- **Internal components:** Jetson Orin Nano/NX module; Fanless chassis; Wide-range DC input; Industrial I/O
- **Operating voltage:** ≈ 12–24 VDC (EST)
- **Power consumption:** ≈ 15–30 W (EST)
- **Communication:** GbE, USB, COM/RS-485 (EST)
- **Operating temperature:** ≈ −10 °C to +60 °C (EST — verify)
- **Environmental limitations:** Higher cost; vendor lead times.
- **Approx. price:** ₹80,000 – ₹1,60,000 (EST)
- **Advantages:** Ruggedised, certified for field cabinets
- **Disadvantages:** Cost
- **Integration:** Production replacement for dev-kit Jetsons in roadside/perimeter cabinets.
- **Alternatives:** Siemens SIMATIC IPC; Moxa UC series

| Specification | Value | Source |
|---|---|---|
| Compute | Jetson Orin Nano / NX variants | EST |
| Cooling | Fanless | EST |

Sources: [Advantech AI edge systems](https://www.advantech.com/en/products/edge-ai-systems)

### Communication

#### Gigabit PoE+ network switch — Various (e.g. TP-Link, Moxa industrial) Model to be selected

- **Category:** Communication / Ethernet
- **Working principle:** Layer-2 switch forwarding Ethernet frames between cameras, edge nodes and uplink; PSE ports supply 48 V DC power over the data cable to cameras (IEEE 802.3af/at).
- **Internal components:** Switch ASIC; PoE PSE controllers; 48 V PSU
- **Operating voltage:** 100–240 VAC or 48 VDC (EST)
- **Power consumption:** Budget + ≈ 10 W (EST)
- **Communication:** IEEE 802.3, VLAN 802.1Q, 802.1X (EST)
- **Operating temperature:** Commercial 0–40 °C; industrial −40 to +75 °C (EST)
- **Environmental limitations:** Outdoor cabinets need industrial temperature rating.
- **Approx. price:** ₹4,000 – ₹25,000 (EST)
- **Advantages:** Single cable power + data; Deterministic latency
- **Disadvantages:** Copper limited to 100 m
- **Integration:** Per-side cabinet; fibre uplink to C2 where > 100 m.
- **Alternatives:** Industrial managed switches (Moxa, Hirschmann)

| Specification | Value | Source |
|---|---|---|
| PoE standard | 802.3af/at | EST |
| Power budget | ≈ 60–120 W (model dependent) | EST |

#### LoRa transceiver module — HopeRF (Semtech SX1276 inside) RFM95W

- **Category:** Communication / LoRaWAN
- **Working principle:** Chirp-spread-spectrum modulation trades data rate for sensitivity, giving km-range links at very low power; LoRaWAN MAC handles join, encryption (AES-128) and ADR.
- **Internal components:** Semtech SX1276 transceiver; TCXO/crystal; Matching network
- **Operating voltage:** 1.8–3.7 V (DS)
- **Power consumption:** ≈ 120 mA TX @ +20 dBm; ≈ 10 mA RX (DS)
- **Communication:** SPI to MCU; LoRaWAN over air (DS)
- **Operating temperature:** −40 °C to +85 °C (DS)
- **Environmental limitations:** Duty-cycle limits; latency 0.4–1.6 s simulated (airtime + gateway + network server).
- **Approx. price:** ₹700 – ₹1,500 (EST)
- **Advantages:** Long range, low power
- **Disadvantages:** Low throughput, high latency — unsuitable for video
- **Integration:** Environmental ESP32 nodes → LoRaWAN gateway at C2 → local network server (ChirpStack) → MQTT.
- **Alternatives:** STM32WL; RAK3172

| Specification | Value | Source |
|---|---|---|
| Frequency | 868/915 MHz variants; India uses IN865 (865–867 MHz) | DS |
| Max TX power | +20 dBm | DS |
| Sensitivity | down to −148 dBm | DS |

Sources: [Semtech SX1276](https://www.semtech.com/products/wireless-rf/lora-connect/sx1276)

#### LTE Cat 4 module — Quectel EC25 series

- **Category:** Communication / 4G/5G
- **Working principle:** Cellular modem providing an IP uplink where cabling is impractical; used here for a remote perimeter side.
- **Internal components:** LTE baseband + RF; GNSS (variant); USB 2.0 / UART
- **Operating voltage:** 3.3–4.3 V (DS)
- **Power consumption:** Peaks ≈ 2 A at TX (EST)
- **Communication:** USB / UART, PPP/QMI (DS)
- **Operating temperature:** −35 °C to +75 °C operating (EST)
- **Environmental limitations:** Carrier coverage/latency variable (40–140 ms simulated); use private APN + VPN.
- **Approx. price:** ₹2,500 – ₹5,000 (EST)
- **Advantages:** No trenching; Fast deployment
- **Disadvantages:** Recurring cost, variable latency, jamming exposure
- **Integration:** Backup or remote-side uplink with IPsec/WireGuard to C2.
- **Alternatives:** Quectel RM5xx (5G); Sierra Wireless

| Specification | Value | Source |
|---|---|---|
| Category | LTE Cat 4 (150 Mbps DL / 50 Mbps UL) | DS |

Sources: [Quectel EC25](https://www.quectel.com/product/lte-ec25-series/)

#### Isolated RS-485 transceiver — Analog Devices ADM2587E

- **Category:** Communication / RS-485
- **Working principle:** Differential half/full-duplex bus robust to noise over long cables; integrated isoPower DC-DC and iCoupler isolation protect the edge node from ground potential differences along a fence line.
- **Internal components:** RS-485 transceiver; iCoupler digital isolators; isoPower DC-DC
- **Operating voltage:** 3.3 V or 5 V (DS)
- **Power consumption:** ≈ < 100 mA (EST)
- **Communication:** RS-485 (Modbus RTU on top) (DS)
- **Operating temperature:** −40 °C to +85 °C (DS)
- **Environmental limitations:** Requires termination and biasing; bus length/speed trade-off (≈ 1200 m at low rates).
- **Approx. price:** ₹600 – ₹1,200 (EST)
- **Advantages:** Long cable runs, multi-drop; Isolation protects electronics
- **Disadvantages:** Low bandwidth
- **Integration:** Fence vibration nodes on a Modbus RTU bus to each side's edge node.
- **Alternatives:** MAX485 (non-isolated); THVD1450

| Specification | Value | Source |
|---|---|---|
| Isolation | 2.5 kV rms | DS |
| Data rate | up to 500 kbps | DS |
| ESD | ±15 kV on bus pins | DS |

Sources: [ADM2587E](https://www.analog.com/en/products/adm2587e.html)

#### MQTT broker (software) — Eclipse Foundation Mosquitto 2.x

- **Category:** Communication / MQTT
- **Working principle:** Publish/subscribe message broker; edge nodes publish observations to topics (viper/<site>/<node>/obs) with QoS 1; the fusion service subscribes. Lightweight, TLS + client certificates.
- **Internal components:** Broker daemon; TLS; ACL / auth plugins
- **Operating voltage:** n/a (software)
- **Power consumption:** n/a
- **Communication:** MQTT over TCP/TLS, WebSockets (DS)
- **Operating temperature:** n/a
- **Environmental limitations:** Single broker is a SPOF — run a bridged pair in production.
- **Approx. price:** open source / n/a
- **Advantages:** Open source; Tiny footprint
- **Disadvantages:** Clustering needs extra work
- **Integration:** In this demonstrator the in-process delivery queue stands in for the broker (QoS 1 retransmit modelled).
- **Alternatives:** EMQX; HiveMQ CE

| Specification | Value | Source |
|---|---|---|
| Protocol | MQTT 3.1.1 / 5.0 | DS |

Sources: [Eclipse Mosquitto](https://mosquitto.org/)

### Power systems

#### Enclosed AC-DC power supply 100 W / 12 V — MEAN WELL LRS-100-12

- **Category:** Power systems / AC power supply
- **Working principle:** Switch-mode converter: rectifies mains, high-frequency switching through a transformer, regulated 12 V output.
- **Internal components:** EMI filter; PFC-less SMPS stage; Transformer; Output regulation & protections
- **Operating voltage:** 85–264 VAC in, 12 VDC out (DS)
- **Power consumption:** Efficiency ≈ 88–89 % (DS)
- **Communication:** n/a
- **Operating temperature:** −30 °C to +70 °C (derating) (DS)
- **Environmental limitations:** Enclosed, not weatherproof — cabinet mounting.
- **Approx. price:** ₹1,200 – ₹2,200 (EST)
- **Advantages:** Reliable, cheap
- **Disadvantages:** No battery management
- **Integration:** Feeds 12 V DC bus in each cabinet downstream of the UPS.
- **Alternatives:** MEAN WELL DIN-rail HDR/NDR series

| Specification | Value | Source |
|---|---|---|
| Output | 12 V / 8.5 A (102 W) | DS |
| Input range | 85–264 VAC | DS |

Sources: [MEAN WELL LRS-100](https://www.meanwell.com/productSeries.aspx)

#### DC-DC buck converter module — Generic (TI LM2596-based) LM2596 module

- **Category:** Power systems / DC power supply
- **Working principle:** Switching step-down regulator converts the 12 V bus to 5 V for sensors/MCUs.
- **Internal components:** LM2596 regulator; Inductor; Schottky diode; Capacitors
- **Operating voltage:** 4.5–40 VDC (DS)
- **Power consumption:** Efficiency ≈ 75–90 % (EST)
- **Communication:** n/a
- **Operating temperature:** −40 °C to +125 °C junction (DS)
- **Environmental limitations:** Cheap modules vary in quality.
- **Approx. price:** ₹100 – ₹250 (EST)
- **Advantages:** Cheap
- **Disadvantages:** Ripple/EMI
- **Integration:** 5 V rail for ESP32 cabinets.
- **Alternatives:** Industrial DC-DC (MEAN WELL DDR)

| Specification | Value | Source |
|---|---|---|
| Input | 4.5–40 V | DS |
| Output current | up to 3 A (with heatsinking) | DS |

Sources: [TI LM2596](https://www.ti.com/product/LM2596)

#### Line-interactive UPS 1500 VA — Schneider Electric (APC) Smart-UPS SMT1500IC

- **Category:** Power systems / UPS
- **Working principle:** Line-interactive topology: automatic voltage regulation on mains; on outage the inverter supplies sine-wave output from internal VRLA batteries. Network card reports status (SNMP) to the C2.
- **Internal components:** Inverter/charger; AVR transformer; VRLA batteries; SmartConnect/network management
- **Operating voltage:** 230 VAC nominal (DS)
- **Power consumption:** Runtime depends on load (≈ 15–25 min at ≈ 300 W) (EST)
- **Communication:** USB, serial, SmartConnect / SNMP card (DS)
- **Operating temperature:** 0 °C to +40 °C (DS)
- **Environmental limitations:** Battery life shortens rapidly above 25 °C — cabinet cooling needed.
- **Approx. price:** ₹45,000 – ₹75,000 (EST)
- **Advantages:** Clean sine output; Remote monitoring
- **Disadvantages:** Indoor-rated
- **Integration:** Command-centre UPS; SNMP traps → VIPER power monitor (power events, rule P1).
- **Alternatives:** Online double-conversion UPS; DC UPS for cabinets

| Specification | Value | Source |
|---|---|---|
| Capacity | 1500 VA / 1000 W | DS |
| Waveform on battery | Sine wave | DS |

Sources: [APC Smart-UPS](https://www.apc.com/)

#### 12 V 7 Ah VRLA battery — Yuasa NP7-12

- **Category:** Power systems / Battery backup
- **Working principle:** Sealed lead-acid AGM battery storing energy for cabinet DC backup.
- **Internal components:** Lead plates; AGM separators; Pressure-relief valve
- **Operating voltage:** 12 V (DS)
- **Power consumption:** n/a
- **Communication:** n/a
- **Operating temperature:** ≈ −15 °C to +50 °C discharge (EST)
- **Environmental limitations:** Capacity drops in cold, life drops in heat.
- **Approx. price:** ₹1,200 – ₹2,200 (EST)
- **Advantages:** Cheap, robust
- **Disadvantages:** Heavy; limited cycles
- **Integration:** Per-cabinet DC backup with a charger/DC-UPS module.
- **Alternatives:** LiFePO4 12 V packs

| Specification | Value | Source |
|---|---|---|
| Nominal | 12 V, 7 Ah (20 h rate) | DS |

Sources: [Yuasa NP series](https://www.yuasa.co.uk/)

#### Solar MPPT charge controller — Victron Energy SmartSolar MPPT 75/15

- **Category:** Power systems / Solar-assisted power
- **Working principle:** Maximum-power-point tracking DC-DC converter harvests PV power and charges the node battery; Bluetooth/VE.Direct telemetry.
- **Internal components:** MPPT buck converter; Battery charge algorithm; Bluetooth; VE.Direct port
- **Operating voltage:** 12/24 V battery (DS)
- **Power consumption:** Self-consumption ≈ tens of mA (EST)
- **Communication:** VE.Direct serial, Bluetooth (DS)
- **Operating temperature:** −30 °C to +60 °C (DS)
- **Environmental limitations:** PV sizing must cover monsoon low-irradiance weeks.
- **Approx. price:** ₹7,000 – ₹11,000 (EST)
- **Advantages:** Off-grid nodes, telemetry
- **Disadvantages:** Cost vs PWM controllers
- **Integration:** Powers remote ESP32/LoRaWAN environmental nodes (PV-1 in the power schematic).
- **Alternatives:** PWM controllers (cheap)

| Specification | Value | Source |
|---|---|---|
| Max PV open-circuit voltage | 75 V | DS |
| Charge current | 15 A | DS |
| Battery | 12/24 V | DS |

Sources: [Victron SmartSolar](https://www.victronenergy.com/solar-charge-controllers)

#### High-side current/power monitor — Texas Instruments INA219

- **Category:** Power systems / Power monitoring
- **Working principle:** Measures voltage across a shunt resistor and the bus voltage; computes current and power for each DC rail.
- **Internal components:** Shunt amplifier; 12-bit ADC; I²C
- **Operating voltage:** 3–5.5 V (DS)
- **Power consumption:** ≈ 1 mA (DS)
- **Communication:** I²C (DS)
- **Operating temperature:** −40 °C to +125 °C (DS)
- **Environmental limitations:** Needs correct shunt sizing.
- **Approx. price:** ₹150 – ₹400 (EST)
- **Advantages:** Cheap per-rail telemetry
- **Disadvantages:** Low-side voltage limit 26 V
- **Integration:** Cabinet DC rails → edge node → power health telemetry.
- **Alternatives:** INA226; PZEM-004T (AC)

| Specification | Value | Source |
|---|---|---|
| Bus voltage | 0–26 V | DS |
| ADC | 12-bit | DS |

Sources: [TI INA219](https://www.ti.com/product/INA219)

## 5. Selection rationale

### Edge computing — why three node classes

| Option | Compute | Power | Cost (INR, EST) | VIPER role |
|---|---|---|---|---|
| Jetson Orin Nano | 40–67 TOPS GPU (DS) | 7–25 W (DS) | 25k–40k | Camera-heavy perimeter sides: multi-stream DNN |
| Raspberry Pi 5 | 4 × A76 CPU, no NPU (DS) | ≈ 3–12 W (EST) | 6.5k–10k | Gate: dry contacts, access-control feed, light analytics |
| ESP32 + SX1276 | MCU (DS) | mW average (EST) | 0.4k–2k | Solar environmental nodes over LoRaWAN |
| Industrial MIC-711 | Jetson Orin in rugged box (EST) | 15–30 W (EST) | 80k–160k | Production replacement for dev kits |

**Conclusion:** Match compute to data: video needs a GPU at the edge (sending raw video centrally costs bandwidth and latency); contacts and slow environmental values do not.

### Thermal sensing

| Option | Resolution | Typical human range | Cost (INR, EST) | Use |
|---|---|---|---|---|
| Perimeter thermal bullet | ≈ 384 × 288 (EST) | 300–600 m (EST) | 1.2–4 lakh | Fence lines (simulated TH-xx) |
| FLIR Lepton 3.5 | 160 × 120 (DS) | tens of m (EST) | 18k–30k | Prototype / hotspot monitoring |
| MLX90640 | 32 × 24 (DS) | few m (EST) | 4.5k–8k | Equipment rooms |
| AMG8833 | 8 × 8 (DS) | ≤ 7 m (DS) | 2.5k–4.5k | Indoor occupancy cross-check |

**Conclusion:** Only commercial uncooled cores reach perimeter ranges; low-cost arrays are used for short-range and equipment hotspot detection in the pilot.

### Perimeter intrusion modalities (cross-validation)

| Modality | Strength | Typical nuisance source | Paired with |
|---|---|---|---|
| Fence vibration | Detects climbing/cutting at the barrier | Wind, rain, traffic | Thermal / optical (rule R6) + wind compensation (R3) |
| Thermal | Darkness, long range | Animals, thermal crossover | Optical classification (R2 vote) |
| Optical | Identification, colour evidence | Low light, glare, shadows | Thermal |
| Radar | Range + velocity, all weather | Vegetation movement, multipath | Camera slew for verification |
| PIR / microwave | Cheap point detection | Heat sources / RF penetration | Each other (dual-tech) |
| Magnetic contact | Unambiguous open/closed state | Mis-adjusted gates | Access-control credential |

**Conclusion:** No single modality is trusted alone; VIPER escalates only when independent modalities agree, and always routes the decision to a human.

### Uplink technologies

| Link | Simulated one-way latency | Loss (sim) | Use |
|---|---|---|---|
| Fibre / Ethernet | 1–4 ms | 0 % | Camera-heavy sides, C2 LAN |
| Wi-Fi PtP bridge | 4–25 ms | 0.5 % | Where trenching is impractical |
| 4G LTE | 40–140 ms | 1 % | Remote side, backup path |
| LoRaWAN IN865 | 400–1600 ms | 2 % | Environmental telemetry only |
| RS-485 Modbus | intra-cabinet bus | — | Fence processors → edge node |

**Conclusion:** Latency figures are simulation parameters chosen to be representative; they must be measured in a pilot.
