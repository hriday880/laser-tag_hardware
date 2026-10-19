"""
Mark FX Laser Tag - Tier 4 Real-World Application Scenarios
Full match simulation test suite.
Covers Requirements R1–R6 and Acceptance Criteria AC-1..AC-11.
"""

import os
import sys
import time
import unittest

# Ensure repo root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import server.server as srv
from mark_fx.tests.models import StandaloneReferee, HUDStateEngine


class TestRealWorldScenariosTier4(unittest.TestCase):
    """Tier 4: Full Match and Real-World Application Simulation Scenarios."""

    def test_scenario_1_4v4_match_progression(self):
        """Scenario 1: Complete 4v4 match simulation with First Blood, Kills, and Scoring."""
        game = srv.Game()
        game.reset()

        # 1. Start match (LOBBY -> COUNTDOWN -> LIVE)
        game.start()
        game.countdown_end = time.time() - 1
        game.tick()
        self.assertEqual(game.phase, "LIVE")

        # 2. P5 (Enemy 1: 0xFF38C7) inflicts First Blood on P1
        ev1 = game.process_hit("0xFF38C7")
        self.assertEqual(ev1["ev"], "HIT")
        self.assertEqual(game.hp, 4)
        # Enemy 1 gets 10 pts (hit) + 25 pts (first blood) = 35 pts
        self.assertEqual(game.stats["Enemy 1"]["score"], 35)

        # 3. P6 (Enemy 2: 0xFF5AA5) inflicts 4 consecutive hits over time
        for _ in range(4):
            game.cooldown_until = 0
            ev = game.process_hit("0xFF5AA5")
        # 5th total hit kills P1 -> P1 enters RESPAWN, lives 2
        self.assertEqual(ev["ev"], "DEATH")
        self.assertEqual(game.lives, 2)
        self.assertEqual(game.pstate, "RESPAWN")

        # 4. Respawn completes after respawn_s (10s)
        game.respawn_at = time.time() - 1
        game.tick()
        self.assertEqual(game.pstate, "ALIVE")
        self.assertEqual(game.hp, 5)

        # 5. Spawn shield (3s) blocks incoming shots
        ev_blocked = game.process_hit("0xFF42BD")  # Enemy 3
        self.assertEqual(ev_blocked["ev"], "BLOCKED")
        self.assertEqual(game.hp, 5)

        # 6. Complete remaining lives to trigger gameover
        for life in range(2):
            game.protect_until = 0
            for h in range(5):
                game.cooldown_until = 0
                ev_kill = game.process_hit("0xFF38C7")
            if game.pstate == "RESPAWN":
                game.respawn_at = time.time() - 1
                game.tick()

        # 7. Player is eliminated
        self.assertEqual(game.pstate, "OUT")
        self.assertEqual(game.phase, "GAMEOVER")
        self.assertEqual(game.result, "ELIMINATED")
        self.assertEqual(game.mvp, "Enemy 1")

    def test_scenario_2_medic_friendly_fire_and_traitor_conversion(self):
        """Scenario 2: Medic friendly fire strikes escalate into traitor defection and enemy damage."""
        game = srv.Game()
        game.reset()
        game.start()
        game.countdown_end = time.time() - 1
        game.tick()

        # Damage player to 2 HP
        game.hp = 2

        # P2 (Friend 2: 0xFF18E7) heals P1
        heal_ev = game.process_hit("0xFF18E7")
        self.assertEqual(heal_ev["ev"], "HEAL")
        self.assertEqual(game.hp, 3)
        self.assertEqual(game.stats["Friend 2"]["heals"], 1)

        # P2 fires 3 times rapidly while medic cooldown is active
        # Strike 1
        s1 = game.process_hit("0xFF18E7")
        self.assertEqual(s1["ev"], "FF")
        self.assertEqual(game.stats["Friend 2"]["strikes"], 1)

        # Strike 2
        s2 = game.process_hit("0xFF18E7")
        self.assertEqual(s2["ev"], "FF")
        self.assertEqual(game.stats["Friend 2"]["strikes"], 2)

        # Strike 3: Defection to TRAITOR!
        s3 = game.process_hit("0xFF18E7")
        self.assertEqual(s3["ev"], "TRAITOR")
        self.assertTrue(game.stats["Friend 2"]["traitor"])

        # P2 fires again: Now deals damage as an ENEMY!
        game.cooldown_until = 0
        dmg_ev = game.process_hit("0xFF18E7")
        self.assertEqual(dmg_ev["ev"], "HIT")
        self.assertEqual(game.hp, 2)  # HP reduced from 3 to 2

    def test_scenario_3_sudden_death_elimination(self):
        """Scenario 3: Sudden Death Match (1 Life, 1 HP) — Instant Elimination and Finisher Bonus."""
        game = srv.Game()
        game.reset()
        # Apply sudden death settings
        game.apply_settings({"max_hp": 1, "max_lives": 1})
        self.assertEqual(game.hp, 1)
        self.assertEqual(game.lives, 1)

        game.start()
        game.countdown_end = time.time() - 1
        game.tick()

        # Single enemy hit from Enemy 3 (0xFF42BD)
        ev = game.process_hit("0xFF42BD")
        self.assertEqual(ev["ev"], "ELIM")
        self.assertEqual(game.lives, 0)
        self.assertEqual(game.hp, 0)
        self.assertEqual(game.pstate, "OUT")
        self.assertEqual(game.phase, "GAMEOVER")
        
        # Enemy 3 earns 10 (hit) + 25 (first blood) + 50 (kill) + 100 (finisher) = 185 pts
        self.assertEqual(game.stats["Enemy 3"]["score"], 185)
        self.assertEqual(game.mvp, "Enemy 3")

    def test_scenario_4_offline_backyard_skirmish(self):
        """Scenario 4: Complete offline backyard skirmish with zero WiFi connection."""
        ref = StandaloneReferee(max_hp=5, max_lives=3)
        hud = HUDStateEngine()

        # Boot offline
        hud.set_hp(ref.hp, ref.lives)
        self.assertEqual(hud.update(now_ms=0), [1, 1, 1, 1, 1])

        # Match proceeds: takes 5 hits from Enemy 1 (0x00FF38C7)
        now = 1000
        for i in range(4):
            res = ref.process_hit(0x00FF38C7, now_ms=now)
            self.assertEqual(res["ev"], "HIT")
            hud.set_hp(ref.hp, ref.lives)
            now += 3500

        # 5th hit causes death
        death_res = ref.process_hit(0x00FF38C7, now_ms=now)
        self.assertEqual(death_res["ev"], "DEATH")
        self.assertEqual(ref.lives, 2)
        self.assertEqual(ref.state, "RESPAWN")

        # 10s Respawn countdown
        now += 10100
        ref.update(now_ms=now)
        self.assertEqual(ref.state, "ALIVE")
        self.assertEqual(ref.hp, 5)

        # Plays through remaining 2 lives
        for life in range(2):
            for h in range(5):
                ref.cooldown_until = 0
                ref.protect_until = 0
                res = ref.process_hit(0x00FF38C7, now_ms=now)
                now += 100
            if ref.state == "RESPAWN":
                now += 10100
                ref.update(now_ms=now)

        self.assertEqual(ref.state, "OUT")
        hud.set_hp(ref.hp, ref.lives)
        self.assertEqual(hud.update(now_ms=now), [0, 0, 0, 0, 0])

    def test_scenario_5_network_glitch_and_auto_recovery(self):
        """Scenario 5: 30-second WiFi outage mid-game with seamless local survival and resync."""
        game = srv.Game()
        game.reset()
        game.start()
        game.countdown_end = time.time() - 1
        game.tick()

        # 1. Player at 4 HP online
        game.process_hit("0xFF38C7")
        self.assertEqual(game.hp, 4)

        # 2. Network disconnect occurs: device uses StandaloneReferee
        local_ref = StandaloneReferee()
        local_ref.hp = game.hp
        local_ref.lives = game.lives

        # 3. 20s offline period: player receives 1 enemy hit offline
        res = local_ref.process_hit(0x00FF5AA5, now_ms=5000)
        self.assertEqual(res["ev"], "HIT")
        self.assertEqual(local_ref.hp, 3)

        # 4. WiFi reconnects: device sends telemetry update to server
        # Synchronize server to client state
        game.hp = local_ref.hp
        dev_state = game.device_state()
        self.assertEqual(dev_state["hp"], 3)
        self.assertEqual(dev_state["ph"], "LIVE")


if __name__ == "__main__":
    unittest.main()
