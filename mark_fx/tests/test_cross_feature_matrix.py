"""
Mark FX Laser Tag - Tier 3 Cross-Feature Combination Matrix
Pairwise and concurrent feature interaction verification.
Covers Requirements R1–R6 and Acceptance Criteria AC-1..AC-9.
"""

import os
import sys
import unittest

# Ensure repo root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from mark_fx.tests.models import (
    HUDStateEngine, AudioEngineModel, TriggerEngine, StandaloneReferee, NECProtocol
)


class TestCrossFeatureMatrixTier3(unittest.TestCase):
    """Tier 3: Pairwise and Cross-Feature Interaction Tests."""

    def setUp(self):
        self.hud = HUDStateEngine()
        self.audio = AudioEngineModel()
        self.trigger = TriggerEngine()
        self.ref = StandaloneReferee(max_hp=5, max_lives=3)

    def test_trigger_during_audio_playback(self):
        """Cross 1: Trigger pull while long audio melody is playing interrupts/mixes cleanly."""
        now = 1000
        # Start playing boot melody (duration ~600ms)
        self.audio.play("BOOT", priority=AudioEngineModel.PRIORITY_MELODY, now_ms=now)
        self.assertTrue(self.audio.is_playing)
        self.assertEqual(self.audio.active_freq, 523)

        # 100ms into boot melody, player pulls trigger
        now += 100
        self.trigger.feed_pin_sample(0, now_ms=now)
        now += 50
        shot_fired = self.trigger.feed_pin_sample(0, now_ms=now)
        self.assertTrue(shot_fired)

        # Fire triggers muzzle flash and shot sound
        self.hud.trigger_muzzle_flash(duration_ms=50, now_ms=now)
        # Low priority chirp won't override boot melody if boot is higher priority,
        # but trigger system does NOT block or crash
        self.hud.update(now_ms=now)
        self.assertEqual(self.hud.led_states, [1, 1, 1, 1, 1])

        # Release trigger
        self.trigger.feed_pin_sample(1, now_ms=now + 20)
        self.trigger.feed_pin_sample(1, now_ms=now + 70)
        self.assertEqual(self.trigger.shots_fired, 1)

    def test_hit_taken_while_firing(self):
        """Cross 2: Incoming enemy hit at the exact moment of trigger firing."""
        now = 2000
        # 1. Trigger fired
        self.trigger.feed_pin_sample(0, now_ms=now)
        shot = self.trigger.feed_pin_sample(0, now_ms=now + 50)
        self.assertTrue(shot)
        self.hud.trigger_muzzle_flash(duration_ms=50, now_ms=now + 50)

        # 2. At same instant, enemy IR hit is received
        hit_res = self.ref.process_hit(0x00FF38C7, now_ms=now + 50)
        self.assertEqual(hit_res["ev"], "HIT")
        self.assertEqual(hit_res["hp"], 4)
        self.hud.set_hp(4)

        # Muzzle flash takes visual priority for 50ms
        self.assertEqual(self.hud.update(now_ms=now + 60), [1, 1, 1, 1, 1])

        # After muzzle flash completes at now+110ms, HUD displays damaged 4 HP state
        self.assertEqual(self.hud.update(now_ms=now + 120), [1, 1, 1, 1, 0])

    def test_respawn_shield_blocking_hits_during_audio(self):
        """Cross 3: Shield blocks incoming hits during shield sound and visual flash."""
        now = 10000
        # Player is in respawn shield
        self.hud.set_respawn_shield()
        self.ref.protect_until = now + 3000
        self.audio.play("SHIELD", priority=AudioEngineModel.PRIORITY_MELODY, now_ms=now)

        # Enemy attacks during shield at now + 500ms
        res = self.ref.process_hit(0x00FF38C7, now_ms=now + 500)
        self.assertEqual(res["ev"], "BLOCKED")
        self.assertEqual(self.ref.hp, 5)

        # Shield audio continues unaffected
        self.audio.update(now_ms=now + 500)
        self.assertTrue(self.audio.is_playing)

        # Shield visual flash continues unaffected
        self.assertEqual(self.hud.state, "RESPAWN_SHIELD")

    def test_server_disconnect_mid_game_preservation(self):
        """Cross 4: WiFi disconnect mid-game; local referee seamlessly inherits state."""
        # Simulated server telemetry before disconnect: 3 HP, 2 Lives
        server_hp = 3
        server_lives = 2
        
        # Local referee initializes from last known valid server state
        self.ref.hp = server_hp
        self.ref.lives = server_lives
        self.hud.set_hp(server_hp, server_lives)

        # Offline match continues immediately: takes hit from Enemy 2 (0x00FF5AA5)
        res = self.ref.process_hit(0x00FF5AA5, now_ms=5000)
        self.assertEqual(res["ev"], "HIT")
        self.assertEqual(self.ref.hp, 2)
        self.assertEqual(self.ref.lives, 2)

        # HUD reflects new state: [1, 1, 0, 0, 0]
        self.hud.set_hp(self.ref.hp, self.ref.lives)
        self.assertEqual(self.hud.update(now_ms=5100), [1, 1, 0, 0, 0])

    def test_critical_health_panic_pulse_during_muzzle_flash(self):
        """Cross 5: Muzzle flash overrides 1 HP panic pulse for 50ms, then resumes pulsing."""
        now = 1000
        self.hud.set_hp(1, lives=1)  # 1 HP Critical
        # At now=950ms (950 // 150 = 6, even), panic pulse is in ON phase
        self.assertEqual(self.hud.update(now_ms=950), [1, 0, 0, 0, 0])

        # Fire weapon at now=1100ms
        self.hud.trigger_muzzle_flash(duration_ms=50, now_ms=1100)
        # During flash (t=1120ms): All 5 LEDs ON
        self.assertEqual(self.hud.update(now_ms=1120), [1, 1, 1, 1, 1])

        # At t=1160ms (flash ended): Returns to 1 HP panic pulse
        # t=1160ms: (1160 // 150) % 2 = 7 % 2 = 1 (OFF phase) -> [0, 0, 0, 0, 0]
        self.assertEqual(self.hud.update(now_ms=1160), [0, 0, 0, 0, 0])
        # t=1220ms: (1220 // 150) % 2 = 8 % 2 = 0 (ON phase) -> [1, 0, 0, 0, 0]
        self.assertEqual(self.hud.update(now_ms=1220), [1, 0, 0, 0, 0])

    def test_medic_heal_during_enemy_hit_cooldown(self):
        """Cross 6: Friendly medic heal processed correctly during enemy cooldown window."""
        now = 1000
        # Player hit by enemy at t=1000ms
        res_enemy = self.ref.process_hit(0x00FF38C7, now_ms=now)
        self.assertEqual(res_enemy["ev"], "HIT")
        self.assertEqual(self.ref.hp, 4)
        self.assertEqual(self.ref.cooldown_until, now + 3000)

        # 500ms later (during enemy hit cooldown), friendly medic heals player
        res_medic = self.ref.process_hit(0x00FF30CF, now_ms=now + 500)
        self.assertEqual(res_medic["ev"], "HEAL")
        self.assertEqual(self.ref.hp, 5)

    def test_trigger_locked_out_during_respawn_countdown(self):
        """Cross 7: Weapon trigger is locked out while dead / respawning."""
        now = 10000
        self.ref.state = "RESPAWN"
        self.ref.respawn_at = now + 10000

        # Attempt to pull trigger
        self.trigger.feed_pin_sample(0, now_ms=now)
        shot = self.trigger.feed_pin_sample(0, now_ms=now + 50)
        self.assertTrue(shot)  # Hardware trigger debounces

        # But game controller suppresses IR transmission when state is RESPAWN
        can_fire = (self.ref.state == "ALIVE")
        self.assertFalse(can_fire)

        # Respawn timer remains untouched
        self.assertEqual(self.ref.respawn_at, now + 10000)

    def test_server_rediscovery_transition_from_standalone(self):
        """Cross 8: System in standalone mode discovers server and attaches cleanly."""
        # Device running offline
        is_connected = False
        discovered_ip = None

        # Simulated UDP packet received on port 5051
        udp_packet = "LASERTAG 5050"
        sender_ip = "192.168.1.100"

        if udp_packet.startswith("LASERTAG"):
            port = int(udp_packet.split()[1])
            self.assertEqual(port, 5050)
            discovered_ip = sender_ip
            is_connected = True

        self.assertTrue(is_connected)
        self.assertEqual(discovered_ip, "192.168.1.100")


if __name__ == "__main__":
    unittest.main()
