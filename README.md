# ESP32 Laser Tag Hardware & Firmware (Mark 6)

An open-source, affordable laser tag system powered by the **ESP32 DOIT DevKit V1 (30-pin)**. The Mark 6 architecture merges both the vest sensors and gun controls into a single ESP32 microcontroller, delivering 360° IR coverage, dual-trigger weapon modes (Enemy Shot & Medic Heal), polyphonic non-blocking buzzer melodies, a 16x2 I2C LCD HUD, and real-time WiFi synchronization with a central Python match server.

---

## 🎯 Features

* **Single-MCU Architecture:** Both vest and wired gun run on one 30-pin ESP32 DevKit V1.
* **360° Anti-Cover IR Receiver Array:** Up to 6x TSOP1838 38kHz infrared sensors connected in parallel on a single data pin (`D15`).
* **Dual-Trigger Gun:**
  * **Red Trigger (`D13`):** Fires Enemy Shot (`0x00FF38C7` NEC).
  * **Green Trigger (`D32`):** Fires Medic/Heal Shot (`0x00FF30CF` NEC).
* **Safe Direct-Drive IR LED:** 940nm 5mm IR emitter driven on `D4` with a ~110Ω resistor network (or 100Ω) for safe ~18mA current draw without burning the ESP32 GPIO.
* **16x2 I2C LCD HUD:** Displays player stats (HP hearts, remaining lives, match phase, timer, and hit/heal overlays).
* **Non-Blocking Melody Player:** Uses a passive piezo buzzer on `D33` for rich retro 8-bit game tones (boot, shot, hit, death, spawn shield, victory/defeat).
* **Autonomous Match Server & Auto-Discovery:** Automatic UDP discovery and HTTP state synchronization with `server/server.py`.
* **Zero-Config Standalone / Offline Mode:** If WiFi or server is unreachable, the device enters standalone testing mode — triggers and sensors still register shots, buzzer melodies, and screen updates immediately.

---

## 🔌 Pin Mapping (DOIT ESP32 DevKit V1 - 30 Pin)

| Pin Silkscreen | Component | Description & Wiring Notes |
| :--- | :--- | :--- |
| **`D15`** | **TSOP1838 OUT** | Data pin for 6x TSOP1838 sensors (Pin 1 / Left leg of all sensors tied together). |
| **`D4`** | **IR LED Anode (+)** | Gun IR LED Long leg via **100Ω – 110Ω resistor** (Short leg to `GND`). |
| **`D13`** | **Red Trigger** | Push button between `D13` and `GND` (Internal `INPUT_PULLUP`). |
| **`D32`** | **Green Trigger** | Push button between `D32` and `GND` (Internal `INPUT_PULLUP`). |
| **`D33`** | **Passive Buzzer** | Positive (+) pin of passive buzzer (Negative (-) to `GND`). |
| **`D21`** | **LCD SDA** | I2C Serial Data for 16x2 LiquidCrystal Display. |
| **`D22`** | **LCD SCL** | I2C Serial Clock for 16x2 LiquidCrystal Display. |
| **`D2`** | **Status LED** | Onboard blue LED flashes on gun fire. |
| **`3V3`** | **Sensor VCC** | Power rail for TSOP1838 sensors (Pin 3 / Right leg). |
| **`VIN` (5V)** | **LCD Power** | Power rail for I2C LCD display module. |
| **`GND`** | **Common Ground** | Shared ground for buttons, sensors, buzzer, and LED cathode. |

### TSOP1838 Pinout (Facing the front round lens/dome with legs down):
* **Pin 1 (Left):** `OUT` $\rightarrow$ `D15`
* **Pin 2 (Middle):** `GND` $\rightarrow$ `GND`
* **Pin 3 (Right):** `VCC` $\rightarrow$ `3V3`

---

## 📂 Repository Structure

```
├── prototype_mark_6/            # Main Mark 6 production firmware
│   ├── prototype_mark_6.ino     # Full ESP32 firmware (IR, LCD, Audio, WiFi, Game State)
│   ├── PIN_GUIDE.md             # Detailed pin reference & breadboard notes
│   ├── pin_diagram.png          # Pinout diagram
│   ├── pin_diagram_detailed.png # Detailed circuit layout
│   └── trigger_wiring.png       # Tactile push switch diagonal wiring guide
├── prototype_mark_6_lite/       # Minimal lightweight variant of Mark 6
├── server/                      # Central match server
│   ├── server.py                # Python Flask/UDP referee server
│   └── templates/dashboard.html # Web dashboard for spectator / arena admin
├── hardware_test/               # Hardware diagnostic sketch
├── buzzer_test/                 # Active vs passive buzzer calibration sketch
├── button_assigner/             # Button code learning & verification utility
├── BOM_and_Blueprints.pdf       # Full bill of materials & physical build blueprints
└── estimate.md                  # Component pricing and sourcing estimates
```

---

## 🚀 Quick Start

### 1. Arduino IDE Setup
1. Install **ESP32 Board Support** in Arduino IDE (`esp32 by Espressif Systems`).
2. Select Board: **`DOIT ESP32 DEVKIT V1`**.
3. Install Required Libraries via Library Manager:
   * `IRremoteESP8266`
   * `LiquidCrystal I2C` by Frank de Brabander
4. Open `prototype_mark_6/prototype_mark_6.ino`.
5. Update your WiFi credentials:
   ```cpp
   const char* ssid = "YourWiFiSSID";
   const char* password = "YourPassword";
   ```
6. Flash to ESP32 at **921600** upload baud rate.

### 2. Running the Match Server
1. In terminal, navigate to `server/`:
   ```bash
   cd server
   pip install flask
   python3 server.py
   ```
2. Open `http://localhost:5050` in your web browser to view the arena dashboard.
3. Turn on the ESP32 vest — it will automatically discover the server and join the match!

---

## 📜 License
MIT License. Built for DIY makers and laser tag enthusiasts.
