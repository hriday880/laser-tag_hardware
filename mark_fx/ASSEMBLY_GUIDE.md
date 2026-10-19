# Mark FX — 8-Player Production Assembly Guide & BOM

This is the complete, ready-to-print production manufacturing and assembly guide for building **8 complete Mark FX Laser Tag units** (8 guns + 8 vests, covering Players `P1` through `P8`).

---

## 📦 8-Player Master Bill of Materials (BOM)

| Item | Qty per Player | Total Qty (8 Players) | Specifications & Notes |
| :--- | :---: | :---: | :--- |
| **ESP32 DOIT DevKit V1** | 1 | **8 pcs** | 30-pin version with micro-USB port. |
| **TSOP1838 IR Receivers** | 5 | **40 pcs** | 38kHz infrared receiver IC (Pin 1=OUT, 2=GND, 3=VCC). |
| **940nm 5mm IR LEDs** | 1 | **8 pcs** | High-radiant AlGaAs 940nm IR emitters for gun barrels. |
| **5mm Unicolor LEDs** | 5 | **40 pcs** | Single-color LEDs (Red, Green, or Blue) for gun health HUD. |
| **330Ω Resistors (1/4W)** | 8 | **64 pcs** | Single standardized resistor value: 3 in parallel per IR LED (110Ω) + 5 per HUD. |
| **Tactile Push Buttons** | 1 | **8 pcs** | 12mm tactile switches or arcade-style trigger buttons. |
| **Passive Piezo Buzzers** | 1 | **8 pcs** | 5V passive buzzers (piezo type, driven by square waves). |
| **3-Wire Umbilical Cable** | 1.5m | **12 meters** | Flexible 28 AWG rainbow ribbon cable (3 conductors). |
| **Gun Housing (PVC Pipe)** | 1 foot | **8 feet** | 3/4" or 1" standard white/grey PVC plumbing pipe. |
| **Nylon Webbing (Harness)**| 2.5m | **20 meters** | 1-inch cheap nylon strap/webbing for cross-body harness. |
| **USB Cable (A to Micro)** | 1 | **8 pcs** | Short, sturdy USB cable (0.3m to 0.5m) to power bank. |

> **Cost Savings:** By eliminating LCDs, Neopixels, transistors, and capacitors, component count is reduced by over **60%**, and assembly time per unit drops to under **30 minutes**.

---

## 🔫 Gun Enclosure Assembly

Each gun houses the complete electronic brain of the player:
```
           ┌────────────────────────────────────────────────────────┐
           │                     GUN HOUSING                        │
           │                                                        │
           │   [5-LED HUD BAR]  (D18, D19, D21, D22, D23)           │
           │      ●  ●  ●  ●  ●                                     │
           │                                                        │
Barrel <===│ [IR LED] <=== [ESP32 DevKit V1] ===> [BUZZER (D33)]    │
           │                                                        │
           │                     [TRIGGER (D13)]                    │
           │                           │                            │
           └───────────────────────────┼────────────────────────────┘
                                       │
                          3-Wire Umbilical to Vest (3V3, GND, D15)
```

### Step 1: Barrel Preparation & IR LED Emitter
1. Cut an 8-inch to 10-inch section of 3/4" PVC pipe.
2. Paint the inside of the front 3 inches **matte black** (or insert a rolled black paper tube) to prevent light reflection.
3. Take **three 330Ω resistors** and twist both ends together in parallel to create a single **110Ω resistor pack**.
4. Solder one end of the 110Ω pack to **Pin `D4`** of the ESP32.
5. Solder the other end to the **Long leg (+)** of the 940nm IR LED.
6. Solder the **Short leg (-)** of the IR LED to **`GND`**.
7. Mount the IR LED **at least 30mm to 40mm recessed inside the barrel** from the front opening. This restricts the beam angle to a tight cone ($\approx 15^\circ$), eliminating room-wide wall bouncing.

### Step 2: 5-LED Unicolor HUD Bar
1. Drill five 5mm holes along the top ridge of the gun housing, spaced 10mm apart:
   * **LED 1 (1 HP / Critical):** Solder 330Ω resistor $\rightarrow$ **`D18`**
   * **LED 2 (2 HP):** Solder 330Ω resistor $\rightarrow$ **`D19`**
   * **LED 3 (3 HP):** Solder 330Ω resistor $\rightarrow$ **`D21`**
   * **LED 4 (4 HP):** Solder 330Ω resistor $\rightarrow$ **`D22`**
   * **LED 5 (5 HP / Full Health):** Solder 330Ω resistor $\rightarrow$ **`D23`**
2. Tie all five **Cathodes (-)** together to a common **`GND`** wire.

### Step 3: Trigger Push Button
1. Solder one diagonal pin of the push switch to **Pin `D13`**.
2. Solder the other diagonal pin to **`GND`**.
3. Mount the switch inside the trigger guard.

### Step 4: Passive Buzzer
1. Solder the positive terminal (+) of the passive buzzer to **Pin `D33`**.
2. Solder the negative terminal (-) to **`GND`**.

---

## 🦺 5-Sensor Vest Harness Assembly

### Sensor Layout (360° Anti-Cover Coverage)
The 5 TSOP1838 receivers are arranged across the body to ensure hit detection from any angle:
* **Sensor 1 (Front Center):** Center chest ($0^\circ$).
* **Sensor 2 (Front Left):** Left shoulder ($45^\circ$ forward angle).
* **Sensor 3 (Front Right):** Right shoulder ($45^\circ$ forward angle).
* **Sensor 4 (Back Left):** Upper left back ($135^\circ$ rear angle).
* **Sensor 5 (Back Right):** Upper right back ($135^\circ$ rear angle).

```
                     FRONT                            BACK
               [S2: L Shoulder]                 [S4: Back Left]
                      \                               /
                  [S1: Chest]                        /
                      /                             /
               [S3: R Shoulder]                 [S5: Back Right]
```

### Sensor Pinout & Parallel Bus Wiring
Looking at each TSOP1838 facing the **curved black dome (bump)** with legs down:
* **Leg 1 (LEFT):** `OUT` (Signal)
* **Leg 2 (MIDDLE):** `GND` (Ground)
* **Leg 3 (RIGHT):** `VCC` (Power 3.3V)

**Parallel Wiring:**
1. Connect all 5 **Leg 1s (OUT)** together $\rightarrow$ connects to **`D15`** via the umbilical cable.
2. Connect all 5 **Leg 2s (GND)** together $\rightarrow$ connects to **`GND`** via the umbilical cable.
3. Connect all 5 **Leg 3s (VCC)** together $\rightarrow$ connects to **`3V3`** via the umbilical cable.

### 3-Wire Umbilical Interconnect
* Use a 1.2m to 1.5m length of 3-conductor ribbon wire.
* Route from the vest shoulder down the player's arm into the rear of the gun.
* Label the 3 wires: **Red = 3V3**, **Black = GND**, **Yellow = D15 (Signal)**.

---

## ⚡ Firmware Flashing & Player Configuration

### Player ID Configuration Table
Open `mark_fx/mark_fx.ino` in Arduino IDE. For each physical ESP32 board, set line 20:

| Board # | Compile Flag | Transmitted IR Code | Team | Server Role |
| :---: | :---: | :---: | :---: | :---: |
| **Player 1** | `#define NODE_ID "P1"` | `0x00FF30CF` | Blue | Friend 1 |
| **Player 2** | `#define NODE_ID "P2"` | `0x00FF18E7` | Blue | Friend 2 |
| **Player 3** | `#define NODE_ID "P3"` | `0x00FF7A85` | Blue | Friend 3 |
| **Player 4** | `#define NODE_ID "P4"` | `0x00FF10EF` | Blue | Friend 4 |
| **Player 5** | `#define NODE_ID "P5"` | `0x00FF38C7` | Red | Enemy 1 |
| **Player 6** | `#define NODE_ID "P6"` | `0x00FF5AA5` | Red | Enemy 2 |
| **Player 7** | `#define NODE_ID "P7"` | `0x00FF42BD` | Red | Enemy 3 |
| **Player 8** | `#define NODE_ID "P8"` | `0x00FF4AB5` | Red | Enemy 4 |

### Upload Settings:
* **Board:** `DOIT ESP32 DEVKIT V1`
* **Upload Speed:** `921600` (or `115200`)
* **Flash Frequency:** `80MHz`
* **Partition Scheme:** `Default 4MB with spiffs`

---

## 🎯 Pre-Flight Bench Test (100% Offline)

You do **not** need Wi-Fi or a computer server running to verify each gun and vest:
1. Plug a USB power bank into the ESP32.
2. The buzzer plays the **Boot Chime**, and the 5 HUD LEDs execute a **Knight Rider sweep**.
3. Point the gun barrel at any of the 5 vest sensors and pull the trigger:
   * The gun emits a crisp **Shot chirp** and flashes the HUD LEDs for 50ms.
   * The vest sensor registers the hit: the buzzer plays the **Hit melody**, and **HUD LED 5 turns OFF** (4 HP remaining).
4. Shoot 4 more times to drop HP to 0:
   * Buzzer plays the **Death knell**, and all 5 LEDs strobe during the 4-second **Respawn shield**.
5. Once verified, the unit is 100% battle-ready!
