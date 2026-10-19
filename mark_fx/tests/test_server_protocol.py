"""
Mark FX Laser Tag - Server Interaction & Game Referee Protocol Verification Suite
Covers Requirement R5 and Acceptance Criteria AC-8.
Tier 1: Feature Coverage (>=5 test cases)
Tier 2: Boundary & Corner Cases (>=5 test cases)
"""

import os
import sys
import json
import time
import unittest

# Ensure repo root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import server.server as srv
from mark_fx.tests.models import NECProtocol


class TestServerProtocolTier1(unittest.TestCase):
    """Tier 1: Feature Coverage for Server Interaction & Referee Rules."""

    def setUp(self):
        self.game = srv.Game()
        self.game.reset()
        # Fast forward into LIVE phase for game tests
        self.game.start()
        # Simulate countdown end
        self.game.countdown_end = time.time() - 1
        self.game.tick()
        self.assertEqual(self.game.phase, "LIVE")

    def test_udp_discovery_packet_format(self):
        """Verify UDP discovery packet string format 'LASERTAG <PORT>'."""
        packet_msg = f"LASERTAG {srv.HTTP_PORT}"
        parts = packet_msg.split()
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0], "LASERTAG")
        self.assertEqual(int(parts[1]), 5050)

    def test_device_state_contract_keys(self):
        """Verify device_state() dictionary contains all required flat keys."""
        state = self.game.device_state()
        required_keys = ["ph", "st", "hp", "mhp", "lv", "mlv", "tm", "rs", "pr", "cd", "last", "ht", "dt"]
        for k in required_keys:
            self.assertIn(k, state, f"Missing key '{k}' in device_state() contract")
        self.assertEqual(state["hp"], 5)
        self.assertEqual(state["mhp"], 5)
        self.assertEqual(state["lv"], 3)
        self.assertEqual(state["mlv"], 3)

    def test_enemy_hit_reduces_hp(self):
        """Verify valid enemy shot reduces player HP and returns ev='HIT'."""
        # Enemy 1 (P5) code is 0xFF38C7
        ev = self.game.process_hit("0xFF38C7")
        self.assertEqual(ev["ev"], "HIT")
        self.assertEqual(ev["attacker"], "Enemy 1")
        self.assertEqual(self.game.hp, 4)
        self.assertEqual(self.game.hits_taken, 1)

    def test_friendly_medic_heal_increases_hp(self):
        """Verify friendly medic shot increases player HP by +1 when damaged."""
        # Inflict 1 damage first
        self.game.process_hit("0xFF38C7")
        self.assertEqual(self.game.hp, 4)

        # Friend 2 (P2) code is 0xFF18E7
        ev = self.game.process_hit("0xFF18E7")
        self.assertEqual(ev["ev"], "HEAL")
        self.assertEqual(ev["attacker"], "Friend 2")
        self.assertEqual(self.game.hp, 5)
        self.assertEqual(self.game.heals, 1)

    def test_spawn_shield_blocks_hits(self):
        """Verify shots received while protect_until is in future return ev='BLOCKED'."""
        self.game.protect_until = time.time() + 3.0  # 3s spawn shield
        ev = self.game.process_hit("0xFF38C7")
        self.assertEqual(ev["ev"], "BLOCKED")
        self.assertEqual(self.game.hp, 5)  # No damage taken

    def test_hit_cooldown_prevents_damage(self):
        """Verify rapid shots received within cooldown_s return ev='COOLDOWN'."""
        # Hit 1
        ev1 = self.game.process_hit("0xFF38C7")
        self.assertEqual(ev1["ev"], "HIT")
        self.assertEqual(self.game.hp, 4)

        # Immediate Hit 2 from Enemy 2 (0xFF5AA5) within 3s cooldown
        ev2 = self.game.process_hit("0xFF5AA5")
        self.assertEqual(ev2["ev"], "COOLDOWN")
        self.assertEqual(self.game.hp, 4)  # HP remains 4


class TestServerProtocolTier2(unittest.TestCase):
    """Tier 2: Boundary & Corner Cases for Server Protocol."""

    def setUp(self):
        self.game = srv.Game()
        self.game.reset()

    def test_unknown_ir_code_ignored(self):
        """Verify corrupted or unrecognized IR code returns ev='IGNORED'."""
        self.game.start()
        self.game.countdown_end = time.time() - 1
        self.game.tick()
        
        ev = self.game.process_hit("0xDEADBEEF")
        self.assertEqual(ev["ev"], "IGNORED")
        self.assertEqual(self.game.hp, 5)

    def test_hit_in_lobby_phase_rejected(self):
        """Verify hit while phase is LOBBY returns ev='NOTLIVE'."""
        self.assertEqual(self.game.phase, "LOBBY")
        ev = self.game.process_hit("0xFF38C7")
        self.assertEqual(ev["ev"], "NOTLIVE")
        self.assertEqual(self.game.hp, 5)

    def test_hit_in_paused_phase_rejected(self):
        """Verify hit while phase is PAUSED returns ev='NOTLIVE'."""
        self.game.start()
        self.game.countdown_end = time.time() - 1
        self.game.tick()
        self.game.pause()
        self.assertEqual(self.game.phase, "PAUSED")

        ev = self.game.process_hit("0xFF38C7")
        self.assertEqual(ev["ev"], "NOTLIVE")
        self.assertEqual(self.game.hp, 5)

    def test_medic_heal_at_full_health_wasted(self):
        """Verify friendly shot when HP is already 5/5 returns ev='FULL'."""
        self.game.start()
        self.game.countdown_end = time.time() - 1
        self.game.tick()

        self.assertEqual(self.game.hp, 5)
        ev = self.game.process_hit("0xFF30CF")  # Friend 1
        self.assertEqual(ev["ev"], "FULL")
        self.assertEqual(self.game.hp, 5)

    def test_friendly_fire_strikes_and_traitor_conversion(self):
        """Verify friendly fire within medic cooldown accumulates strikes and triggers TRAITOR."""
        self.game.start()
        self.game.countdown_end = time.time() - 1
        self.game.tick()

        # Damage player to 3 HP so heal is possible
        self.game.hp = 3

        # Medic heal 1 by Friend 1 (0xFF30CF)
        ev1 = self.game.process_hit("0xFF30CF")
        self.assertEqual(ev1["ev"], "HEAL")
        self.assertEqual(self.game.hp, 4)

        # Friend 1 fires again immediately: Strike 1
        ev2 = self.game.process_hit("0xFF30CF")
        self.assertEqual(ev2["ev"], "FF")

        # Friend 1 fires again: Strike 2
        ev3 = self.game.process_hit("0xFF30CF")
        self.assertEqual(ev3["ev"], "FF")

        # Friend 1 fires again: Strike 3 -> TRAITOR!
        ev4 = self.game.process_hit("0xFF30CF")
        self.assertEqual(ev4["ev"], "TRAITOR")
        self.assertTrue(self.game.stats["Friend 1"]["traitor"])

    def test_traitor_inflicts_damage_as_enemy(self):
        """Verify that after becoming a traitor, former friend deals real damage."""
        self.game.start()
        self.game.countdown_end = time.time() - 1
        self.game.tick()
        self.game.hp = 4

        # Manually mark Friend 1 as traitor
        self.game.stats["Friend 1"]["traitor"] = True

        # Friend 1 shoots P1
        ev = self.game.process_hit("0xFF30CF")
        self.assertEqual(ev["ev"], "HIT")
        self.assertEqual(self.game.hp, 3)
        self.assertIn("(T)", ev["attacker"])

    def test_elimination_after_losing_all_lives(self):
        """Verify player transitions to OUT/ELIMINATED after losing 5 HP across 3 lives."""
        self.game.start()
        self.game.countdown_end = time.time() - 1
        self.game.tick()

        # Life 1: 5 hits
        for _ in range(5):
            self.game.cooldown_until = 0  # Bypass cooldown for test speed
            ev = self.game.process_hit("0xFF38C7")
        self.assertEqual(ev["ev"], "DEATH")
        self.assertEqual(self.game.lives, 2)
        self.assertEqual(self.game.pstate, "RESPAWN")

        # Fast-forward respawn
        self.game.respawn_at = time.time() - 1
        self.game.tick()
        self.assertEqual(self.game.pstate, "ALIVE")
        self.assertEqual(self.game.hp, 5)

        # Life 2: 5 hits
        for _ in range(5):
            self.game.protect_until = 0
            self.game.cooldown_until = 0
            ev = self.game.process_hit("0xFF38C7")
        self.assertEqual(ev["ev"], "DEATH")
        self.assertEqual(self.game.lives, 1)

        # Fast-forward respawn
        self.game.respawn_at = time.time() - 1
        self.game.tick()

        # Life 3 (Final life): 5 hits
        for _ in range(5):
            self.game.protect_until = 0
            self.game.cooldown_until = 0
            ev = self.game.process_hit("0xFF38C7")
        self.assertEqual(ev["ev"], "ELIM")
        self.assertEqual(self.game.lives, 0)
        self.assertEqual(self.game.hp, 0)
        self.assertEqual(self.game.pstate, "OUT")
        self.assertEqual(self.game.phase, "GAMEOVER")


if __name__ == "__main__":
    unittest.main()
