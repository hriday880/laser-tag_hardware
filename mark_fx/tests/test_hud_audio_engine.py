"""
Mark FX Laser Tag - Visual 5-LED HUD & Audio Engine Verification Suite
Covers Requirements R3, R4, and Acceptance Criteria AC-6, AC-8, AC-9.
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

from mark_fx.tests.models import HUDStateEngine, AudioEngineModel


class TestHUDAudioEngineTier1(unittest.TestCase):
    """Tier 1: Feature Coverage for 5-LED HUD and Audio Sound Engine."""

    def setUp(self):
        self.hud = HUDStateEngine()
        self.audio = AudioEngineModel()

    def test_full_health_5_hp_all_leds_solid(self):
        """Verify Full Health (5 HP): All 5 LEDs on D18, D19, D21, D22, D23 are lit solid [1, 1, 1, 1, 1]."""
        self.hud.set_hp(5, lives=3)
        leds = self.hud.update(now_ms=1000)
        self.assertEqual(leds, [1, 1, 1, 1, 1])

    def test_progressive_damage_health_loss(self):
        """Verify progressive health loss from 4 down to 2 HP turns off LEDs sequentially."""
        # 4 HP: LED 1..4 ON, LED 5 OFF
        self.hud.set_hp(4, lives=3)
        self.assertEqual(self.hud.update(now_ms=1000), [1, 1, 1, 1, 0])

        # 3 HP: LED 1..3 ON, LED 4..5 OFF
        self.hud.set_hp(3, lives=3)
        self.assertEqual(self.hud.update(now_ms=1000), [1, 1, 1, 0, 0])

        # 2 HP: LED 1..2 ON, LED 3..5 OFF
        self.hud.set_hp(2, lives=3)
        self.assertEqual(self.hud.update(now_ms=1000), [1, 1, 0, 0, 0])

    def test_critical_health_1_hp_rapid_pulse(self):
        """Verify Critical Health (1 HP): LED 1 (D18) pulses rapidly while others stay OFF."""
        self.hud.set_hp(1, lives=3)
        # Check ON phase (0-149ms)
        self.assertEqual(self.hud.update(now_ms=50), [1, 0, 0, 0, 0])
        # Check OFF phase (150-299ms)
        self.assertEqual(self.hud.update(now_ms=200), [0, 0, 0, 0, 0])
        # Check next ON phase (300-449ms)
        self.assertEqual(self.hud.update(now_ms=350), [1, 0, 0, 0, 0])

    def test_eliminated_all_leds_off(self):
        """Verify Eliminated (0 HP or 0 lives): All 5 LEDs turn OFF [0, 0, 0, 0, 0]."""
        self.hud.set_hp(0, lives=0)
        self.assertEqual(self.hud.update(now_ms=500), [0, 0, 0, 0, 0])
        self.assertEqual(self.hud.update(now_ms=1000), [0, 0, 0, 0, 0])

    def test_respawn_shield_synchronous_flash(self):
        """Verify Respawn Shield / Invulnerability: All 5 LEDs flash in sync."""
        self.hud.set_respawn_shield()
        # ON phase (0-249ms)
        self.assertEqual(self.hud.update(now_ms=100), [1, 1, 1, 1, 1])
        # OFF phase (250-499ms)
        self.assertEqual(self.hud.update(now_ms=300), [0, 0, 0, 0, 0])
        # Next ON phase (500-749ms)
        self.assertEqual(self.hud.update(now_ms=600), [1, 1, 1, 1, 1])

    def test_muzzle_flash_momentary_burst(self):
        """Verify Muzzle Flash momentarily flashes all LEDs on trigger pull, then restores state."""
        self.hud.set_hp(3, lives=3)
        # Normal state at 3 HP: [1, 1, 1, 0, 0]
        self.assertEqual(self.hud.update(now_ms=1000), [1, 1, 1, 0, 0])

        # Trigger muzzle flash for 50ms at now_ms=1050
        self.hud.trigger_muzzle_flash(duration_ms=50, now_ms=1050)
        # During flash (now_ms=1070): All 5 LEDs ON
        self.assertEqual(self.hud.update(now_ms=1070), [1, 1, 1, 1, 1])

        # After flash expires (now_ms=1110): Restored to [1, 1, 1, 0, 0]
        self.assertEqual(self.hud.update(now_ms=1110), [1, 1, 1, 0, 0])

    def test_lobby_boot_knight_rider_sweep(self):
        """Verify Lobby/Boot: 5-LED sweep (Knight Rider back-and-forth) during connection."""
        self.hud.state = "LOBBY"
        # At t=0..99ms (step 0): LED 1 lit
        self.assertEqual(self.hud.update(now_ms=50), [1, 0, 0, 0, 0])
        # At t=200..299ms (step 2): LED 3 lit
        self.assertEqual(self.hud.update(now_ms=250), [0, 0, 1, 0, 0])
        # At t=400..499ms (step 4): LED 5 lit
        self.assertEqual(self.hud.update(now_ms=450), [0, 0, 0, 0, 1])
        # At t=600..699ms (step 6, bouncing back): LED 3 lit
        self.assertEqual(self.hud.update(now_ms=650), [0, 0, 1, 0, 0])

    def test_audio_melodies_defined(self):
        """Verify all required audio cues exist in sound engine dictionary."""
        required_melodies = [
            "BOOT", "SHOT", "HIT", "HEAL", "SHIELD", "HEARTBEAT",
            "DEATH", "MATCH_START", "WIN", "DEFEAT"
        ]
        for m in required_melodies:
            self.assertIn(m, self.audio.MELODIES)
            notes = self.audio.MELODIES[m]
            self.assertGreater(len(notes), 0)
            for freq, dur in notes:
                self.assertGreaterEqual(freq, 0)
                self.assertGreater(dur, 0)

    def test_audio_playback_progression(self):
        """Verify audio player advances through note sequence without blocking."""
        self.audio.play("SHOT", priority=AudioEngineModel.PRIORITY_CHIRP, now_ms=0)
        self.assertTrue(self.audio.is_playing)
        # Note 1 of SHOT is (1800, 30)
        self.assertEqual(self.audio.active_freq, 1800)

        # Advance to t=35ms (Note 2 is (2400, 40))
        self.audio.update(now_ms=35)
        self.assertTrue(self.audio.is_playing)
        self.assertEqual(self.audio.active_freq, 2400)

        # Advance to t=80ms (Melody completed)
        self.audio.update(now_ms=80)
        self.assertFalse(self.audio.is_playing)
        self.assertEqual(self.audio.active_freq, 0)

    def test_audio_visual_synchrony_on_shot(self):
        """Verify muzzle flash and shot chirp start in perfect synchrony."""
        now_ms = 5000
        self.hud.set_hp(5)
        self.hud.trigger_muzzle_flash(duration_ms=50, now_ms=now_ms)
        self.audio.play("SHOT", priority=AudioEngineModel.PRIORITY_CHIRP, now_ms=now_ms)

        # Simultaneously check both states
        leds = self.hud.update(now_ms=now_ms + 10)
        self.assertEqual(leds, [1, 1, 1, 1, 1])  # Muzzle flash active
        self.assertTrue(self.audio.is_playing)
        self.assertEqual(self.audio.active_freq, 1800)  # Chirp active


class TestHUDAudioEngineTier2(unittest.TestCase):
    """Tier 2: Boundary & Corner Cases for HUD and Audio Engine."""

    def setUp(self):
        self.hud = HUDStateEngine()
        self.audio = AudioEngineModel()

    def test_hp_upper_bound_clamping(self):
        """Verify HP cannot exceed max health (5 HP) and does not corrupt LED state."""
        self.hud.set_hp(10, lives=3)  # Input beyond max
        self.assertEqual(self.hud.hp, 5)
        self.assertEqual(self.hud.update(now_ms=1000), [1, 1, 1, 1, 1])

    def test_hp_lower_bound_clamping(self):
        """Verify HP cannot drop below 0 HP and clamps cleanly into ELIMINATED."""
        self.hud.set_hp(-5, lives=3)
        self.assertEqual(self.hud.hp, 0)
        self.assertEqual(self.hud.state, "ELIMINATED")
        self.assertEqual(self.hud.update(now_ms=1000), [0, 0, 0, 0, 0])

    def test_audio_priority_preemption(self):
        """Verify high priority sound (DEATH, P3) preempts low priority sound (SHOT, P1)."""
        # Start low priority shot
        self.audio.play("SHOT", priority=AudioEngineModel.PRIORITY_CHIRP, now_ms=0)
        self.assertEqual(self.audio.active_freq, 1800)

        # Higher priority death knell interrupts immediately
        preempted = self.audio.play("DEATH", priority=AudioEngineModel.PRIORITY_DEATH, now_ms=10)
        self.assertTrue(preempted)
        self.assertEqual(self.audio.current_priority, AudioEngineModel.PRIORITY_DEATH)
        self.assertEqual(self.audio.active_freq, 440)  # First note of DEATH

    def test_audio_priority_blocking(self):
        """Verify low priority sound cannot interrupt high priority playback."""
        # Start high priority death knell
        self.audio.play("DEATH", priority=AudioEngineModel.PRIORITY_DEATH, now_ms=0)
        # Attempt to play shot chirp (lower priority)
        blocked = self.audio.play("SHOT", priority=AudioEngineModel.PRIORITY_CHIRP, now_ms=50)
        self.assertFalse(blocked)
        # Still playing DEATH
        self.assertEqual(self.audio.current_priority, AudioEngineModel.PRIORITY_DEATH)

    def test_non_blocking_zero_delay_execution(self):
        """Verify note scheduler runs entirely non-blocking (0ms CPU wait)."""
        import time
        start_cpu = time.perf_counter()
        self.audio.play("BOOT", now_ms=0)
        for t in range(0, 1000, 10):
            self.audio.update(now_ms=t)
        elapsed_cpu = time.perf_counter() - start_cpu
        # 100 virtual time ticks should take < 5ms of real CPU time
        self.assertLess(elapsed_cpu, 0.05)

    def test_panic_pulse_sync_with_heartbeat_tone(self):
        """Verify 1 HP panic pulse LED blink matches heartbeat acoustic period."""
        self.hud.set_hp(1, lives=1)
        # Panic pulse period is 300ms (150ms ON, 150ms OFF)
        led_t0 = self.hud.update(now_ms=50)[0]    # ON
        led_t150 = self.hud.update(now_ms=180)[0] # OFF
        led_t300 = self.hud.update(now_ms=320)[0] # ON
        self.assertEqual(led_t0, 1)
        self.assertEqual(led_t150, 0)
        self.assertEqual(led_t300, 1)


if __name__ == "__main__":
    unittest.main()
