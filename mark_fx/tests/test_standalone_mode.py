"""
Mark FX Laser Tag - Autonomous Standalone Fallback Mode Verification Suite
Covers Requirement R5, R6, and Acceptance Criteria AC-9.
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

from mark_fx.tests.models import StandaloneReferee, NECProtocol


class TestStandaloneModeTier1(unittest.TestCase):
    """Tier 1: Feature Coverage for Standalone Fallback Mode."""

    def setUp(self):
        self.ref = StandaloneReferee(max_hp=5, max_lives=3)

    def test_standalone_initialization(self):
        """Verify standalone referee starts at 5 HP, 3 Lives, ALIVE state."""
        self.assertEqual(self.ref.hp, 5)
        self.assertEqual(self.ref.lives, 3)
        self.assertEqual(self.ref.state, "ALIVE")
        self.assertEqual(self.ref.hits_taken, 0)
        self.assertEqual(self.ref.deaths, 0)

    def test_offline_enemy_hit(self):
        """Verify enemy hit in standalone mode deducts 1 HP and sets 3s cooldown."""
        # Enemy 1 (P5: 0x00FF38C7)
        res = self.ref.process_hit(0x00FF38C7, now_ms=1000)
        self.assertEqual(res["ev"], "HIT")
        self.assertEqual(res["hp"], 4)
        self.assertEqual(self.ref.hp, 4)
        self.assertEqual(self.ref.hits_taken, 1)
        self.assertEqual(self.ref.cooldown_until, 4000)

    def test_offline_medic_heal(self):
        """Verify friendly hit in standalone mode heals damaged player +1 HP."""
        # Damage player first
        self.ref.process_hit(0x00FF38C7, now_ms=1000)
        self.assertEqual(self.ref.hp, 4)

        # Friend 1 (P1: 0x00FF30CF) shoots
        res = self.ref.process_hit(0x00FF30CF, now_ms=5000)
        self.assertEqual(res["ev"], "HEAL")
        self.assertEqual(res["hp"], 5)
        self.assertEqual(self.ref.hp, 5)

    def test_offline_respawn_cycle(self):
        """Verify losing 5 HP triggers 10s RESPAWN state and deducts 1 life."""
        # Inflict 5 hits
        t = 1000
        for i in range(5):
            res = self.ref.process_hit(0x00FF38C7, now_ms=t)
            t += 3500  # Advance past cooldown
        self.assertEqual(res["ev"], "DEATH")
        self.assertEqual(self.ref.lives, 2)
        self.assertEqual(self.ref.state, "RESPAWN")
        self.assertEqual(self.ref.respawn_at, t - 3500 + 10000)

        # Advance 10 seconds to complete respawn
        respawn_complete_time = self.ref.respawn_at + 100
        self.ref.update(now_ms=respawn_complete_time)
        self.assertEqual(self.ref.state, "ALIVE")
        self.assertEqual(self.ref.hp, 5)
        self.assertEqual(self.ref.protect_until, respawn_complete_time + 3000)

    def test_offline_elimination_after_all_lives_lost(self):
        """Verify player enters OUT/ELIMINATED state after losing all 3 lives."""
        self.ref.lives = 1
        self.ref.hp = 1
        res = self.ref.process_hit(0x00FF38C7, now_ms=1000)
        self.assertEqual(res["ev"], "ELIM")
        self.assertEqual(self.ref.lives, 0)
        self.assertEqual(self.ref.hp, 0)
        self.assertEqual(self.ref.state, "OUT")

    def test_offline_fire_when_eliminated_rejected(self):
        """Verify any further hits when eliminated return NOTALIVE."""
        self.ref.state = "OUT"
        self.ref.lives = 0
        self.ref.hp = 0
        res = self.ref.process_hit(0x00FF38C7, now_ms=1000)
        self.assertEqual(res["ev"], "NOTALIVE")


class TestStandaloneModeTier2(unittest.TestCase):
    """Tier 2: Boundary & Corner Cases for Standalone Mode."""

    def setUp(self):
        self.ref = StandaloneReferee(max_hp=5, max_lives=3)

    def test_corrupted_ir_noise_rejection(self):
        """Verify corrupted or optical noise pulses are ignored in standalone mode."""
        res = self.ref.process_hit(0x12345678, now_ms=1000)
        self.assertEqual(res["ev"], "IGNORED")
        self.assertEqual(self.ref.hp, 5)

    def test_offline_3s_hit_cooldown_boundary(self):
        """Verify hit at 2999ms is rejected, but hit at 3001ms is registered."""
        # Hit 1 at t=1000ms
        self.ref.process_hit(0x00FF38C7, now_ms=1000)
        self.assertEqual(self.ref.hp, 4)
        self.assertEqual(self.ref.cooldown_until, 4000)

        # Hit 2 at t=3999ms (2999ms elapsed < 3000ms)
        res_early = self.ref.process_hit(0x00FF38C7, now_ms=3999)
        self.assertEqual(res_early["ev"], "COOLDOWN")
        self.assertEqual(self.ref.hp, 4)

        # Hit 3 at t=4001ms (3001ms elapsed > 3000ms)
        res_ok = self.ref.process_hit(0x00FF38C7, now_ms=4001)
        self.assertEqual(res_ok["ev"], "HIT")
        self.assertEqual(self.ref.hp, 3)

    def test_offline_3s_spawn_shield_boundary(self):
        """Verify hits during 3s spawn shield are blocked without reducing HP."""
        self.ref.protect_until = 5000
        # Shot during shield at t=3000ms
        res = self.ref.process_hit(0x00FF38C7, now_ms=3000)
        self.assertEqual(res["ev"], "BLOCKED")
        self.assertEqual(self.ref.hp, 5)

        # Shot after shield at t=5001ms
        res_after = self.ref.process_hit(0x00FF38C7, now_ms=5001)
        self.assertEqual(res_after["ev"], "HIT")
        self.assertEqual(self.ref.hp, 4)

    def test_mid_game_network_drop_state_preservation(self):
        """Verify local referee cleanly inherits live match state upon network drop."""
        # Simulated state when WiFi drops: HP=3, Lives=2
        self.ref.hp = 3
        self.ref.lives = 2
        self.ref.state = "ALIVE"

        # Continues playing offline seamlessly
        res = self.ref.process_hit(0x00FF38C7, now_ms=10000)
        self.assertEqual(res["ev"], "HIT")
        self.assertEqual(self.ref.hp, 2)
        self.assertEqual(self.ref.lives, 2)

    def test_medic_heal_at_max_health_rejected(self):
        """Verify medic heal when already at 5 HP returns FULL."""
        res = self.ref.process_hit(0x00FF30CF, now_ms=1000)
        self.assertEqual(res["ev"], "FULL")
        self.assertEqual(self.ref.hp, 5)


if __name__ == "__main__":
    unittest.main()
