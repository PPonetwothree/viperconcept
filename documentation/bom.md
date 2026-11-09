# VIPER — Preliminary Bill of Materials (pilot, one site)

Layout basis: **Airport perimeter** simulated layout (31 sensors, 6 edge nodes).

> **All prices are estimates (EST)** — indicative Indian market ranges, ex-GST, before integration, civil works, cabling, enclosures, licences and installation labour. Unit price shown = midpoint of the estimated range. Obtain distributor/integrator quotations before budgeting. Several entries are development-grade parts suitable for a lab pilot only (see Devices → Disadvantages); production would substitute ruggedised equivalents.

| Component | Qty | Unit price (EST) | Total (EST) | Manufacturer | Model | Purpose | Source link |
|---|---|---|---|---|---|---|---|
| 4 MP fixed bullet IP camera (AcuSense) | 4 | ₹9,500 | ₹38,000 | Hikvision | DS-2CD2043G2-I | Optical (IP CCTV) | https://www.hikvision.com/en/products/IP-Products/Network-Cameras/ |
| Fixed thermal bullet camera (perimeter class) | 4 | ₹2,60,000 | ₹10,40,000 | Various (model to be selected) | e.g. Hikvision DS-2TD26xx / Axis Q19xx / Teledyne FLIR FC-Series | Thermal | https://www.flir.com/security/ |
| Fence-mounted vibration node (low-noise MEMS accelerometer) | 8 | ₹4,750 | ₹38,000 | Analog Devices | ADXL355 | Fence vibration | https://www.analog.com/en/products/adxl355.html |
| 60–64 GHz mmWave radar sensor | 2 | ₹25,000 | ₹50,000 | Texas Instruments | IWR6843 | Perimeter radar | https://www.ti.com/product/IWR6843 |
| Surface magnetic door/gate contact | 1 | ₹165 | ₹165 | Generic | MC-38 | Magnetic contact | — (generic; obtain quotation) |
| PIR motion sensor module | 2 | ₹105 | ₹210 | Generic (BISS0001-based) | HC-SR501 | PIR motion | — (generic; obtain quotation) |
| Microwave Doppler motion sensor module | 2 | ₹100 | ₹200 | Generic (RCWL) | RCWL-0516 | Microwave motion | https://github.com/jdesbonnet/RCWL-0516 |
| 4 MP 25× IR PTZ dome | 1 | ₹52,500 | ₹52,500 | Hikvision | DS-2DE4425IW-DE | PTZ camera | https://www.hikvision.com/en/products/IP-Products/PTZ-Cameras/ |
| 4 MP ColorVu fixed bullet camera (low-light, wide-angle) | 1 | ₹9,500 | ₹9,500 | Hikvision | DS-2CD2047G2-L | Low-light wide-angle camera | https://www.hikvision.com/en/products/IP-Products/Network-Cameras/ |
| Digital temperature & humidity sensor | 3 | ₹500 | ₹1,500 | Sensirion | SHT31 | Temperature / humidity | https://sensirion.com/products/catalog/SHT31-DIS-B |
| Conventional photoelectric smoke detector | 2 | ₹1,550 | ₹3,100 | Various — must be EN 54-7 / UL 268 certified | Model to be selected | Smoke detection | — (generic; obtain quotation) |
| Water / liquid leak-detection cable | 1 | ₹9,000 | ₹9,000 | Various (e.g. TTK, RLE) | Model to be selected | Water / liquid leak | — (generic; obtain quotation) |
| Edge AI computer | 4 | ₹32,500 | ₹1,30,000 | NVIDIA | Jetson Orin Nano 8 GB (Developer Kit) | Edge node (Jetson Orin Nano) | https://developer.nvidia.com/embedded/learn/get-started-jetson-orin-nano-devkit |
| Single-board computer | 1 | ₹8,250 | ₹8,250 | Raspberry Pi Ltd | Raspberry Pi 5 (4/8 GB) | Edge node (Raspberry Pi 5) | https://www.raspberrypi.com/products/raspberry-pi-5/ |
| Wi-Fi/BT microcontroller module | 1 | ₹650 | ₹650 | Espressif | ESP32-WROOM-32E | Edge node (ESP32 + SX1276) | https://www.espressif.com/en/products/modules/esp32 |
| Gigabit PoE+ network switch | 5 | ₹14,500 | ₹72,500 | Various (e.g. TP-Link, Moxa industrial) | Model to be selected | Per-side and gate cabinets | — (generic; obtain quotation) |
| Isolated RS-485 transceiver | 4 | ₹900 | ₹3,600 | Analog Devices | ADM2587E | Isolated RS-485 per side bus | https://www.analog.com/en/products/adm2587e.html |
| LoRa transceiver module | 1 | ₹1,100 | ₹1,100 | HopeRF (Semtech SX1276 inside) | RFM95W | Env node radio | https://www.semtech.com/products/wireless-rf/lora-connect/sx1276 |
| Enclosed AC-DC power supply 100 W / 12 V | 6 | ₹1,700 | ₹10,200 | MEAN WELL | LRS-100-12 | Cabinet DC supplies | https://www.meanwell.com/productSeries.aspx |
| DC-DC buck converter module | 2 | ₹175 | ₹350 | Generic (TI LM2596-based) | LM2596 module | 5 V rails | https://www.ti.com/product/LM2596 |
| Line-interactive UPS 1500 VA | 1 | ₹60,000 | ₹60,000 | Schneider Electric (APC) | Smart-UPS SMT1500IC | Command-centre UPS | https://www.apc.com/ |
| 12 V 7 Ah VRLA battery | 12 | ₹1,700 | ₹20,400 | Yuasa | NP7-12 | Cabinet batteries (2 per cabinet) | https://www.yuasa.co.uk/ |
| Solar MPPT charge controller | 1 | ₹9,000 | ₹9,000 | Victron Energy | SmartSolar MPPT 75/15 | Solar env node | https://www.victronenergy.com/solar-charge-controllers |
| High-side current/power monitor | 6 | ₹275 | ₹1,650 | Texas Instruments | INA219 | Rail monitoring per cabinet | https://www.ti.com/product/INA219 |
| MQTT broker (software) | 1 | ₹0 | ₹0 | Eclipse Foundation | Mosquitto 2.x | Broker (software) | https://mosquitto.org/ |

**Hardware subtotal (EST):** ₹15,59,875 (range ₹8,18,100 – ₹23,01,650)

### Not included (must be estimated separately)

- Poles, enclosures (IP66), lightning/surge protection, earthing
- Fibre/copper cabling, trenching, conduits
- Command-centre workstation, displays, server (≈ any modern x86 PC suffices for the demonstrator software)
- LoRaWAN gateway, VPN/firewall appliances, cellular data plans
- Installation, commissioning, calibration walk-tests, training, AMC
