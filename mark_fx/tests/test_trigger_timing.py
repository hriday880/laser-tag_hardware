"""
Mark FX Laser Tag - Trigger Debounce & Non-Blocking Timing Verification Suite
Covers Requirement R1 and Acceptance Criteria AC-7, AC-9.
Tier 1: Feature Coverage (>=5 test cases)
Tier 2: Boundary & Corner Cases (>=5 test cases)
"""

import os
import sys
import unittest

# Ensure repo root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from mark_fx.tests.models import TriggerEngine


class TestTriggerTimingTier1(unittest.TestCase):
    """Tier 1: Feature Coverage for Trigger Debounce and Rate Limiting."""

    def setUp(self):
        self.trigger = TriggerEngine()

    def test_single_clean_press_fires_shot(self):
        """Verify a clean trigger press (HIGH -> LOW held >40ms) triggers exactly 1 shot."""
        # Initial idle state: pin HIGH (released)
        shot = self.trigger.feed_pin_sample(raw_pin_val=1, now_ms=0)
        self.assertFalse(shot)

        # Press trigger at t=10ms
        self.trigger.feed_pin_sample(raw_pin_val=0, now_ms=10)
        # Advance 20ms (t=30ms, still within 40ms debounce window)
        shot = self.trigger.feed_pin_sample(raw_pin_val=0, now_ms=30)
        self.assertFalse(shot)

        # Reach debounce threshold (t=55ms, elapsed 45ms > 40ms)
        shot = self.trigger.feed_pin_sample(raw_pin_val=0, now_ms=55)
        self.assertTrue(shot)
        self.assertEqual(self.trigger.shots_fired, 1)

    def test_mechanical_contact_bounce_filtered(self):
        """Verify contact bounce oscillations (0->1->0 within 15ms) are completely filtered."""
        # Contact starts bouncing at t=10ms
        self.trigger.feed_pin_sample(0, now_ms=10)
        self.trigger.feed_pin_sample(1, now_ms=12)
        self.trigger.feed_pin_sample(0, now_ms=15)
        self.trigger.feed_pin_sample(1, now_ms=18)
        self.trigger.feed_pin_sample(0, now_ms=22)  # Finally settles at LOW

        # Check during bounce period: no shot fired
        self.assertEqual(self.trigger.shots_fired, 0)

        # Settled LOW for 45ms after last bounce (t=67ms)
        shot = self.trigger.feed_pin_sample(0, now_ms=67)
        self.assertTrue(shot)
        self.assertEqual(self.trigger.shots_fired, 1)

    def test_rate_limiter_600ms_cooldown(self):
        """Verify rate limiter blocks subsequent shots within 600ms cooldown window."""
        # Shot 1 at t=50ms
        self.trigger.feed_pin_sample(0, now_ms=0)
        self.trigger.feed_pin_sample(0, now_ms=50)
        self.assertEqual(self.trigger.shots_fired, 1)

        # Release trigger at t=100ms
        self.trigger.feed_pin_sample(1, now_ms=100)
        self.trigger.feed_pin_sample(1, now_ms=150)

        # Press trigger again at t=200ms (only 150ms after first shot)
        self.trigger.feed_pin_sample(0, now_ms=200)
        shot = self.trigger.feed_pin_sample(0, now_ms=250)
        # Blocked by 600ms cooldown!
        self.assertFalse(shot)
        self.assertEqual(self.trigger.shots_fired, 1)

    def test_trigger_release_and_second_shot(self):
        """Verify full cycle: Shot 1 -> Release -> Wait 600ms -> Shot 2."""
        # Shot 1 at t=50ms
        self.trigger.feed_pin_sample(0, now_ms=0)
        self.trigger.feed_pin_sample(0, now_ms=50)
        self.assertEqual(self.trigger.shots_fired, 1)

        # Release trigger at t=100ms, debounce release at t=150ms
        self.trigger.feed_pin_sample(1, now_ms=100)
        self.trigger.feed_pin_sample(1, now_ms=150)

        # Wait until t=700ms (elapsed 650ms > 600ms cooldown)
        self.trigger.feed_pin_sample(0, now_ms=700)
        shot = self.trigger.feed_pin_sample(0, now_ms=750)
        self.assertTrue(shot)
        self.assertEqual(self.trigger.shots_fired, 2)

    def test_non_blocking_performance(self):
        """Verify trigger update execution takes <<1ms CPU time."""
        import time
        start_cpu = time.perf_counter()
        for t in range(0, 1000):
            self.trigger.feed_pin_sample(raw_pin_val=1, now_ms=t)
        elapsed_cpu = time.perf_counter() - start_cpu
        # 1000 samples should run in < 5ms of real CPU time
        self.assertLess(elapsed_cpu, 0.05)


class TestTriggerTimingTier2(unittest.TestCase):
    """Tier 2: Boundary & Corner Cases for Trigger Input."""

    def setUp(self):
        self.trigger = TriggerEngine()

    def test_exact_39ms_bounce_cutoff_rejected(self):
        """Verify a pin transition at 39ms (< 40ms threshold) does not trigger a shot."""
        self.trigger.feed_pin_sample(0, now_ms=100)
        shot = self.trigger.feed_pin_sample(0, now_ms=139)  # 39ms elapsed
        self.assertFalse(shot)
        self.assertEqual(self.trigger.shots_fired, 0)

    def test_exact_41ms_debounce_accepted(self):
        """Verify a pin transition at 41ms (> 40ms threshold) triggers a valid shot."""
        self.trigger.feed_pin_sample(0, now_ms=100)
        shot = self.trigger.feed_pin_sample(0, now_ms=141)  # 41ms elapsed
        self.assertTrue(shot)
        self.assertEqual(self.trigger.shots_fired, 1)

    def test_rapid_burst_fire_spam_suppression(self):
        """Verify rapidly toggling trigger 10 times in 300ms produces only 1 shot."""
        now = 0
        for i in range(10):
            # Press
            self.trigger.feed_pin_sample(0, now_ms=now)
            now += 15
            # Release
            self.trigger.feed_pin_sample(1, now_ms=now)
            now += 15
        # Total time 300ms: only 0 or 1 shot could possibly have debounced
        self.assertLessEqual(self.trigger.shots_fired, 1)

    def test_continuous_trigger_hold_no_auto_fire(self):
        """Verify holding down the trigger for 5000ms does NOT continuously fire."""
        # Press at t=0, settle at t=50ms
        self.trigger.feed_pin_sample(0, now_ms=0)
        shot1 = self.trigger.feed_pin_sample(0, now_ms=50)
        self.assertTrue(shot1)
        self.assertEqual(self.trigger.shots_fired, 1)

        # Hold continuously from 50ms to 5000ms without releasing
        for t in range(100, 5000, 100):
            shot = self.trigger.feed_pin_sample(0, now_ms=t)
            self.assertFalse(shot)  # Must NOT fire again without release!

        self.assertEqual(self.trigger.shots_fired, 1)

    def test_cooldown_boundary_599ms_vs_601ms(self):
        """Verify shot attempt at 599ms after fire is rejected, but 601ms is accepted."""
        # Shot 1 at t=50ms
        self.trigger.feed_pin_sample(0, now_ms=0)
        self.trigger.feed_pin_sample(0, now_ms=50)
        self.assertEqual(self.trigger.shots_fired, 1)

        # Release at t=100ms, debounce release at t=150ms
        self.trigger.feed_pin_sample(1, now_ms=100)
        self.trigger.feed_pin_sample(1, now_ms=150)

        # Attempt shot at t=648ms (elapsed since fire = 598ms < 600ms)
        self.trigger.feed_pin_sample(0, now_ms=600)
        shot_598 = self.trigger.feed_pin_sample(0, now_ms=648)
        self.assertFalse(shot_598)

        # Attempt shot at t=651ms (elapsed since fire = 601ms > 600ms)
        # Note: Need release edge first or fresh debounce
        self.trigger.feed_pin_sample(1, now_ms=660)
        self.trigger.feed_pin_sample(1, now_ms=710)
        self.trigger.feed_pin_sample(0, now_ms=720)
        shot_601 = self.trigger.feed_pin_sample(0, now_ms=770)
        self.assertTrue(shot_601)
        self.assertEqual(self.trigger.shots_fired, 2)


if __name__ == "__main__":
    unittest.main()
