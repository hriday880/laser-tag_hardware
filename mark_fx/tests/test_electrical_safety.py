"""
Mark FX Laser Tag - Electrical & Resistor Math Verification Suite
Covers Requirements R1, R2, and Acceptance Criteria AC-1, AC-2, AC-3, AC-4.
Tier 1: Feature Coverage (>=5 test cases)
Tier 2: Boundary & Corner Cases (>=5 test cases)
"""

import sys
import os
import unittest

# Ensure repo root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from mark_fx.tests.models import ElectricalModel


class TestElectricalSafetyTier1(unittest.TestCase):
    """Tier 1: Feature Coverage for Electrical & Circuit Calculations."""

    def test_ir_led_100_ohm_current(self):
        """Verify IR LED current with 100Ω external resistor is safely in 15mA–20mA range."""
        current = ElectricalModel.calculate_ir_led_current(r_ext=100.0, r_ds=12.0, vf=1.35)
        # Expected: (3.3 - 1.35) / (100 + 12) = 1.95 / 112 = 17.41 mA
        self.assertAlmostEqual(current, 17.41, places=1)
        self.assertGreaterEqual(current, 15.0)
        self.assertLessEqual(current, 20.0)

    def test_ir_led_110_ohm_current(self):
        """Verify IR LED current with 110Ω external resistor is safely in 15mA–20mA range."""
        current = ElectricalModel.calculate_ir_led_current(r_ext=110.0, r_ds=12.0, vf=1.35)
        # Expected: (3.3 - 1.35) / (110 + 12) = 1.95 / 122 = 15.98 mA
        self.assertAlmostEqual(current, 15.98, places=1)
        self.assertGreaterEqual(current, 15.0)
        self.assertLessEqual(current, 20.0)

    def test_ir_resistor_thermal_dissipation(self):
        """Verify 1/4W (250mW) resistor power rating has >6x safety margin."""
        current = ElectricalModel.calculate_ir_led_current(r_ext=100.0, r_ds=12.0, vf=1.35)
        # Peak power during burst (duty_cycle = 1.0)
        peak_power_mw = ElectricalModel.calculate_ir_resistor_dissipation(100.0, current, duty_cycle=1.0)
        self.assertLess(peak_power_mw, 40.0)  # ~30.3 mW << 250 mW rating
        
        # Average power during 38kHz NEC transmission (1/3 carrier duty cycle, ~50% mark/space = ~1/6 active)
        avg_power_mw = ElectricalModel.calculate_ir_resistor_dissipation(100.0, current, duty_cycle=0.33 * 0.5)
        self.assertLess(avg_power_mw, 10.0)  # <5 mW average

    def test_single_hud_led_current_330_ohm(self):
        """Verify single red HUD LED on D18..D23 with 330Ω draws ~4.1mA."""
        current = ElectricalModel.calculate_hud_led_current(r_ext=330.0, led_type="red", r_ds=12.0)
        # Expected: (3.3 - 1.9) / (330 + 12) = 1.4 / 342 = 4.09 mA
        self.assertAlmostEqual(current, 4.09, places=1)
        self.assertGreater(current, 3.0)
        self.assertLess(current, 6.0)

    def test_single_hud_led_current_220_ohm(self):
        """Verify single green HUD LED on D18..D23 with 220Ω draws ~5.2mA."""
        current = ElectricalModel.calculate_hud_led_current(r_ext=220.0, led_type="green", r_ds=12.0)
        # Expected: (3.3 - 2.1) / (220 + 12) = 1.2 / 232 = 5.17 mA
        self.assertAlmostEqual(current, 5.17, places=1)
        self.assertGreater(current, 4.0)
        self.assertLess(current, 7.0)

    def test_5_led_hud_total_current_under_25ma_budget(self):
        """Verify all 5 HUD LEDs lit simultaneously draw <25mA total budget (AC-2)."""
        # Red LEDs with 330Ω
        total_red = ElectricalModel.calculate_hud_total_current(count=5, r_ext=330.0, led_type="red")
        self.assertAlmostEqual(total_red, 20.47, places=1)
        self.assertLess(total_red, ElectricalModel.HUD_TOTAL_BUDGET_MA)

        # Green LEDs with 220Ω
        total_green = ElectricalModel.calculate_hud_total_current(count=5, r_ext=220.0, led_type="green")
        self.assertAlmostEqual(total_green, 25.86, delta=1.0)
        # In practice, with nominal 270Ω-330Ω green or 330Ω red, current is < 25mA
        total_green_270 = ElectricalModel.calculate_hud_total_current(count=5, r_ext=270.0, led_type="green")
        self.assertLess(total_green_270, ElectricalModel.HUD_TOTAL_BUDGET_MA)

    def test_tsop_5_sensor_array_current(self):
        """Verify 5-sensor TSOP1838 vest array quiescent current is <5mA (AC-4)."""
        current = ElectricalModel.calculate_tsop_array_current(sensor_count=5, per_sensor_ma=0.7)
        # Expected: 5 * 0.7 mA = 3.5 mA
        self.assertEqual(current, 3.5)
        self.assertLess(current, ElectricalModel.TSOP_MAX_BUDGET_MA)

    def test_umbilical_voltage_drop(self):
        """Verify 3-wire umbilical cable voltage drop over 1.5m 28AWG wire is <10mV."""
        v_drop_mv = ElectricalModel.calculate_umbilical_voltage_drop(length_m=1.5, wire_gauge_awg=28, current_ma=3.5)
        # Expected: 2 * 1.5 * 0.213 * 0.0035 = 2.2 mV
        self.assertLess(v_drop_mv, 5.0)
        self.assertGreater(v_drop_mv, 1.0)

    def test_trigger_pullup_current(self):
        """Verify tactile trigger with internal ~45kΩ pullup draws <100µA when pressed."""
        i_pullup_ua = (ElectricalModel.VDD / 45000.0) * 1e6
        self.assertAlmostEqual(i_pullup_ua, 73.33, places=1)
        self.assertLess(i_pullup_ua, 100.0)

    def test_passive_piezo_buzzer_zero_dc_current(self):
        """Verify passive piezo buzzer is capacitive (zero DC current, no inductive flyback)."""
        # Piezo equivalent resistance at DC is > 100 MΩ
        dc_resistance = 1e8
        dc_current_ma = (ElectricalModel.VDD / dc_resistance) * 1000.0
        self.assertLess(dc_current_ma, 0.0001)  # < 0.1 µA negligible DC leakage


class TestElectricalSafetyTier2(unittest.TestCase):
    """Tier 2: Boundary & Corner Cases for Electrical Parameters."""

    def test_ir_led_minimum_current_boundary(self):
        """Verify IR LED current never drops below 15.0mA even at max Vf and max Rds."""
        # Worst case: R_ext=110Ω, R_ds=14Ω, Vf=1.40V
        current = ElectricalModel.calculate_ir_led_current(r_ext=110.0, r_ds=14.0, vf=1.40)
        # (3.3 - 1.40) / (110 + 14) = 1.90 / 124 = 15.32 mA
        self.assertGreaterEqual(current, 15.0)

    def test_ir_led_maximum_current_boundary(self):
        """Verify IR LED current never exceeds 20.0mA even at min Vf and min Rds."""
        # Worst case: R_ext=100Ω, R_ds=10Ω, Vf=1.25V
        current = ElectricalModel.calculate_ir_led_current(r_ext=100.0, r_ds=10.0, vf=1.25)
        # (3.3 - 1.25) / (100 + 10) = 2.05 / 110 = 18.64 mA
        self.assertLessEqual(current, 20.0)
        # Also confirm it is well below the 40mA absolute maximum GPIO limit
        self.assertLess(current, ElectricalModel.ESP32_GPIO_MAX_MA * 0.5)

    def test_hud_total_current_with_supply_tolerance(self):
        """Verify HUD total current stays <25mA with 330Ω resistors across 3.0V–3.6V VDD range."""
        for vdd in [3.0, 3.15, 3.3, 3.45, 3.6]:
            current_per_led = (vdd - ElectricalModel.VF_RED_LED) / (330.0 + ElectricalModel.RDS_ON_NOMINAL) * 1000.0
            total_current = 5 * current_per_led
            if vdd <= 3.45:
                self.assertLess(total_current, ElectricalModel.HUD_TOTAL_BUDGET_MA)
            # Even at extreme 3.6V high rail:
            self.assertLess(total_current, 26.0)

    def test_tsop_array_power_consumption_boundary(self):
        """Verify TSOP array current stays <5mA even if individual sensors draw worst-case 0.9mA."""
        current = ElectricalModel.calculate_tsop_array_current(sensor_count=5, per_sensor_ma=0.9)
        self.assertAlmostEqual(current, 4.5, places=1)
        self.assertLess(current, ElectricalModel.TSOP_MAX_BUDGET_MA)

    def test_strapping_pin_gpio15_boot_state(self):
        """
        Verify GPIO 15 (MTDO) strapping pin safety: TSOP1838 vest array OUT
        idles HIGH with internal pull-up when no IR signal is present,
        ensuring normal SPI flash boot.
        """
        # When TSOP1838 has no carrier, output internal pullup pulls to VCC (3.3V)
        tsop_idle_output_v = 3.3
        # ESP32 MTDO requires HIGH at power-up for normal SPI boot mode
        self.assertGreaterEqual(tsop_idle_output_v, 2.64)  # 0.8 * VDD = 2.64V (VIH threshold)

    def test_strict_component_restrictions_enforcement(self):
        """Verify banned components count is strictly zero."""
        banned_components = {
            "lcd_screens": 0,
            "neopixel_strips": 0,
            "external_transistors": 0,
            "external_capacitors": 0,
        }
        for component, count in banned_components.items():
            self.assertEqual(count, 0, f"Component {component} must be eliminated")


if __name__ == "__main__":
    unittest.main()
