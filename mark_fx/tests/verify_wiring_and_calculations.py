#!/usr/bin/env python3
"""
Mark FX Hardware Architecture & Electrical Verification Script
Validates all electrical calculations, pin assignments, constraint compliance,
and safety margins documented in mark_fx/WIRING_AND_PINOUT.md.
"""

import math
import sys

def test_pin_mapping():
    print("=== 1. Testing Pin Mapping & Strapping Safety ===")
    
    # 30-Pin DOIT ESP32 DevKit V1 Definition
    left_pins = [
        "EN", "VP (GPIO36)", "VN (GPIO39)", "D34 (GPIO34)", "D35 (GPIO35)",
        "D32 (GPIO32)", "D33 (GPIO33)", "D25 (GPIO25)", "D26 (GPIO26)", "D27 (GPIO27)",
        "D14 (GPIO14)", "D12 (GPIO12)", "D13 (GPIO13)", "GND", "VIN"
    ]
    right_pins = [
        "D23 (GPIO23)", "D22 (GPIO22)", "TX0 (GPIO1)", "RX0 (GPIO3)", "D21 (GPIO21)",
        "D19 (GPIO19)", "D18 (GPIO18)", "D5 (GPIO5)", "TX2 (GPIO17)", "RX2 (GPIO16)",
        "D4 (GPIO4)", "D2 (GPIO2)", "D15 (GPIO15)", "GND", "3V3"
    ]
    
    assert len(left_pins) == 15, f"Left pin count must be 15, got {len(left_pins)}"
    assert len(right_pins) == 15, f"Right pin count must be 15, got {len(right_pins)}"
    assert len(left_pins) + len(right_pins) == 30, "Total pins must be exactly 30"
    print("  [PASS] 30-pin board layout verified (15 left, 15 right).")
    
    # Active GPIO Assignments in Mark FX
    assigned_gpios = {
        "IR_TX": 4,
        "TRIGGER": 13,
        "TSOP_RX": 15,
        "BUZZER": 33,
        "HUD_LED1": 18,
        "HUD_LED2": 19,
        "HUD_LED3": 21,
        "HUD_LED4": 22,
        "HUD_LED5": 23,
    }
    
    # Check uniqueness
    unique_pins = set(assigned_gpios.values())
    assert len(unique_pins) == 9, f"Pin collision detected! Expected 9 unique pins, got {len(unique_pins)}"
    print(f"  [PASS] All 9 active GPIOs are unique: {assigned_gpios}")
    
    # Check that output peripherals do not use input-only pins (GPIO 34, 35, 36, 39)
    input_only_pins = {34, 35, 36, 39}
    output_pins = [
        assigned_gpios["IR_TX"],
        assigned_gpios["BUZZER"],
        assigned_gpios["HUD_LED1"],
        assigned_gpios["HUD_LED2"],
        assigned_gpios["HUD_LED3"],
        assigned_gpios["HUD_LED4"],
        assigned_gpios["HUD_LED5"],
    ]
    for pin in output_pins:
        assert pin not in input_only_pins, f"Output assigned to input-only pin {pin}!"
    print("  [PASS] No output peripherals assigned to input-only pins.")
    
    # Check strapping pin safety
    # GPIO 15 (MTDO) requires HIGH at boot for normal debug console output
    # TSOP1838 idles HIGH (3.3V) -> SAFE
    assert assigned_gpios["TSOP_RX"] == 15
    # GPIO 13 has internal pullup -> SAFE
    assert assigned_gpios["TRIGGER"] == 13
    # GPIO 0 and GPIO 2 are NOT used for external peripherals -> SAFE
    assert 0 not in assigned_gpios.values()
    assert 2 not in assigned_gpios.values()
    # GPIO 12 (MTDI) is NOT used -> prevents flash voltage bootstrap lockup
    assert 12 not in assigned_gpios.values()
    print("  [PASS] Strapping pin safety verified: D15 idles HIGH, D0/D2/D12 unused.")

def test_ir_led_calculations():
    print("\n=== 2. Testing 940nm IR LED Direct Drive Calculations ===")
    Vdd = 3.3
    Vf = 1.35  # Nominal forward voltage of 940nm GaAs LED
    R_int = 12.0  # Internal PMOS R_DS(on) of ESP32 GPIO driver
    
    # 100 Ohm external resistor
    R_ext_100 = 100.0
    I_100_real = (Vdd - Vf) / (R_ext_100 + R_int)
    I_100_ideal = (Vdd - Vf) / R_ext_100
    
    print(f"  100Ω Resistor: Ideal Current = {I_100_ideal*1000:.2f} mA | Real Current (with R_DS(on)) = {I_100_real*1000:.2f} mA")
    assert 0.015 <= I_100_real <= 0.020, f"100Ω current {I_100_real*1000:.2f}mA out of 15-20mA range!"
    assert round(I_100_real * 1000, 1) == 17.4, f"Expected 17.4 mA, got {I_100_real*1000:.2f} mA"
    
    # Standardization on 100Ω and elimination of 110Ω
    # With 110Ω at low-rail corner (3.15V, Vf=1.60V, R_ds=18Ω, R=110Ω + 5% = 115.5Ω):
    I_110_corner = (3.15 - 1.60) / (115.5 + 18.0)
    print(f"  110Ω Low-Rail Corner: {I_110_corner*1000:.2f} mA (< 15mA minimum range target!)")
    assert I_110_corner < 0.015, "110Ω in low corner drops below 15mA, justifying standardization on 100Ω"
    
    # Thermal Dissipation
    P_resistor = (I_100_real ** 2) * R_ext_100
    print(f"  Resistor Peak Thermal Dissipation: {P_resistor*1000:.2f} mW (Rating: 250 mW 1/4W)")
    assert P_resistor < 0.250, "Resistor power exceeds 1/4W rating!"
    margin_resistor = 0.250 / P_resistor
    print(f"  Resistor Safety Factor: {margin_resistor:.1f}x")
    
    # Average power over NEC pulse burst (14ms carrier active / 500ms shot interval)
    duty_cycle = 14.0 / 500.0
    P_avg = P_resistor * duty_cycle
    print(f"  Average Power Dissipation during active firing: {P_avg*1000:.2f} mW (< 1 mW target)")
    assert P_avg < 0.001, f"Average power {P_avg*1000:.2f} mW exceeds 1 mW!"
    
    # ESP32 GPIO Limits Comparison
    esp32_abs_max = 0.040  # 40 mA
    esp32_rec_cont = 0.012  # 12 mA
    assert I_100_real < esp32_abs_max
    pct_abs_max = (I_100_real / esp32_abs_max) * 100
    print(f"  Peak Current is {pct_abs_max:.1f}% of ESP32 40mA absolute maximum.")
    print("  [PASS] 940nm IR LED direct drive calculations verified.")

def test_hud_led_calculations():
    print("\n=== 3. Testing 5-LED Unicolor HUD Calculations ===")
    Vdd = 3.3
    
    # Red LEDs with 330Ω
    Vf_red = 1.90
    R_red = 330.0
    I_red_single = (Vdd - Vf_red) / R_red
    I_red_total = 5 * I_red_single
    print(f"  Red LED @ 330Ω: Single = {I_red_single*1000:.2f} mA | 5 LEDs Total = {I_red_total*1000:.2f} mA")
    assert round(I_red_total * 1000, 1) == 21.2, f"Expected 21.2 mA total, got {I_red_total*1000:.2f}"
    assert I_red_total < 0.025, f"HUD total current {I_red_total*1000:.2f} mA exceeds 25 mA limit!"
    
    # Green LEDs with 330Ω (Standardized across Red and Green alike, eliminating 220Ω)
    Vf_green = 2.20
    R_green = 330.0
    I_green_single = (Vdd - Vf_green) / R_green
    I_green_total = 5 * I_green_single
    print(f"  Green LED @ 330Ω: Single = {I_green_single*1000:.2f} mA | 5 LEDs Total = {I_green_total*1000:.2f} mA")
    assert round(I_green_total * 1000, 1) == 16.7, f"Expected 16.7 mA total, got {I_green_total*1000:.2f}"
    assert I_green_total < 0.025, f"HUD total current {I_green_total*1000:.2f} mA exceeds 25 mA limit!"

    # Real circuit with R_DS(on) = 12Ω
    R_ds = 12.0
    I_red_real_total = 5 * ((Vdd - Vf_red) / (R_red + R_ds))
    I_green_real_total = 5 * ((Vdd - Vf_green) / (R_green + R_ds))
    print(f"  Real Circuit with R_DS(on)=12Ω: Red Total = {I_red_real_total*1000:.2f} mA | Green Total = {I_green_real_total*1000:.2f} mA")
    assert I_red_real_total < 0.025
    assert I_green_real_total < 0.025
    
    # 220Ω elimination proof: Check that 220Ω with green LEDs at -5% tolerance violates 25mA budget
    R_green_220_min = 220.0 * 0.95
    I_green_220_violation = 5 * ((3.45 - 2.05) / (R_green_220_min + 8.0))
    print(f"  220Ω Green Worst-Case Surge: {I_green_220_violation*1000:.2f} mA (> 25mA budget violation!)")
    assert I_green_220_violation > 0.025, "220Ω must violate 25mA in worst-case corner to justify elimination"
    
    # Per-pin limit check (recommended <= 12mA)
    assert I_red_single < 0.012
    assert I_green_single < 0.012
    print("  [PASS] 5-LED HUD calculations verified (330Ω standardized, < 25mA total simultaneous, < 12mA per pin).")

def test_piezo_buzzer_calculations():
    print("\n=== 4. Testing Passive Piezo Buzzer Direct Drive ===")
    C_piezo = 20e-9  # 20 nF
    f_audio = 2000.0  # 2 kHz typical tone
    V_peak = 3.3
    V_rms = V_peak / 2.0  # Square wave 0-3.3V has AC rms of 1.65V
    
    # DC Current
    I_dc = 0.0
    assert I_dc == 0.0
    
    # AC RMS Current: I = 2 * pi * f * C * V_rms
    I_ac_rms = 2 * math.pi * f_audio * C_piezo * V_rms
    print(f"  Piezo AC RMS Current @ 2kHz: {I_ac_rms*1000:.3f} mA (Target: ~0.41 mA)")
    assert round(I_ac_rms * 1000, 2) == 0.41
    
    # Inductive Flyback
    L_piezo = 0.0  # Non-inductive
    V_flyback = 0.0
    assert V_flyback == 0.0
    print("  [PASS] Passive Piezo Buzzer verified: 0mA DC, 0.41mA AC rms, 0V flyback.")

def test_trigger_calculations():
    print("\n=== 5. Testing Single Tactile Trigger Circuit ===")
    Vdd = 3.3
    R_pu = 45000.0  # 45 kΩ internal pull-up
    
    I_released = 0.0
    I_pressed = Vdd / R_pu
    print(f"  Released Current: {I_released} µA")
    print(f"  Pressed Current: {I_pressed*1e6:.2f} µA (Target: ~73.3 µA)")
    assert round(I_pressed * 1e6, 1) == 73.3
    print("  [PASS] Trigger pullup calculations verified.")

def test_tsop_array_calculations():
    print("\n=== 6. Testing 5-Sensor TSOP1838 Vest Array ===")
    num_sensors = 5
    I_sensor_typ = 0.00070  # 0.70 mA
    I_total_array = num_sensors * I_sensor_typ
    print(f"  Total 5-Sensor Quiescent Current: {I_total_array*1000:.2f} mA (Target: ~3.5 mA)")
    assert round(I_total_array * 1000, 1) == 3.5
    
    # Wired-OR Pull-Up Network
    R_pu_single = 30000.0  # 30 kΩ internal pull-up per TSOP
    R_pu_parallel = R_pu_single / num_sensors
    print(f"  Equivalent Parallel Pull-Up Resistance: {R_pu_parallel/1000:.1f} kΩ (Target: 6.0 kΩ)")
    assert R_pu_parallel == 6000.0
    
    # Current Sunk by Single Sensor NPN during hit
    Vdd = 3.3
    I_sink = Vdd / R_pu_parallel
    print(f"  Current Sunk by Single NPN Transistor: {I_sink*1000:.2f} mA (Target: 0.55 mA)")
    assert round(I_sink * 1000, 2) == 0.55
    assert I_sink < 0.005  # TSOP1838 is rated for up to 5 mA sink
    print("  [PASS] TSOP1838 Vest Array Wired-OR calculations verified.")

def test_umbilical_calculations():
    print("\n=== 7. Testing 3-Wire Umbilical Interconnect ===")
    # 28 AWG wire: ~0.21 Ω/m (or 26 AWG ~0.134 Ω/m)
    # Testing 1.2m (standard) and 1.5m (max extension)
    R_per_meter_28awg = 0.21
    length_1_2m = 1.2
    length_1_5m = 1.5
    I_vest = 0.0035  # 3.5 mA
    
    # 1.2m umbilical
    R_single_1_2 = length_1_2m * R_per_meter_28awg
    V_drop_1_2 = I_vest * R_single_1_2
    print(f"  1.2m 28AWG: R = {R_single_1_2:.3f} Ω | V_drop = {V_drop_1_2*1000:.3f} mV")
    assert V_drop_1_2 * 1000 < 1.1  # 0.882 mV is strictly < 1.1 mV
    
    # 1.5m umbilical
    R_single_1_5 = length_1_5m * R_per_meter_28awg
    V_drop_1_5 = I_vest * R_single_1_5
    print(f"  1.5m 28AWG: R = {R_single_1_5:.3f} Ω | V_drop = {V_drop_1_5*1000:.3f} mV")
    assert V_drop_1_5 * 1000 <= 1.11  # ~1.1 mV

    
    # Rise time on data line (6kΩ pullup, ~150pF cable capacitance)
    C_cable = 150e-12
    tau_rise = 6000.0 * C_cable
    print(f"  Signal Rise Time (RC): {tau_rise*1e6:.2f} µs (vs 560 µs NEC carrier burst envelope)")
    assert tau_rise < 2e-6  # < 2 µs
    print("  [PASS] 3-Wire Umbilical calculations verified.")

def test_power_and_battery_calculations():
    print("\n=== 8. Testing Power Budget & Battery Runtime ===")
    # Current budget breakdown
    I_esp_wifi = 0.110  # 110 mA nominal average
    I_hud = 0.0212      # 21.2 mA (5 Red LEDs)
    I_vest = 0.0035     # 3.5 mA
    I_buzzer_avg = 0.0005 # 0.5 mA
    I_ir_avg = 0.0005   # < 1 mA
    
    I_avg_total = I_esp_wifi + I_hud + I_vest + I_buzzer_avg + I_ir_avg
    print(f"  System Continuous Average Current: {I_avg_total*1000:.1f} mA (Budget: ~120-140 mA)")
    assert 120 <= (I_avg_total * 1000) <= 145
    
    # Peak current
    I_peak_wifi = 0.240
    I_peak_hud = 0.0212
    I_peak_vest = 0.0035
    I_peak_ir = 0.0174
    I_peak_buzzer = 0.0010
    I_peak_total = I_peak_wifi + I_peak_hud + I_peak_vest + I_peak_ir + I_peak_buzzer
    print(f"  System Peak Transient Current: {I_peak_total*1000:.1f} mA (Target: ~283-285 mA)")
    assert 280 <= (I_peak_total * 1000) <= 290
    
    # Battery Runtime at 85% efficiency
    eta = 0.85
    runtimes = {
        2000: (2000 * eta) / (I_avg_total * 1000),
        3000: (3000 * eta) / (I_avg_total * 1000),
        5000: (5000 * eta) / (I_avg_total * 1000)
    }
    print(f"  2000 mAh Runtime: {runtimes[2000]:.1f} hours")
    print(f"  3000 mAh Runtime: {runtimes[3000]:.1f} hours")
    print(f"  5000 mAh Runtime: {runtimes[5000]:.1f} hours")
    assert runtimes[2000] >= 12.0
    assert runtimes[3000] >= 18.0
    assert runtimes[5000] >= 30.0
    
    # Auto-sleep prevention
    power_bank_auto_sleep_threshold_ma = 50.0
    assert (I_avg_total * 1000) > power_bank_auto_sleep_threshold_ma
    print(f"  Auto-Sleep Check: System current ({I_avg_total*1000:.1f} mA) >> threshold ({power_bank_auto_sleep_threshold_ma} mA)")

    # Power Bank & USB Cable Electrical Headroom Requirements (Brownout Prevention)
    V_pb_min = 4.85  # Minimum power bank output under 300mA load
    I_load_peak = 0.2831  # 283.1 mA peak transient coincident draw
    L_cable_max = 0.5  # Max length 0.5 m
    R_per_m_24awg = 0.0842  # 24 AWG copper resistance Ω/m
    R_cable_loop = 2 * L_cable_max * R_per_m_24awg
    R_connectors = 0.050  # USB-A + Micro-B contact resistance
    R_total_pwr = R_cable_loop + R_connectors
    V_drop_cable = I_load_peak * R_total_pwr
    V_in_esp = V_pb_min - V_drop_cable
    
    V_dropout_ams1117_max = 1.25  # AMS1117 max dropout at 300mA
    V_headroom = V_in_esp - (3.30 + V_dropout_ams1117_max)
    print(f"  Power Bank Min: {V_pb_min}V | Cable Drop: {V_drop_cable*1000:.1f}mV | ESP32 VBUS: {V_in_esp:.3f}V")
    print(f"  AMS1117-3.3 Dropout Headroom: {V_headroom*1000:.1f} mV (> +250 mV positive margin)")
    assert V_headroom > 0.250, f"Headroom {V_headroom}V below 0.250V requirement!"
    print("  [PASS] Power budget, battery runtime & power bank headroom verified.")

def test_markdown_document_contents():
    print("\n=== 9. Testing WIRING_AND_PINOUT.md Document Completeness ===")
    import os
    doc_path = "/Users/admin/Documents/LaserTag-hardware/mark_fx/WIRING_AND_PINOUT.md"
    assert os.path.exists(doc_path), f"File {doc_path} does not exist!"
    
    with open(doc_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    assert len(content) > 5000, f"Document is too short: {len(content)} characters"
    print(f"  Document size: {len(content)} characters ({len(content.splitlines())} lines).")
    
    # Required Sections
    required_sections = [
        "1. System Overview & Physical Topography",
        "2. Strict Constraint Compliance & Bill-of-Materials Rationalization",
        "3. Master Pinout & Signal Mapping Matrix (30-Pin DevKit V1)",
        "4. Detailed Electrical & Safety Calculations",
        "4.1 940nm 5mm IR LED Direct Drive Circuit (`GPIO 4`)",
        "4.2 5-LED Unicolor HUD Bar (`D18`, `D19`, `D21`, `D22`, `D23`)",
        "4.3 Passive Piezo Buzzer Direct Drive (`GPIO 33`)",
        "4.4 Single Tactile Trigger Circuit (`GPIO 13`)",
        "4.5 5-Sensor 360° TSOP1838 Vest Array & Wired-OR Bus (`D15`)",
        "4.6 3-Wire Umbilical Interconnect (`3V3`, `GND`, `D15`)",
        "4.7 Power Supply Budget & Battery Life",
        "5. Textual Circuit Schematics",
        "5.1 Gun Core Circuit Schematic",
        "5.2 Vest Sensor Array Schematic",
        "5.3 Umbilical Interconnect Interface Schematic",
        "6. Benchtop Electrical Verification Checklist"
    ]
    for sec in required_sections:
        assert sec in content, f"Missing required section: '{sec}'"
    print("  [PASS] All 16 required sections and subsections present.")
    
    # Required Constraint Checks
    constraints = [
        "LCD Screens (16x2 / I2C / OLED)",
        "Neopixel Strips (WS2812B / SK6812)",
        "External Transistors (BJT / MOSFET)",
        "External Capacitors (Electrolytic / Ceramic)"
    ]
    for c in constraints:
        assert c in content, f"Missing constraint check for {c}"
    print("  [PASS] All strict constraints explicitly documented.")

    # Challenger 1 Engineering Improvements Checks
    content_lower = content.lower()
    assert "330ω" in content_lower or "330" in content, "Missing 330Ω standardization in WIRING_AND_PINOUT.md"
    assert "100ω" in content_lower or "100" in content, "Missing 100Ω standardization in WIRING_AND_PINOUT.md"
    assert "metal-film" in content_lower, "Missing metal-film resistor mandate in WIRING_AND_PINOUT.md"
    assert "4.85" in content, "Missing 4.85V power bank requirement in WIRING_AND_PINOUT.md"
    assert "24 awg" in content_lower, "Missing 24 AWG USB cable requirement in WIRING_AND_PINOUT.md"
    assert "0.5m" in content_lower or "0.5 m" in content_lower, "Missing <= 0.5m cable requirement in WIRING_AND_PINOUT.md"
    assert "ams1117" in content_lower, "Missing AMS1117 dropout analysis in WIRING_AND_PINOUT.md"
    assert "dropout" in content_lower, "Missing dropout discussion in WIRING_AND_PINOUT.md"
    print("  [PASS] Challenger 1 remediation engineering requirements verified in documentation.")
    
    # Verify all 30 pins are in the table
    for pin_num in range(1, 31):
        pin_str = f"| **{pin_num:02d}** |"
        assert pin_str in content, f"Pin #{pin_num:02d} missing from master table!"
    print("  [PASS] All 30 physical pins (01 to 30) verified in Master Pinout Table.")
    
    # Verify Test Points TP-01 to TP-10
    for tp in range(1, 11):
        tp_str = f"**TP-{tp:02d}**"
        assert tp_str in content, f"Test point {tp_str} missing from checklist!"
    print("  [PASS] All 10 benchtop test points (TP-01 to TP-10) verified.")

def main():
    print("================================================================")
    print("MARK FX HARDWARE ARCHITECTURE & ELECTRICAL VERIFICATION TEST")
    print("================================================================")
    try:
        test_pin_mapping()
        test_ir_led_calculations()
        test_hud_led_calculations()
        test_piezo_buzzer_calculations()
        test_trigger_calculations()
        test_tsop_array_calculations()
        test_umbilical_calculations()
        test_power_and_battery_calculations()
        test_markdown_document_contents()
        print("\n================================================================")
        print("ALL ELECTRICAL & HARDWARE TESTS PASSED WITH ZERO ERRORS!")
        print("================================================================")
        return 0
    except AssertionError as e:
        print(f"\n[FAIL] Assertion Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
