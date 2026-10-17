# Mark 6 - Pin Guide (ESP32 30-pin, 1 vest + 1 gun)

> **Board Silkscreen Note:** On 30-pin ESP32 boards, the pins are stamped as **D13, D12, D14, D27...** on one side and **D15, D2, D4, D16...** on the other side. "D" stands for Digital GPIO. In Arduino code, `D13` is simply referenced as pin number `13`.

Diagrams in this folder:
- `pin_diagram.png`: whole system on one page (showing exact D-pin labels)
- `pin_diagram_detailed.png`: each component close up, plus the full pin map
- `trigger_wiring.png`: push switches explained for beginners

---

## 1. Complete Pin Map (Board Silkscreen vs Code)

| Board Silkscreen Label | Arduino GPIO # | Connects to | Direction | Notes |
|---|---|---|---|---|
| **3V3** | 3.3V | VCC of all 6 TSOP sensors | power | Sensors must NOT get 5V |
| **VIN** (or 5V) | 5V | LCD backpack VCC | power | Powered from USB for now |
| **GND** | Ground | Every ground in the build | ground | Join all grounds together |
| **D15** | GPIO 15 | OUT of all 6 TSOP sensors (joined) | input | Boot pin safe (sensors idle HIGH) |
| **D4** | GPIO 4 | IR LED (+) through a 100 ohm resistor | output | Sends the IR beam shot code |
| **D13** | GPIO 13 | RED trigger button (other side to GND) | input | Enemy shot (internal pull-up) |
| **D32** | GPIO 32 | GREEN trigger button (other side to GND) | input | Friend / medic shot (internal pull-up) |
| **D33** | GPIO 33 | Passive Buzzer (+) | output | Melody and tone output |
| **D21** | GPIO 21 | LCD SDA | I2C | Default I2C data pin |
| **D22** | GPIO 22 | LCD SCL | I2C | Default I2C clock pin |
| **D2** | GPIO 2 | Onboard LED (built into the board) | output | Status blink (no external wiring) |

---

## 2. Component Wiring Guide

### 6x TSOP1838 Sensors (Vest)
- **Pinout (facing the dome from left to right):** Pin 1 = **OUT**, Pin 2 = **GND**, Pin 3 = **VCC**.
- Join all six **VCC** pins together -> connect to board pin **3V3**.
- Join all six **GND** pins together -> connect to board pin **GND**.
- Join all six **OUT** pins together -> connect to board pin **D15**.
- Solder a **0.1µF (104) ceramic capacitor across VCC and GND** directly at each sensor.
- Placement on harness: 4 sensors on the front, 2 on the back.

### IR LED (Gun)
- Long leg (+) -> **100 ohm resistor** -> board pin **D4**.
- Short leg (flat notch edge, -) -> board pin **GND**.
- Recess the LED 30mm deep inside a matte black tube for a narrow, directional beam.

### Triggers (2 Push Switches)
- **RED Button (Enemy Shot):** One leg to board pin **D13**, diagonal leg to board pin **GND**.
- **GREEN Button (Friend/Medic Shot):** One leg to board pin **D32**, diagonal leg to board pin **GND**.
- Both buttons share the common GND wire. No external pull-up resistors needed!

### Passive Buzzer
- **Bare 2-pin buzzer:** (+) leg (longer leg or marked with `+`) -> board pin **D33**; (-) leg -> board pin **GND**.
- **3-pin buzzer module:** Pin `S` -> board pin **D33**; Pin `VCC` -> **3V3**; Pin `GND` -> **GND**.

### 16x2 LCD with I2C Backpack
- **GND** -> board pin **GND**
- **VCC** -> board pin **VIN** (5V)
- **SDA** -> board pin **D21**
- **SCL** -> board pin **D22**
- Default I2C address is `0x27` (or `0x3F` if your backpack uses that). Adjust the blue contrast potentiometer on the back if screen is blank.

---

## 3. Step-by-Step Test Order

Upload `prototype_mark_6.ino` via Arduino IDE and check in the Serial Monitor (115200 baud):

| Step | Wire Up | Expected Result |
|---|---|---|
| 1 | LCD to VIN, GND, D21, D22 | Displays `"LaserTag Mark 6"` and WiFi status at boot |
| 2 | Buzzer to D33, GND | Plays startup boot chime |
| 3 | Buttons to D13, D32, GND | Pressing triggers plays a short blocked beep (locked until match starts) |
| 4 | Sensors to 3V3, GND, D15 | Ready to receive IR signals |
| 5 | IR LED to D4 (via 100Ω), GND | Start match from dashboard, shoot RED at sensors: Serial logs `[GUN] Fired`, LCD shows `HIT! -1 HP` |
| 6 | Medic shot | Shoot GREEN at sensors: LCD displays `+1 HP MEDIC` (or `HP ALREADY FULL`) |

---

## 4. Quick Troubleshooting

| Issue | Root Cause & Fix |
|---|---|
| LCD lit but blank / blocks only | Rotate blue contrast trimmer on back of backpack; check if address is `0x3F` |
| Button doesn't trigger | Wires connected to same internal pair. Connect to **diagonal** legs! |
| Gun fires but sensors don't register | IR LED polarity reversed; check D4 connection; ensure match is LIVE |
| Random ghost hits | Missing 0.1µF capacitors, or TSOP VCC wired to 5V instead of 3V3 |
| Upload stuck on "Connecting..." | Hold down the physical **BOOT** button on the ESP32 until percentage begins |
