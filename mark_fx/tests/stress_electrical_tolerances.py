#!/usr/bin/env python3
"""
Mark FX Laser Tag - Adversarial Electrical Tolerance Stress Suite
Empirical validation of component tolerances under extreme conditions.

Tests:
1. Resistor tolerance variations (±5%, ±10%, ±20% on 100Ω, 110Ω, 220Ω, 330Ω).
2. IR LED forward voltage variations (V_f from 1.15V to 1.60V).
3. ESP32 GPIO internal resistance variations (R_DS(on) from 8Ω to 18Ω).
4. USB rail variations (4.5V to 5.5V) and 3.3V LDO variations (3.15V to 3.45V).
5. Umbilical wire length variations (1.0m to 5.0m) and gauge (26 AWG to 32 AWG).
6. Safety constraint evaluations:
   - IR LED current limit: 15.0mA <= I_LED <= 20.0mA (AC-1)
   - 5-LED HUD total budget: <= 25.0mA (AC-2)
   - ESP32 absolute maximum per GPIO: <= 40.0mA
   - ESP32 recommended continuous maximum per GPIO: <= 20.0mA
   - Umbilical supply voltage at vest: >= 2.50V (TSOP operating minimum)
   - Umbilical signal rise-time: <= 56.0µs (10x faster than 560µs NEC bit pulse)
   - AMS1117 LDO dropout headroom under USB rail variations (4.5V–5.5V)
"""

import sys
import os
import math
import itertools
import random
import unittest
from typing import Dict, List, Tuple, Any

# Ensure project root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from mark_fx.tests.models import ElectricalModel


class ElectricalStressHarness:
    """Adversarial stress-testing physics and tolerance engine."""

    # Parameters from prompt
    TOLERANCES = [0.05, 0.10, 0.20]  # ±5%, ±10%, ±20%
    VF_IR_RANGE = (1.15, 1.60)       # 1.15V to 1.60V
    RDS_ON_RANGE = (8.0, 18.0)        # 8Ω to 18Ω
    VDD_LDO_RANGE = (3.15, 3.45)     # 3.15V to 3.45V (±4.5% LDO tolerance)
    V_USB_RANGE = (4.50, 5.50)       # 4.5V to 5.5V USB specification
    UMBILICAL_LENGTH_RANGE = (1.0, 5.0)  # 1.0m to 5.0m
    WIRE_GAUGES = [26, 28, 30, 32]   # AWG

    # Copper wire resistance per meter (Ω/m at 20°C)
    WIRE_RESISTANCE_PER_M = {
        26: 0.134,
        28: 0.213,
        30: 0.338,
        32: 0.538,
    }

    # Parasitic capacitance per meter of 3-conductor ribbon (pF/m)
    RIBBON_CAPACITANCE_PF_M = 120.0

    # LDO Dropout voltage for AMS1117 (V at ~280mA load)
    AMS1117_DROPOUT_VOLTAGE_NOMINAL = 1.10
    AMS1117_DROPOUT_VOLTAGE_MAX = 1.25

    @classmethod
    def calc_ir_led_current(cls, vdd: float, vf: float, r_ext: float, r_ds: float) -> float:
        """Returns I_LED in mA."""
        total_r = r_ext + r_ds
        if total_r <= 0:
            return float('inf')
        return ((vdd - vf) / total_r) * 1000.0

    @classmethod
    def calc_hud_current(cls, vdd: float, vf_led: float, r_ext: float, r_ds: float, count: int = 5) -> Tuple[float, float]:
        """Returns (current_per_led_ma, total_hud_current_ma)."""
        total_r = r_ext + r_ds
        if total_r <= 0:
            return float('inf'), float('inf')
        i_per_led = ((vdd - vf_led) / total_r) * 1000.0
        return i_per_led, i_per_led * count

    @classmethod
    def calc_umbilical_specs(cls, length_m: float, awg: int, vest_current_ma: float = 3.5, pullup_ohms: float = 6000.0) -> Dict[str, float]:
        """Calculates DC voltage drop and AC rise-time for umbilical cable."""
        r_per_m = cls.WIRE_RESISTANCE_PER_M[awg]
        r_round_trip = 2.0 * length_m * r_per_m
        v_drop_mv = (vest_current_ma / 1000.0) * r_round_trip * 1000.0
        
        # Parasitic capacitance
        c_cable_pf = length_m * cls.RIBBON_CAPACITANCE_PF_M
        c_cable_f = c_cable_pf * 1e-12
        tau_s = pullup_ohms * c_cable_f
        rise_time_us = 2.2 * tau_s * 1e6
        
        return {
            "r_round_trip_ohms": r_round_trip,
            "v_drop_mv": v_drop_mv,
            "c_cable_pf": c_cable_pf,
            "rise_time_us": rise_time_us,
        }

    @classmethod
    def calc_ldo_headroom(cls, v_usb: float, vdd_target: float = 3.30, peak_load_ma: float = 283.1) -> Dict[str, float]:
        """Calculates AMS1117-3.3 linear regulator dropout headroom and dissipation."""
        v_diff = v_usb - vdd_target
        headroom_nominal = v_diff - cls.AMS1117_DROPOUT_VOLTAGE_NOMINAL
        headroom_worst = v_diff - cls.AMS1117_DROPOUT_VOLTAGE_MAX
        
        # Power dissipation
        p_avg_mw = (v_usb - vdd_target) * 135.7
        p_peak_mw = (v_usb - vdd_target) * peak_load_ma
        
        return {
            "v_diff": v_diff,
            "headroom_nominal_v": headroom_nominal,
            "headroom_worst_v": headroom_worst,
            "power_avg_mw": p_avg_mw,
            "power_peak_mw": p_peak_mw,
            "in_dropout": headroom_worst < 0,
        }


class TestAdversarialElectricalTolerances(unittest.TestCase):
    """Unit test suite testing boundary corners and empirical stress."""

    def test_ir_led_nominal_conditions_compliance(self):
        """Verify IR LED at nominal values (3.3V, 1.35V, 100Ω/110Ω, 12Ω) meets 15–20mA."""
        i_100 = ElectricalStressHarness.calc_ir_led_current(3.30, 1.35, 100.0, 12.0)
        i_110 = ElectricalStressHarness.calc_ir_led_current(3.30, 1.35, 110.0, 12.0)
        self.assertAlmostEqual(i_100, 17.41, places=1)
        self.assertAlmostEqual(i_110, 15.98, places=1)
        self.assertTrue(15.0 <= i_100 <= 20.0)
        self.assertTrue(15.0 <= i_110 <= 20.0)

    def test_ir_led_worst_case_overcurrent_adversarial(self):
        """
        Adversarial Test: Check maximum current under worst-case combined tolerance.
        Vdd = 3.45V, Vf = 1.15V, R_ds = 8Ω, R_ext = 100Ω (-5%, -10%, -20%).
        """
        # At -5% tolerance (95Ω)
        i_max_5pct = ElectricalStressHarness.calc_ir_led_current(3.45, 1.15, 95.0, 8.0)
        self.assertAlmostEqual(i_max_5pct, 22.33, places=2)
        # Note: 22.33mA exceeds 20.0mA target!
        self.assertGreater(i_max_5pct, 20.0)
        # But safely under ESP32 absolute maximum (40mA)
        self.assertLess(i_max_5pct, 40.0)

        # At -20% tolerance (80Ω)
        i_max_20pct = ElectricalStressHarness.calc_ir_led_current(3.45, 1.15, 80.0, 8.0)
        self.assertAlmostEqual(i_max_20pct, 26.14, places=2)
        self.assertGreater(i_max_20pct, 20.0)
        self.assertLess(i_max_20pct, 40.0)

    def test_ir_led_worst_case_undercurrent_adversarial(self):
        """
        Adversarial Test: Check minimum current under worst-case combined tolerance.
        Vdd = 3.15V, Vf = 1.60V, R_ds = 18Ω, R_ext = 110Ω (+5%, +10%, +20%).
        """
        # 110Ω at +20% (132Ω)
        i_min_20pct = ElectricalStressHarness.calc_ir_led_current(3.15, 1.60, 132.0, 18.0)
        self.assertAlmostEqual(i_min_20pct, 10.33, places=2)
        # Drops below 15mA range target
        self.assertLess(i_min_20pct, 15.0)

        # 100Ω at +5% (105Ω)
        i_min_100_5pct = ElectricalStressHarness.calc_ir_led_current(3.15, 1.60, 105.0, 18.0)
        self.assertAlmostEqual(i_min_100_5pct, 12.60, places=2)
        self.assertLess(i_min_100_5pct, 15.0)

    def test_hud_330_ohm_red_current_tolerances(self):
        """
        Adversarial Test: Check 5-LED HUD total current with 330Ω resistors across tolerances.
        Vf_red = 1.85V to 1.95V, Vdd = 3.15V to 3.45V, R_ds = 8Ω to 18Ω.
        """
        # Nominal: Vdd=3.3V, Vf=1.90V, R=330Ω, R_ds=12Ω
        _, i_nom_total = ElectricalStressHarness.calc_hud_current(3.30, 1.90, 330.0, 12.0, 5)
        self.assertAlmostEqual(i_nom_total, 20.47, places=1)
        self.assertLess(i_nom_total, 25.0)

        # Worst-case high current with 330Ω ±5% (R_min = 313.5Ω, R_ds = 8Ω, Vdd = 3.45V, Vf = 1.85V)
        _, i_worst_5pct = ElectricalStressHarness.calc_hud_current(3.45, 1.85, 313.5, 8.0, 5)
        # i_per_led = 1.60 / 321.5 = 4.977 mA -> Total = 24.88 mA (< 25.0mA)
        self.assertLess(i_worst_5pct, 25.0)

        # Worst-case high current with 330Ω ±10% (R_min = 297.0Ω)
        _, i_worst_10pct = ElectricalStressHarness.calc_hud_current(3.45, 1.85, 297.0, 8.0, 5)
        # Total = 26.23 mA (exceeds 25mA!)
        self.assertGreater(i_worst_10pct, 25.0)

        # Worst-case with 330Ω ±20% (R_min = 264.0Ω)
        _, i_worst_20pct = ElectricalStressHarness.calc_hud_current(3.45, 1.85, 264.0, 8.0, 5)
        self.assertGreater(i_worst_20pct, 25.0)

    def test_hud_220_ohm_green_adversarial(self):
        """
        Adversarial Test: Check 5-LED HUD total current if 220Ω is used for green LEDs.
        Vf_green = 2.10V, Vdd = 3.3V, R_ds = 12Ω.
        """
        _, i_green_total = ElectricalStressHarness.calc_hud_current(3.30, 2.10, 220.0, 12.0, 5)
        # 1.20V / 232Ω * 5 = 25.86 mA
        self.assertGreater(i_green_total, 25.0)

    def test_umbilical_cable_stress_matrix(self):
        """
        Verify umbilical cable voltage drop and rise time across 1.0m to 5.0m
        and 26 AWG to 32 AWG.
        """
        for length in [1.0, 1.5, 2.5, 5.0]:
            for awg in ElectricalStressHarness.WIRE_GAUGES:
                res = ElectricalStressHarness.calc_umbilical_specs(length, awg, vest_current_ma=4.75)
                # Max voltage drop must not degrade 3.3V supply below 2.5V
                supply_at_vest = 3.15 - (res["v_drop_mv"] / 1000.0)
                self.assertGreater(supply_at_vest, 2.50)
                # Signal rise time must be at least 10x faster than 560µs NEC bit
                self.assertLess(res["rise_time_us"], 56.0)

    def test_usb_rail_ldo_headroom_adversarial(self):
        """
        Adversarial Test: Check AMS1117-3.3 dropout headroom when USB rail sags to 4.5V.
        """
        # Nominal USB 5.0V
        res_5v0 = ElectricalStressHarness.calc_ldo_headroom(5.00)
        self.assertGreater(res_5v0["headroom_nominal_v"], 0.4)
        self.assertFalse(res_5v0["in_dropout"])

        # Extreme low USB 4.50V
        res_4v5 = ElectricalStressHarness.calc_ldo_headroom(4.50)
        # Difference = 4.50 - 3.30 = 1.20V.
        # Max AMS1117 dropout is 1.25V -> Margin is negative (-0.05V) at max load!
        self.assertTrue(res_4v5["in_dropout"] or res_4v5["headroom_worst_v"] <= 0.0)


def run_comprehensive_stress_simulation():
    """Executes full Monte Carlo and exhaustive grid simulation and returns data."""
    print("=" * 80)
    print(" MARK FX MILITARY-GRADE ADVERSARIAL ELECTRICAL TOLERANCE STRESS HARNESS")
    print("=" * 80)

    # ---------------------------------------------------------
    # 1. EXHAUSTIVE CORNER MATRIX: IR LED DIRECT DRIVE (GPIO 4)
    # ---------------------------------------------------------
    print("\n[SECTION 1] EXHAUSTIVE CORNER ANALYSIS: 940nm IR LED DIRECT DRIVE")
    print("-" * 80)
    
    r_nominals = [100.0, 110.0]
    tolerances = [0.00, 0.05, 0.10, 0.20]
    vdd_corners = [3.15, 3.30, 3.45]
    vf_corners = [1.15, 1.25, 1.35, 1.45, 1.60]
    rds_corners = [8.0, 10.0, 12.0, 14.0, 18.0]

    corner_results = []
    for r_nom in r_nominals:
        for tol in tolerances:
            r_vals = [r_nom * (1.0 - tol), r_nom, r_nom * (1.0 + tol)] if tol > 0 else [r_nom]
            currents = []
            for r_ext, vdd, vf, rds in itertools.product(r_vals, vdd_corners, vf_corners, rds_corners):
                i_ma = ElectricalStressHarness.calc_ir_led_current(vdd, vf, r_ext, rds)
                currents.append((i_ma, r_nom, tol, r_ext, vdd, vf, rds))
            
            i_values = [c[0] for c in currents]
            i_min = min(i_values)
            i_max = max(i_values)
            worst_high = max(currents, key=lambda x: x[0])
            worst_low = min(currents, key=lambda x: x[0])
            
            # Count violations of 15mA - 20mA band
            v_high = sum(1 for i in i_values if i > 20.0)
            v_low = sum(1 for i in i_values if i < 15.0)
            v_gpio40 = sum(1 for i in i_values if i > 40.0)
            
            corner_results.append({
                "r_nom": r_nom,
                "tol": tol,
                "count": len(i_values),
                "min": i_min,
                "max": i_max,
                "worst_high": worst_high,
                "worst_low": worst_low,
                "viol_high_pct": (v_high / len(i_values)) * 100.0,
                "viol_low_pct": (v_low / len(i_values)) * 100.0,
                "viol_gpio40_count": v_gpio40,
            })

    print(f"{'R_nom':<8} {'Tol(±%)':<10} {'Min (mA)':<10} {'Max (mA)':<10} {'High Viol(%)':<14} {'Low Viol(%)':<14} {'GPIO >40mA'}")
    print("-" * 80)
    for cr in corner_results:
        print(f"{cr['r_nom']:<8.0f} {cr['tol']*100:<10.0f} {cr['min']:<10.2f} {cr['max']:<10.2f} {cr['viol_high_pct']:<14.1f} {cr['viol_low_pct']:<14.1f} {cr['viol_gpio40_count']}")

    # ---------------------------------------------------------
    # 2. MONTE CARLO SIMULATION: IR LED DIRECT DRIVE
    # ---------------------------------------------------------
    print("\n[SECTION 2] MONTE CARLO STRESS TEST: 100,000 CYCLES (IR LED DIRECT DRIVE)")
    print("-" * 80)
    random.seed(42)
    mc_iterations = 100000

    for r_nom, tol in [(100.0, 0.05), (100.0, 0.10), (100.0, 0.20), (110.0, 0.05)]:
        mc_currents = []
        for _ in range(mc_iterations):
            # Uniform distributions across specified physical ranges
            vdd = random.uniform(3.15, 3.45)
            vf = random.uniform(1.15, 1.60)
            rds = random.uniform(8.0, 18.0)
            # Resistor tolerance: normal distribution truncated at ±tol, 3-sigma
            r_ext = random.gauss(r_nom, (r_nom * tol) / 3.0)
            r_ext = max(r_nom * (1.0 - tol), min(r_nom * (1.0 + tol), r_ext))
            
            i_ma = ElectricalStressHarness.calc_ir_led_current(vdd, vf, r_ext, rds)
            mc_currents.append(i_ma)
        
        mc_min = min(mc_currents)
        mc_max = max(mc_currents)
        mc_mean = sum(mc_currents) / mc_iterations
        mc_std = math.sqrt(sum((x - mc_mean) ** 2 for x in mc_currents) / mc_iterations)
        pct_over_20ma = (sum(1 for x in mc_currents if x > 20.0) / mc_iterations) * 100.0
        pct_under_15ma = (sum(1 for x in mc_currents if x < 15.0) / mc_iterations) * 100.0
        pct_over_40ma = (sum(1 for x in mc_currents if x > 40.0) / mc_iterations) * 100.0

        print(f"R_nom: {r_nom:.0f}Ω | Tol: ±{tol*100:.0f}%")
        print(f"  Range: [{mc_min:.2f} mA, {mc_max:.2f} mA] | Mean: {mc_mean:.2f} mA ± {mc_std:.2f} mA")
        print(f"  > 20.0 mA (AC-1 upper viol) : {pct_over_20ma:.2f}%")
        print(f"  < 15.0 mA (AC-1 lower viol) : {pct_under_15ma:.2f}%")
        print(f"  > 40.0 mA (ESP32 Abs Max)   : {pct_over_40ma:.2f}%")
        print()

    # ---------------------------------------------------------
    # 3. 5-LED HUD BAR TOLERANCE ANALYSIS
    # ---------------------------------------------------------
    print("\n[SECTION 3] 5-LED HUD BAR CURRENT STRESS ANALYSIS (AC-2: < 25.0 mA Budget)")
    print("-" * 80)
    
    hud_configs = [
        {"color": "Red (330Ω)", "r_nom": 330.0, "vf_range": (1.80, 2.05), "tols": [0.05, 0.10, 0.20]},
        {"color": "Green (220Ω)", "r_nom": 220.0, "vf_range": (2.05, 2.30), "tols": [0.05, 0.10, 0.20]},
        {"color": "Green (330Ω)", "r_nom": 330.0, "vf_range": (2.05, 2.30), "tols": [0.05, 0.10, 0.20]},
    ]

    for cfg in hud_configs:
        print(f"HUD Configuration: {cfg['color']}")
        r_nom = cfg["r_nom"]
        vf_min, vf_max = cfg["vf_range"]
        
        for tol in cfg["tols"]:
            # Monte carlo 50k
            tot_currents = []
            for _ in range(50000):
                vdd = random.uniform(3.15, 3.45)
                vf = random.uniform(vf_min, vf_max)
                rds = random.uniform(8.0, 18.0)
                r_ext = random.uniform(r_nom * (1.0 - tol), r_nom * (1.0 + tol))
                _, i_tot = ElectricalStressHarness.calc_hud_current(vdd, vf, r_ext, rds, count=5)
                tot_currents.append(i_tot)
            
            i_min = min(tot_currents)
            i_max = max(tot_currents)
            i_mean = sum(tot_currents) / len(tot_currents)
            pct_over_25 = (sum(1 for x in tot_currents if x > 25.0) / len(tot_currents)) * 100.0
            
            # Theoretical absolute worst case
            r_abs_min = r_nom * (1.0 - tol)
            _, i_abs_max = ElectricalStressHarness.calc_hud_current(3.45, vf_min, r_abs_min, 8.0, count=5)
            
            print(f"  Tol ±{tol*100:.0f}%: Sim Range [{i_min:.2f}mA - {i_max:.2f}mA] | Mean {i_mean:.2f}mA | Abs Peak {i_abs_max:.2f}mA | >25mA: {pct_over_25:.2f}%")
        print()

    # ---------------------------------------------------------
    # 4. UMBILICAL CABLE ANALYSIS (1.0m to 5.0m, 26–32 AWG)
    # ---------------------------------------------------------
    print("\n[SECTION 4] UMBILICAL INTERCONNECT STRESS ANALYSIS (1.0m–5.0m, 26–32 AWG)")
    print("-" * 80)
    print(f"{'Length (m)':<12} {'AWG':<6} {'R_loop (Ω)':<12} {'V_drop (mV)':<14} {'Vest Supply (V)':<18} {'Rise Time (µs)':<16} {'Integrity'}")
    print("-" * 80)
    
    umb_test_matrix = itertools.product([1.0, 1.5, 2.0, 3.0, 5.0], [26, 28, 30, 32])
    for length, awg in umb_test_matrix:
        res = ElectricalStressHarness.calc_umbilical_specs(length, awg, vest_current_ma=4.75)
        vest_supply_min = 3.15 - (res["v_drop_mv"] / 1000.0)
        # Check against TSOP min supply (2.50V) and NEC bit pulse (560µs)
        safe = (vest_supply_min >= 2.50) and (res["rise_time_us"] <= 56.0)
        status = "PASS" if safe else "FAIL"
        print(f"{length:<12.1f} {awg:<6} {res['r_round_trip_ohms']:<12.3f} {res['v_drop_mv']:<14.2f} {vest_supply_min:<18.3f} {res['rise_time_us']:<16.2f} {status}")

    # ---------------------------------------------------------
    # 5. USB POWER BANK & AMS1117-3.3 REGULATOR STRESS
    # ---------------------------------------------------------
    print("\n[SECTION 5] USB POWER BANK RAIL (4.5V–5.5V) & AMS1117 LDO HEADROOM")
    print("-" * 80)
    print(f"{'USB Rail (V)':<14} {'V_diff (V)':<12} {'Nom Headroom':<16} {'Worst Headroom':<16} {'Peak Power (mW)':<16} {'LDO State'}")
    print("-" * 80)
    
    for v_usb in [4.50, 4.60, 4.75, 5.00, 5.25, 5.50]:
        res = ElectricalStressHarness.calc_ldo_headroom(v_usb)
        state = "DROPOUT RISK" if res["in_dropout"] else "REGULATING"
        print(f"{v_usb:<14.2f} {res['v_diff']:<12.2f} {res['headroom_nominal_v']:<16.2f} {res['headroom_worst_v']:<16.2f} {res['power_peak_mw']:<16.1f} {state}")

    print("=" * 80)


if __name__ == "__main__":
    run_comprehensive_stress_simulation()
    print("\nRunning unittest test suite...")
    unittest.main()
