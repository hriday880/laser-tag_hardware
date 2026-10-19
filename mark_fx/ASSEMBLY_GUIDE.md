# Mark FX — 8-Player Production Assembly Guide & Master BOM

This is the complete, ready-to-print production manufacturing, pre-cut scheduling, and assembly manual for constructing **8 complete Mark FX Laser Tag units** (8 guns + 8 vests, covering Players `P1` through `P8`).

---

## 📋 Table of Contents
1. [System Architecture & Manufacturing Philosophy](#-system-architecture--manufacturing-philosophy)
2. [8-Player Master Bill of Materials (BOM)](#-8-player-master-bill-of-materials-bom)
3. [8-Unit Pre-Cut Manufacturing Matrix](#-8-unit-pre-cut-manufacturing-matrix)
4. [Mechanical Preparation & Drilling Specifications](#-mechanical-preparation--drilling-specifications)
5. [Batch Production Workflow](#-batch-production-workflow)
6. [Physical Player Visual Coding (Blue P1–P4 vs Red P5–P8)](#-physical-player-visual-coding-blue-p1p4-vs-red-p5p8)
7. [Step-by-Step Sub-Assembly Guide](#-step-by-step-sub-assembly-guide)
   - [Sub-Assembly A: 5-Sensor 360° Vest Harness](#sub-assembly-a-5-sensor-360-vest-harness)
   - [Sub-Assembly B: Gun Enclosure Electronics](#sub-assembly-b-gun-enclosure-electronics)
8. [Firmware Flashing & Node ID Assignment](#-firmware-flashing--node-id-assignment)
9. [Pre-Flight Bench QA Acceptance Checklist](#-pre-flight-bench-qa-acceptance-checklist)
10. [Visual Schematics & Diagram References](#-visual-schematics--diagram-references)

---

## 🎯 System Architecture & Manufacturing Philosophy

The **Mark FX** laser tag system is engineered for low-cost, high-reliability batch manufacturing. All active electronics, microcontrollers, sound transducers, and visual displays are consolidated inside the gun enclosure, eliminating complex backpack enclosures and fragile displays.

```
       ┌────────────────────────────────────────────────────────┐
       │                   MARK FX GUN ENCLOSURE                │
       │                                                        │
       │   [5-LED UNICOLOR HUD BAR]  (D18, D19, D21, D22, D23)  │
       │        ●     ●     ●     ●     ●                       │
       │       HP1   HP2   HP3   HP4   HP5                      │
       │                                                        │
Muzzle │ [940nm IR LED] <==== [ESP32 DevKit V1] ===> [BUZZER]   │ Rear
<======│  (D4 via 100Ω)                                (D33)    │ Cap
       │                                                        │
       │                   [TRIGGER SWITCH]                     │
       │                        (D13)                           │
       └──────────────────────────┼─────────────────────────────┘
                                  │
                 Flexible 3-Wire Umbilical Cable
                   (Red: 3V3, Black: GND, Yellow: D15)
                                  │
                                  ▼
               5-Sensor TSOP1838 Parallel Vest Harness
             (S1: Chest, S2: L-Shoulder, S3: R-Shoulder,
              S4: Back-Left, S5: Back-Right)
```

### Strict Constraint Enforcement:
- **NO LCD screens or OLEDs:** Replaced entirely by a 5-LED unicolor status bar on top of the gun barrel.
- **NO Neopixel or WS2812 strips:** Eliminates timing jitter, external level-shifters, and high current draw.
- **NO external drive transistors:** The 940nm IR LED and piezo buzzer are driven directly from ESP32 GPIOs safely.
- **NO external capacitors:** Power rails rely on clean USB 5V regulation from the power bank and internal ESP32 decoupling.
- **Direct-Drive IR Safety:** Muzzle emitter uses a single **100Ω 1/4W 1% metal-film resistor** (centering forward current at **17.41mA**, strictly inside the 15mA–20mA design envelope to guarantee 4–6m indoor/backyard tactical range without overdriving ESP32 silicon).

---

## 📦 8-Player Master Bill of Materials (BOM)

Procurement quantities for building 8 complete player units (8 guns + 8 vests):

| # | Item Description | Qty / Unit | Total (8 Units) | Procurement Specifications & Notes |
| :-: | :--- | :-: | :-: | :--- |
| **A** | **Core Electronics** | | | |
| 1 | **ESP32 DOIT DevKit V1** | 1 | **8 pcs** | 30-pin version, CH340 or CP2102 USB, micro-USB port. |
| 2 | **TSOP1838 IR Receiver Modules** | 5 | **40 pcs** | 38kHz carrier, miniaturized epoxy package (Pin 1=OUT, 2=GND, 3=VCC). |
| 3 | **940nm 5mm IR Emitter LEDs** | 1 | **8 pcs** | High-radiant AlGaAs, $V_f \approx 1.35\text{V}$, half-angle $15^\circ$–$20^\circ$. |
| 4 | **5mm Unicolor Diffused LEDs** | 5 | **40 pcs** | Red, Green, or Blue unicolor status LEDs ($V_f \approx 2.0\text{V}$, 5mA–7mA). |
| 5 | **Passive Piezo Buzzers** | 1 | **8 pcs** | 5V 12mm passive buzzer (transducer type, driven by ESP32 `tone()`). |
| 6 | **Tactile Push Buttons** | 1 | **8 pcs** | 12×12mm tactile momentary SPST switch (or arcade button). |
| 7 | **USB Power Cables (A to Micro)**| 1 | **8 pcs** | 0.3m to 0.5m sturdy braided cable connecting ESP32 to power bank. |
| **B** | **Resistors & Passives** | | | |
| 8 | **100Ω 1/4W 1% Metal-Film Resistor**| 1 | **8 pcs** | **Mandated IR LED current limiter** ($I = 17.41\text{mA}$). *Note:* 3× 330Ω in parallel ($110\Omega$, $I = 16.0\text{mA}$) is an acceptable alternative (24 pcs 330Ω needed). |
| 9 | **330Ω 1/4W 5% Carbon/Metal Resistors**| 5 | **40 pcs** | Current limiting for HUD LEDs 1–5 on D18, D19, D21, D22, D23 (~4.5mA/LED). |
| **C** | **Wiring & Tubing** | | | |
| 10 | **28 AWG 3-Conductor Ribbon Wire** | 2.65m | **22.0 meters** | Rainbow flat ribbon cable: Red (3V3), Black (GND), Yellow (D15). 12m for 8 umbilicals + 9.2m for 8 vest harnesses + 0.8m margin. |
| 11 | **Heat Shrink Tubing Ø 1.5mm–2.0mm** | 0.5m | **4.0 meters** | 2:1 polyolefin heat shrink for insulating individual TSOP pins, LEDs, resistors. |
| 12 | **Heat Shrink Tubing Ø 4.0mm–5.0mm** | 0.2m | **1.5 meters** | 2:1 polyolefin heat shrink for sensor body encapsulation and splice bundling. |
| 13 | **Heat Shrink Tubing Ø 8.0mm–10.0mm**| 0.1m | **0.75 meters**| Heavy-wall polyolefin for gun and vest umbilical entry strain-relief boots. |
| **D** | **Mechanical & Harness Hardware** | | | |
| 14 | **3/4" Schedule 40 White PVC Pipe** | 0.33m | **3.0 meters** | 10-foot stock pipe cut into 8x 230mm barrels + 8x 100mm handles. |
| 15 | **3/4" PVC Tee Fittings (Slip x Slip)**| 1 | **8 pcs** | Forms the ergonomic pistol grip / trigger handle junction. |
| 16 | **3/4" PVC End Caps (Slip-on)** | 2 | **16 pcs** | 8 caps for grip bases + 8 caps for rear barrel housing enclosures. |
| 17 | **1-inch (25mm) Heavy Nylon Webbing**| 2.5m | **20.0 meters** | Durable tactical webbing for 8 cross-body/chest harnesses. |
| 18 | **1-inch Quick-Release Buckles** | 1 | **8 pcs** | Side-squeeze plastic buckles for adjustable torso closure. |
| 19 | **1-inch Tri-Glide Slide Adjusters** | 2 | **16 pcs** | Webbing sliders for chest and shoulder strap tension adjustment. |
| 20 | **100mm (4-inch) Nylon Cable Ties** | 10 | **80 pcs** | Miniature zip-ties to anchor TSOP sensors and wiring to webbing. |
| 21 | **Matte Black Enamel Paint / Paper** | — | **1 can / sheet**| Non-reflective optical liner for front 75mm (3") of PVC barrel. |
| 22 | **Hot Melt Glue / Industrial Adhesive**| — | **4 sticks** | Secures internal components and strain relief anchor points. |
| **E** | **Visual Coding & Identification** | | | |
| 23 | **Blue Electrical Vinyl Tape (19mm)** | — | **1 roll** | Visual team coding bands for Blue Team units (`P1`–`P4`). |
| 24 | **Red Electrical Vinyl Tape (19mm)** | — | **1 roll** | Visual team coding bands for Red Team units (`P5`–`P8`). |
| 25 | **Die-Cut Weatherproof Number Decals**| — | **1 pack** | Bold white numbers `1` through `8` for gun body and vest S1 plate. |

---

## 📐 8-Unit Pre-Cut Manufacturing Matrix

To achieve high-efficiency batch production, all raw stock materials (PVC tubing, nylon webbing, ribbon wire, and heat shrink tubing) MUST be pre-cut to exact dimensions before starting soldering or sub-assembly.

### Table 1: PVC Pipe Pre-Cut Schedule (8 Units)
Raw stock required: 1× 10-foot (3.05m) length of standard 3/4" Schedule 40 PVC pipe.

| Component | Cut Length (Metric) | Cut Length (Imperial) | Qty / Unit | Total Pieces (8 Units) | Cumulative Length |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Main Gun Barrel** | **230 mm** | 9.0 in | 1 | 8 pcs | 1,840 mm (6.04 ft) |
| **Pistol Grip Handle**| **100 mm** | 4.0 in | 1 | 8 pcs | 800 mm (2.62 ft) |
| *Kerf / Scrap allowance* | — | — | — | — | 410 mm (1.34 ft) |
| **Total Stock Required** | — | — | — | **16 pcs** | **3,050 mm (10.0 ft)** |

### Table 2: Nylon Webbing Harness Pre-Cut Schedule (8 Units)
Raw stock required: 20.0 meters of 1-inch (25mm) black nylon webbing.

| Harness Segment | Function / Placement | Cut Length | Qty / Vest | Total Pieces (8 Vests) | Total Webbing |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **W1: Torso Belt** | Main waist belt with quick-release buckle & slider | **100 cm** | 1 | 8 pcs | 8.0 m |
| **W2: Left Shoulder** | Over left shoulder supporting Sensor S2 | **65 cm** | 1 | 8 pcs | 5.2 m |
| **W3: Right Shoulder**| Over right shoulder supporting Sensor S3 | **65 cm** | 1 | 8 pcs | 5.2 m |
| **W4: Cross-Back** | Horizontal back stabilizer linking S4 and S5 | **20 cm** | 1 | 8 pcs | 1.6 m |
| **Total per Vest / System**| Fits player chests from 28" to 44" | **250 cm** | **4 straps** | **32 straps** | **20.0 meters** |

> **Cutting Tip:** Sear all nylon webbing ends with a lighter or hot-knife to prevent fraying.

### Table 3: 3-Conductor Ribbon Cable Pre-Cut Schedule (8 Units)
Raw stock required: 22.0 meters of 28 AWG 3-conductor flat ribbon wire (Red, Black, Yellow).

| Segment | Origin | Destination | Cut Length | Qty / Unit | Total Pieces (8 Units) | Total Wire |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **C1: Chest to Left Shld** | S1 (Chest) | S2 (L-Shoulder) | **25 cm** | 1 | 8 pcs | 2.0 m |
| **C2: Chest to Right Shld**| S1 (Chest) | S3 (R-Shoulder) | **25 cm** | 1 | 8 pcs | 2.0 m |
| **C3: Left Shld to Back-L** | S2 (L-Shoulder) | S4 (Back-Left) | **35 cm** | 1 | 8 pcs | 2.8 m |
| **C4: Back-L to Back-R** | S4 (Back-Left) | S5 (Back-Right) | **30 cm** | 1 | 8 pcs | 2.4 m |
| **C5: Umbilical Cable** | S1 Vest Junction | Gun ESP32 | **150 cm** | 1 | 8 pcs | 12.0 m |
| *Harness Total per Unit* | — | — | **2.65 m** | **5 segments**| **40 segments**| **21.2 m** |

### Table 4: Heat Shrink Tubing Pre-Cut Schedule (8 Units)

| Diameter | Application / Target Joints | Cut Length | Cuts / Unit | Total Cuts (8 Units) | Total Length |
| :---: | :--- | :---: | :---: | :---: | :---: |
| **Ø 1.5mm–2.0mm** | TSOP pins (3/sensor × 5), HUD LEDs (2/LED × 5), IR resistor (3), Trigger (2), Buzzer (2) | **15 mm** | 32 cuts | **256 cuts** | 3.84 m (~4.0m) |
| **Ø 4.0mm–5.0mm** | TSOP sensor body weatherproofing, 3-wire ribbon splices, IR resistor bundle | **25 mm** | 7 cuts | **56 cuts** | 1.40 m (~1.5m) |
| **Ø 8.0mm–10.0mm** | Umbilical entry strain-relief sleeves (gun exit & vest S1 junction) | **40 mm** | 2 cuts | **16 cuts** | 0.64 m (~0.7m) |

---

## 🛠 Mechanical Preparation & Drilling Specifications

Before assembling electronics, prepare all 8 sets of PVC barrels and grips using a standardized drill jig:

```
                          GUN HOUSING DRILL TEMPLATE
     Muzzle                                                             Rear Cap
       │◄── 35mm ──►│◄─────────── 117mm ───────────►│◄────── 78mm ─────►│
       ┌────────────┬───────────────────────────────┬───────────────────┐
       │            │  (Top Ridge HUD LED Array)    │  (Rear Enclosure) │
  ─────┤   BARREL   │   (5)    (4)    (3)    (2)   (1)  │  [ESP32 SLED]     ├─────
       │            │    ●      ●      ●      ●     ●   │                   │
       └────────────┴────┼──────┼──────┼──────┼─────┼───┴───────────────────┘
                         │◄12mm►│◄12mm►│◄12mm►│◄12mm►│
                         D23    D22    D21    D19   D18
```

1. **Top Ridge HUD Holes:**
   - Scribe a straight line along the top crown of each 230mm PVC barrel.
   - Measure from the **rear edge**:
     * **LED 1 (1 HP / Critical):** Mark at **30 mm** from rear.
     * **LED 2 (2 HP):** Mark at **42 mm** from rear.
     * **LED 3 (3 HP):** Mark at **54 mm** from rear.
     * **LED 4 (4 HP):** Mark at **66 mm** from rear.
     * **LED 5 (5 HP / Full):** Mark at **78 mm** from rear.
   - Center-punch and drill five **5.0 mm holes** along the line. Deburr thoroughly.

2. **Trigger Switch Hole:**
   - Mark a point on the underside of the barrel (or front face of the 100mm grip tube) **60 mm below the barrel centerline**.
   - Drill a **12.0 mm hole** to accommodate the tactile push button bushing.

3. **Rear Cap Umbilical & Power Ports:**
   - Take the 8 rear PVC end caps.
   - Drill one **6.0 mm hole** on the lower half of each end cap for the 3-wire umbilical strain relief grommet.
   - Mill or drill a **10mm × 6mm rectangular slot** directly centered for the micro-USB power cable connector to plug securely into the ESP32.

4. **Optical Barrel Baffling & Recess:**
   - Scribe an internal depth stop mark **35 mm from the muzzle front opening**.
   - Paint the interior of the front 75mm (3 inches) with **matte black paint** (or insert a rolled matte black cardstock sleeve). This eliminates wall-bouncing internal reflections and restricts the 940nm beam to a clean, tactical $\approx 15^\circ$ forward cone.

---

## 🔄 Batch Production Workflow

Follow this 4-phase assembly sequence across all 8 units to maximize quality control and consistency:

```
╔═════════════════════════════════════════════════════════════════════════════════════╗
║                               BATCH WORKFLOW PHASES                                 ║
╠════════════════════╦════════════════════╦════════════════════╦══════════════════════╣
║      PHASE 1       ║      PHASE 2       ║      PHASE 3       ║       PHASE 4        ║
║   Pre-Cutting &    ║  5-Sensor 360°     ║   Gun Enclosure    ║  Flashing, Visual    ║
║  Mechanical Prep   ║  Harness Assembly  ║    Electronics     ║   Coding & Bench QA  ║
╠════════════════════╬════════════════════╬════════════════════╬══════════════════════╣
║ • Cut 16 PVC pipes ║ • Build 8 webbing  ║ • Mount 5 HUD LEDs ║ • Flash mark_fx.ino  ║
║ • Drill HUD holes  ║   strap harnesses  ║ • Solder 330Ω pack ║   with P1..P8 NODE_ID║
║ • Paint muzzles    ║ • Wire 40 TSOPs    ║ • Solder 100Ω IR   ║ • Apply Blue/Red tape║
║ • Cut 32 straps    ║   in parallel bus  ║ • Wire trigger &   ║ • Apply P1..P8 decals║
║ • Cut 40 wires     ║ • Apply heatshrink ║   passive buzzer   ║ • Execute 6-step     ║
║ • Cut 328 shrinks  ║ • Fit 1.5m umbilical║• Secure ESP32 sled║   bench test check   ║
╚════════════════════╩════════════════════╩════════════════════╩══════════════════════╝
```

---

## 🎨 Physical Player Visual Coding (Blue P1–P4 vs Red P5–P8)

Each unit must be visually identifiable in the arena so players, referees, and spectators can immediately distinguish friendly teammates from enemies:

```
  ┌────────────────────────────────────────────────────────────────────────┐
  │                           BLUE TEAM (P1 – P4)                          │
  │   • Barrel Band: 25mm Blue Vinyl Tape around muzzle collar             │
  │   • Grip Base: 25mm Blue Vinyl Tape around grip cap                    │
  │   • Vest Plate: Blue background tag behind S1 chest sensor             │
  │   • Decals: Bold white "P1", "P2", "P3", "P4" on gun flank and vest    │
  ├────────────────────────────────────────────────────────────────────────┤
  │                            RED TEAM (P5 – P8)                          │
  │   • Barrel Band: 25mm Red Vinyl Tape around muzzle collar              │
  │   • Grip Base: 25mm Red Vinyl Tape around grip cap                     │
  │   • Vest Plate: Red background tag behind S1 chest sensor              │
  │   • Decals: Bold white "P5", "P6", "P7", "P8" on gun flank and vest    │
  └────────────────────────────────────────────────────────────────────────┘
```

### Visual Coding & Firmware Allocation Matrix

| Unit | Team | Color Tag | Transmitted NEC Code | Compile Flag | Server Attributed Role |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **Player 1** | **Blue** | Blue Tape + "P1" | `0x00FF30CF` | `#define NODE_ID "P1"` | Blue Friend 1 |
| **Player 2** | **Blue** | Blue Tape + "P2" | `0x00FF18E7` | `#define NODE_ID "P2"` | Blue Friend 2 |
| **Player 3** | **Blue** | Blue Tape + "P3" | `0x00FF7A85` | `#define NODE_ID "P3"` | Blue Friend 3 |
| **Player 4** | **Blue** | Blue Tape + "P4" | `0x00FF10EF` | `#define NODE_ID "P4"` | Blue Friend 4 |
| **Player 5** | **Red** | Red Tape + "P5" | `0x00FF38C7` | `#define NODE_ID "P5"` | Red Enemy 1 |
| **Player 6** | **Red** | Red Tape + "P6" | `0x00FF5AA5` | `#define NODE_ID "P6"` | Red Enemy 2 |
| **Player 7** | **Red** | Red Tape + "P7" | `0x00FF42BD` | `#define NODE_ID "P7"` | Red Enemy 3 |
| **Player 8** | **Red** | Red Tape + "P8" | `0x00FF4AB5` | `#define NODE_ID "P8"` | Red Enemy 4 |

---

## 🔧 Step-by-Step Sub-Assembly Guide

### Sub-Assembly A: 5-Sensor 360° Vest Harness

#### 1. Webbing Harness Construction:
1. Lay out the pre-cut straps:
   - **Torso Belt (100cm):** Thread one end through the male side-squeeze buckle and secure with a 1" tri-glide slider. Thread the female buckle half onto the opposite end.
   - **Left Shoulder Strap (65cm):** Stitch or loop one end to the torso belt 12cm left of center front; loop the other end to the back belt 15cm left of center back.
   - **Right Shoulder Strap (65cm):** Repeat symmetrically on the right side.
   - **Cross-Back Stabilizer (20cm):** Connect between the two shoulder straps horizontally across the shoulder blades.

```
                  FRONT VIEW                           BACK VIEW
              [S2: L Shoulder]                     [S4: Back Left]
                    \                                    /
                     \     [S3: R Shoulder]             /     [S5: Back Right]
                      \          /                     /            /
                       \        /                     ┌────────────┐ (W4: Cross-Back)
                   [S1: Chest Center]                 │   W4 20cm  │
                        │    │                        └────────────┘
         ═══════════════╧════╧═════════════════════════════════════════════════
                              (W1: Adjustable Torso Belt 100cm)
```

#### 2. TSOP1838 Pinout Orientation:
Holding each TSOP1838 facing the **curved black dome (bump)** with legs pointing downwards:
- **Pin 1 (LEFT):** `OUT` (Signal line $\rightarrow$ Yellow Wire)
- **Pin 2 (MIDDLE):** `GND` (Ground rail $\rightarrow$ Black Wire)
- **Pin 3 (RIGHT):** `VCC` (Power rail 3.3V $\rightarrow$ Red Wire)

```
        TSOP1838 FRONT FACE
           ┌──────────┐
           │   (●)    │  <-- Curved IR Receiving Dome
           │          │
           └──┬──┬──┬─┘
              │  │  │
              │  │  │
            Pin1 │ Pin3
               Pin2
            (OUT GND VCC)
```

#### 3. Parallel Bus Soldering & Heat Shrinking:
All 5 sensors operate on a **Parallel Wired-OR Bus**. An active hit detected by any single sensor pulls the shared signal line LOW to 0V.
1. Slide three 15mm pieces of **Ø 2mm heat shrink** over the pre-cut ribbon wires.
2. Solder the inter-sensor ribbon wires according to the routing schedule:
   - S1 (Chest) connects to S2 (L-Shoulder) via 25cm ribbon.
   - S1 (Chest) connects to S3 (R-Shoulder) via 25cm ribbon.
   - S2 (L-Shoulder) connects to S4 (Back-Left) via 35cm ribbon.
   - S4 (Back-Left) connects to S5 (Back-Right) via 30cm ribbon.
3. Slide heat shrink down over each solder joint and shrink with a heat gun.
4. Slide a 25mm piece of **Ø 5mm heat shrink** over the sensor body and pins, leaving only the curved receiving dome exposed.
5. At Sensor S1 (Chest), splice in the **150cm 3-wire Umbilical Cable**:
   - Join all Pin 1 (OUT) lines to **Yellow Wire**.
   - Join all Pin 2 (GND) lines to **Black Wire**.
   - Join all Pin 3 (VCC) lines to **Red Wire**.
6. Secure the umbilical junction with a 40mm sleeve of **Ø 10mm heat shrink** for strain relief.
7. Fasten each sensor to its designated webbing mount point using two 100mm nylon cable ties and a drop of hot glue.

---

### Sub-Assembly B: Gun Enclosure Electronics

#### 1. 5-LED Unicolor HUD Bar Wiring:
1. Insert five 5mm unicolor LEDs into the top ridge holes (LED 1 at rear $\rightarrow$ LED 5 at front):
   - **LED 1 (1 HP / Critical):** Solder a **330Ω resistor** to the Long lead (Anode +); connect to **Pin `D18`**.
   - **LED 2 (2 HP):** Solder a **330Ω resistor** to Anode (+); connect to **Pin `D19`**.
   - **LED 3 (3 HP):** Solder a **330Ω resistor** to Anode (+); connect to **Pin `D21`**.
   - **LED 4 (4 HP):** Solder a **330Ω resistor** to Anode (+); connect to **Pin `D22`**.
   - **LED 5 (5 HP / Full):** Solder a **330Ω resistor** to Anode (+); connect to **Pin `D23`**.
2. Insulate each resistor and anode lead with 15mm of **Ø 2mm heat shrink**.
3. Bend all five Short leads (Cathodes -) together, solder into a common ground bus wire, and insulate.
4. Route common cathode wire to **ESP32 `GND`**.

#### 2. 940nm IR LED Direct-Drive Muzzle Circuit:
1. Solder the **100Ω 1/4W 1% metal-film resistor** directly to the Long lead (Anode +) of the 940nm IR LED.
   *(Alternative: If 100Ω metal-film is unavailable, twist three 330Ω resistors in parallel to make a 110Ω pack).*
2. Connect the other end of the resistor to **Pin `D4`**.
3. Solder the Short lead (Cathode -) of the IR LED to **ESP32 `GND`**.
4. Insulate both leads with **Ø 2mm heat shrink**.
5. Mount the IR LED assembly **exactly 35 mm recessed inside the front PVC barrel**, aligned parallel to the barrel bore. Secure with hot glue.

#### 3. Trigger Push Button:
1. Solder two flexible wires to opposite diagonal pins of the tactile push switch.
2. Insulate terminals with **Ø 2mm heat shrink**.
3. Connect one wire to **Pin `D13`**; connect the other wire to **`GND`**.
   *(Firmware configures D13 with internal `INPUT_PULLUP` (~45kΩ); switch closure pulls D13 to 0V).*
4. Insert button into the 12mm trigger hole and secure with lock nut or hot glue.

#### 4. Passive Piezo Buzzer:
1. Solder positive lead (+) of buzzer to **Pin `D33`**.
2. Solder negative lead (-) to **`GND`**.
3. Insulate terminals with **Ø 2mm heat shrink**. Mount inside the PVC Tee junction facing rearward sound relief ports.

#### 5. Umbilical Cable Connection & Sled Closure:
1. Feed the 150cm umbilical cable through the 6mm hole in the rear cap. Slide a 40mm sleeve of **Ø 10mm heat shrink** over the cable for exterior strain relief.
2. Solder umbilical wires to ESP32:
   - **Yellow Wire (Signal)** $\rightarrow$ **Pin `D15`**
   - **Red Wire (Power 3.3V)** $\rightarrow$ **`3V3`**
   - **Black Wire (Ground)** $\rightarrow$ **`GND`**
3. Plug the short USB cable into the ESP32 micro-USB port and align the plug through the rear cap access slot.
4. Secure the ESP32 inside the 230mm barrel tube using a plastic mounting sled or high-density foam block. Press-fit the rear cap.

---

## ⚡ Firmware Flashing & Node ID Assignment

Each of the 8 physical ESP32 boards requires flashing with `mark_fx/mark_fx.ino` configured with its unique player identity:

1. Open `mark_fx/mark_fx.ino` in Arduino IDE or compile via CLI.
2. Locate the Player ID configuration line near the top:
   ```cpp
   #define NODE_ID "P1"  // Change to "P1" through "P8" for each physical unit
   ```
3. Set the target `#define NODE_ID` according to the table:
   - Unit 1: `#define NODE_ID "P1"`
   - Unit 2: `#define NODE_ID "P2"`
   - Unit 3: `#define NODE_ID "P3"`
   - Unit 4: `#define NODE_ID "P4"`
   - Unit 5: `#define NODE_ID "P5"`
   - Unit 6: `#define NODE_ID "P6"`
   - Unit 7: `#define NODE_ID "P7"`
   - Unit 8: `#define NODE_ID "P8"`
4. Verify standard Arduino ESP32 board settings:
   - **Board:** `DOIT ESP32 DEVKIT V1`
   - **CPU Frequency:** `240MHz (WiFi/BT)`
   - **Flash Frequency:** `80MHz`
   - **Flash Mode:** `QIO`
   - **Partition Scheme:** `Default 4MB with spiffs (1.2MB APP/1.5MB SPIFFS)`
   - **Upload Speed:** `921600` (or `115200`)
5. Click **Upload**. Repeat for all 8 boards, applying the corresponding white number decal (`P1`–`P8`) immediately after verification.

---

## 🎯 Pre-Flight Bench QA Acceptance Checklist

Every completed Mark FX unit must pass this 6-step bench test in **100% Standalone Offline Mode** (no Wi-Fi router or Python server required):

| Step | Action | Expected Hardware Behavior | Pass/Fail |
| :-: | :--- | :--- | :-: |
| **1** | **Power-On Boot** | Plug USB power bank into rear micro-USB port. Buzzer plays ascending 3-note **Boot Chime**. HUD LEDs 1–5 execute smooth **Knight Rider sweep** back and forth. | [ ] |
| **2** | **Lobby Connection** | While searching for server/standalone, HUD displays slow ping-pong lobby pulse. Buzzer is silent. | [ ] |
| **3** | **Trigger Fire & Cooldown** | Pull gun trigger once. Muzzle emits 14ms IR burst. Gun emits crisp **Shot chirp**; HUD flashes briefly (50ms). Pulling trigger rapidly within 500ms is ignored by rate limiter. | [ ] |
| **4** | **360° Vest Hit Detection** | Point barrel at Sensor S1 (Chest) and fire: buzzer plays descending **Hit melody**, HUD drops to 4 LEDs. Repeat aiming at S2 (L-Shoulder), S3 (R-Shoulder), S4 (Back-L), S5 (Back-R) to confirm all 5 receivers register hits. | [ ] |
| **5** | **Critical Health & Death** | Fire until 1 HP remains: **LED 1 pulses rapidly** in sync with warning buzzer heartbeat. Fire final shot to reach 0 HP: buzzer plays solemn **Death knell**, all 5 HUD LEDs turn OFF. | [ ] |
| **6** | **Respawn Shield Strobe** | Immediately following death, all 5 LEDs strobe in unison for 4.0 seconds during respawn invulnerability. Hits taken during shield are ignored. Full 5 HP restores upon completion. | [ ] |

---

## 🖼 Visual Schematics & Diagram References

High-resolution vector (`.svg`) and production raster (`.png`, 2000px width) schematics are provided in the project root:

1. **System Wiring Schematic:**
   - Vector: `mark_fx/wiring_schematic.svg`
   - Production PNG: `mark_fx/wiring_schematic.png`
   - *Details complete electrical wiring, pin mappings, 100Ω metal-film resistor, buzzer, trigger, and unified ground return.*

2. **Gun Internal Pinout Diagram:**
   - Vector: `mark_fx/gun_pinout.svg`
   - Production PNG: `mark_fx/gun_pinout.png`
   - *Details ESP32 DevKit V1 30-pin header pinout, GPIO 4/13/15/18/19/21/22/23/33 assignments, and housing layout.*

3. **5-Sensor Vest Harness Diagram:**
   - Vector: `mark_fx/vest_harness.svg`
   - Production PNG: `mark_fx/vest_harness.png`
   - *Details front and rear 360° sensor positioning (S1–S5), TSOP1838 pinout (1=OUT, 2=GND, 3=VCC), and 3-wire umbilical bus.*
