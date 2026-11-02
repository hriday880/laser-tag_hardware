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
        self.assertEqual(ev["attacker"], "P5")
        self.assertEqual(self.game.vests["P1"].hp, 4)
        self.assertEqual(self.game.vests["P1"].hits_taken, 1)

    def test_friendly_medic_heal_increases_hp(self):
        """Verify friendly medic shot increases player HP by +1 when damaged."""
        # Inflict 1 damage first
        self.game.process_hit("0xFF38C7")
        self.assertEqual(self.game.vests["P1"].hp, 4)

        # Friend 2 (P2) code is 0xFF18E7
        ev = self.game.process_hit("0xFF18E7")
        self.assertEqual(ev["ev"], "HEAL")
        self.assertEqual(ev["attacker"], "P2")
        self.assertEqual(self.game.vests["P1"].hp, 5)
        self.assertEqual(self.game.vests["P1"].heals, 1)

    def test_spawn_shield_blocks_hits(self):
        """Verify shots received while protect_until is in future return ev='BLOCKED'."""
        self.game.vests["P1"].protect_until = time.time() + 3.0  # 3s spawn shield
        ev = self.game.process_hit("0xFF38C7")
        self.assertEqual(ev["ev"], "BLOCKED")
        self.assertEqual(self.game.vests["P1"].hp, 5)  # No damage taken

    def test_hit_cooldown_prevents_damage(self):
        """Verify rapid shots received within cooldown_s return ev='COOLDOWN'."""
        # Hit 1
        ev1 = self.game.process_hit("0xFF38C7")
        self.assertEqual(ev1["ev"], "HIT")
        self.assertEqual(self.game.vests["P1"].hp, 4)

        # Immediate Hit 2 from Enemy 2 (0xFF5AA5) within 3s cooldown
        ev2 = self.game.process_hit("0xFF5AA5")
        self.assertEqual(ev2["ev"], "COOLDOWN")
        self.assertEqual(self.game.vests["P1"].hp, 4)  # HP remains 4


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
        self.assertEqual(self.game.vests["P1"].hp, 5)

    def test_hit_in_lobby_phase_rejected(self):
        """Verify hit while phase is LOBBY returns ev='NOTLIVE'."""
        self.assertEqual(self.game.phase, "LOBBY")
        ev = self.game.process_hit("0xFF38C7")
        self.assertEqual(ev["ev"], "NOTLIVE")
        self.assertEqual(self.game.vests["P1"].hp, 5)

    def test_hit_in_paused_phase_rejected(self):
        """Verify hit while phase is PAUSED returns ev='NOTLIVE'."""
        self.game.start()
        self.game.countdown_end = time.time() - 1
        self.game.tick()
        self.game.pause()
        self.assertEqual(self.game.phase, "PAUSED")

        ev = self.game.process_hit("0xFF38C7")
        self.assertEqual(ev["ev"], "NOTLIVE")
        self.assertEqual(self.game.vests["P1"].hp, 5)

    def test_medic_heal_at_full_health_wasted(self):
        """Verify friendly shot when HP is already 5/5 returns ev='FULL'."""
        self.game.start()
        self.game.countdown_end = time.time() - 1
        self.game.tick()

        self.assertEqual(self.game.vests["P1"].hp, 5)
        ev = self.game.process_hit("0xFF7A85")  # Friend 1
        self.assertEqual(ev["ev"], "FULL")
        self.assertEqual(self.game.vests["P1"].hp, 5)

    def test_friendly_fire_strikes_and_traitor_conversion(self):
        """Verify friendly fire within medic cooldown accumulates strikes and triggers TRAITOR."""
        self.game.start()
        self.game.countdown_end = time.time() - 1
        self.game.tick()

        # Damage player to 3 HP so heal is possible
        self.game.vests["P1"].hp = 3

        # Medic heal 1 by Friend 1 (0xFF30CF)
        ev1 = self.game.process_hit("0xFF7A85")
        self.assertEqual(ev1["ev"], "HEAL")
        self.assertEqual(self.game.vests["P1"].hp, 4)

        # Friend 1 fires again immediately: Strike 1
        ev2 = self.game.process_hit("0xFF7A85")
        self.assertEqual(ev2["ev"], "FF")

        # Friend 1 fires again: Strike 2
        ev3 = self.game.process_hit("0xFF7A85")
        self.assertEqual(ev3["ev"], "FF")

        # Friend 1 fires again: Strike 3 -> TRAITOR!
        ev4 = self.game.process_hit("0xFF7A85")
        self.assertEqual(ev4["ev"], "TRAITOR")
        self.assertTrue(self.game.stats["P3"]["traitor"])

    def test_traitor_inflicts_damage_as_enemy(self):
        """Verify that after becoming a traitor, former friend deals real damage."""
        self.game.start()
        self.game.countdown_end = time.time() - 1
        self.game.tick()
        self.game.vests["P1"].hp = 4

        # Manually mark Friend 1 as traitor
        self.game.stats["P3"]["traitor"] = True

        # Friend 1 shoots P1
        ev = self.game.process_hit("0xFF7A85")
        self.assertEqual(ev["ev"], "HIT")
        self.assertEqual(self.game.vests["P1"].hp, 3)
        self.assertIn("(T)", ev["attacker"])

    def test_elimination_after_losing_all_lives(self):
        """Verify player transitions to OUT/ELIMINATED after losing 5 HP across 3 lives."""
        self.game.start()
        self.game.countdown_end = time.time() - 1
        self.game.tick()

        # Life 1: 5 hits
        for _ in range(5):
            self.game.vests["P1"].cooldown_until = 0  # Bypass cooldown for test speed
            ev = self.game.process_hit("0xFF38C7")
        self.assertEqual(ev["ev"], "DEATH")
        self.assertEqual(self.game.vests["P1"].lives, 2)
        self.assertEqual(self.game.vests["P1"].pstate, "RESPAWN")

        # Fast-forward respawn
        self.game.vests["P1"].respawn_at = time.time() - 1
        self.game.tick()
        self.assertEqual(self.game.vests["P1"].pstate, "ALIVE")
        self.assertEqual(self.game.vests["P1"].hp, 5)

        # Life 2: 5 hits
        for _ in range(5):
            self.game.vests["P1"].protect_until = 0
            self.game.vests["P1"].cooldown_until = 0
            ev = self.game.process_hit("0xFF38C7")
        self.assertEqual(ev["ev"], "DEATH")
        self.assertEqual(self.game.vests["P1"].lives, 1)

        # Fast-forward respawn
        self.game.vests["P1"].respawn_at = time.time() - 1
        self.game.tick()

        # Life 3 (Final life): 5 hits
        for _ in range(5):
            self.game.vests["P1"].protect_until = 0
            self.game.vests["P1"].cooldown_until = 0
            ev = self.game.process_hit("0xFF38C7")
        self.assertEqual(ev["ev"], "ELIM")
        self.assertEqual(self.game.vests["P1"].lives, 0)
        self.assertEqual(self.game.vests["P1"].hp, 0)
        self.assertEqual(self.game.vests["P1"].pstate, "OUT")
        self.assertEqual(self.game.phase, "GAMEOVER")


class TestMultiVestAndFailsafe(unittest.TestCase):
    """Per-vest state, team logic and failsafe reporting."""

    def setUp(self):
        self._save, srv.save_history = srv.save_history, lambda h: None
        self._log, srv.failsafe_log = srv.failsafe_log, self.events_append
        self.events = []
        self.game = srv.Game()
        for v in ("P1", "P2", "P5"):
            self.game.touch_vest(v, "10.0.0.1", {})
        self.game.start()
        self.game.countdown_end = time.time() - 1
        self.game.tick()

    def tearDown(self):
        srv.save_history, srv.failsafe_log = self._save, self._log

    def events_append(self, e):
        self.events.append(e)

    def test_hp_is_per_vest(self):
        self.game.process_hit("0xFF38C7", "P1")
        self.assertEqual(self.game.vests["P1"].hp, 4)
        self.assertEqual(self.game.vests["P2"].hp, 5)

    def test_team_is_relative_to_victim(self):
        self.assertEqual(self.game.process_hit("0xFF30CF", "P5")["ev"], "HIT")
        self.game.vests["P5"].hp = 3
        self.assertEqual(self.game.process_hit("0xFF5AA5", "P5")["ev"], "HEAL")

    def test_own_code_ignored(self):
        self.assertEqual(self.game.process_hit("0xFF30CF", "P1")["ev"], "IGNORED")

    def test_match_continues_until_whole_team_out(self):
        self.game.settings["max_lives"] = 1
        self.game.vests["P1"].hp, self.game.vests["P1"].lives = 1, 1
        self.game.process_hit("0xFF38C7", "P1")
        self.assertEqual(self.game.phase, "LIVE")
        self.game.vests["P2"].hp, self.game.vests["P2"].lives = 1, 1
        self.game.process_hit("0xFF38C7", "P2")
        self.assertEqual(self.game.phase, "GAMEOVER")
        self.assertEqual(self.game.result, "RED WINS")
        self.assertEqual(self.game.device_state("P5")["res"], "WIN")
        self.assertEqual(self.game.device_state("P1")["res"], "LOSE")

    def test_reports_logged_once(self):
        report = {"s": "STUCK_LOW", "b": "OK", "a": 1, "ad": 1, "dp": "P5+P6", "am": 2, "ah": 0}
        self.game.touch_vest("P1", "10.0.0.1", report)
        self.game.touch_vest("P1", "10.0.0.1", report)
        kinds = [e["event"] for e in self.events]
        self.assertEqual(kinds.count("DOUBLE_HIT_IGNORED"), 1)
        self.assertEqual(kinds.count("ASSIST_ACTIVE"), 1)
        self.assertEqual(kinds.count("SENSOR_STATE"), 1)
        self.assertEqual(self.game.vests["P1"].assist_doubles, 1)

    def test_assist_hit_flows_through_normal_rules(self):
        self.assertEqual(self.game.process_hit("0xFF38C7", "P1", True)["ev"], "HIT")
        self.assertEqual(self.game.process_hit("0xFF38C7", "P1", True)["ev"], "COOLDOWN")
        self.assertEqual([e["event"] for e in self.events].count("ASSIST_HIT"), 1)

    def test_referee_override_reaches_only_that_vest(self):
        self.game.set_manual_assist("P1", True)
        self.assertEqual(self.game.device_state("P1")["ast"], 1)
        self.assertEqual(self.game.device_state("P2")["ast"], 0)

    def test_public_view_hides_failsafe(self):
        self.game.touch_vest("P1", "10.0.0.1", {"s": "OPEN", "b": "OK", "a": 1})
        self.game.process_hit("0xFF38C7", "P1", True)
        public = json.dumps(self.game.full_state())
        for secret in ("FAILSAFE", "ailsafe", "assist", "OPEN", "sensors"):
            self.assertNotIn(secret, public)
        referee = self.game.full_state(True)
        self.assertEqual(referee["vests"][0]["sensors"], "OPEN")
        self.assertIn("[FAILSAFE]", json.dumps(referee["feed"]))

    def test_assist_heal_from_teammate(self):
        self.game.vests["P1"].hp = 3
        self.assertEqual(self.game.process_hit("0xFF18E7", "P1", True)["ev"], "HEAL")
        self.assertEqual([e["event"] for e in self.events].count("ASSIST_HEAL"), 1)

    def test_buzzer_assignment_per_gun(self):
        self.assertNotIn("bz", self.game.device_state("P1"))
        saved = srv.save_buzzers
        written = []
        srv.save_buzzers = written.append
        try:
            self.assertTrue(self.game.set_buzzer("P1", "ACTIVE"))
            self.assertFalse(self.game.set_buzzer("P1", "LOUD"))
        finally:
            srv.save_buzzers = saved
        self.assertEqual(self.game.device_state("P1")["bz"], 1)
        self.assertNotIn("bz", self.game.device_state("P2"))
        self.assertEqual(written, [{"P1": "ACTIVE"}])
        self.assertNotIn("buzzer", json.dumps(self.game.full_state()))
        self.game.touch_vest("P1", "10.0.0.1", {"bz": 1})
        self.assertEqual(self.game.vests["P1"].buzzer_device, "ACTIVE")

    def test_not_target_rolls_logged(self):
        self.game.touch_vest("P1", "10.0.0.1", {"an": 2})
        self.game.touch_vest("P1", "10.0.0.1", {"an": 2})
        self.assertEqual(self.game.vests["P1"].assist_not_target, 2)
        self.assertEqual([e["event"] for e in self.events].count("ASSIST_NOT_TARGET"), 1)
        self.assertNotIn("not_target", json.dumps(self.game.full_state()))

    def test_referee_key_required(self):
        saved, srv.REFEREE_KEY = srv.REFEREE_KEY, "secret"
        try:
            self.assertTrue(srv.is_referee_key("secret"))
            for bad in ("", "1", None, "secre"):
                self.assertFalse(srv.is_referee_key(bad))
        finally:
            srv.REFEREE_KEY = saved
        self.assertFalse(srv.is_referee_key("secret"))

    def test_radio_failure_reported_to_referee_only(self):
        self.game.touch_vest("P1", "10.0.0.1", {"en": 1})
        self.game.touch_vest("P1", "10.0.0.1", {"en": 0})
        self.assertEqual(self.game.full_state(True)["vests"][0]["radio"], "FAILED")
        self.assertIn("RADIO_STATE", [e["event"] for e in self.events])
        self.assertNotIn("radio", json.dumps(self.game.full_state()))

    def _sync(self, **kw):
        data = {"mid": self.game.match_id, "boot": 7, "hp": 4, "lv": 3, "st": "ALIVE", "rs": 0, "pr": 0, "cd": 1000,
                "ev": [[1, "D", 4, 0]]}
        data.update(kw)
        return self.game.sync_offline("P1", data)

    def test_offline_sync_applies_events_and_final_state(self):
        self._sync()
        self.assertEqual(self.game.vests["P1"].hp, 4)
        self.assertEqual(self.game.vests["P1"].hits_taken, 1)
        self.assertEqual(self.game.stats["P5"]["hits"], 1)
        self.assertGreater(self.game.vests["P1"].cooldown_until, time.time())

    def test_offline_sync_retry_not_double_counted(self):
        self._sync()
        self._sync()
        self.assertEqual(self.game.stats["P5"]["hits"], 1)
        self.assertEqual(self.game.vests["P1"].hits_taken, 1)

    def test_offline_sync_death_and_respawn_timer(self):
        self.game.vests["P1"].hp = 1
        self._sync(hp=0, lv=2, st="RESPAWN", rs=4000)
        v = self.game.vests["P1"]
        self.assertEqual((v.pstate, v.lives, v.deaths), ("RESPAWN", 2, 1))
        self.assertEqual(self.game.stats["P5"]["kills"], 1)
        self.assertGreater(v.respawn_at, time.time() + 3)

    def test_offline_sync_elimination_ends_team(self):
        self.game.vests["P2"].pstate = "OUT"
        self.game.vests["P1"].hp, self.game.vests["P1"].lives = 1, 1
        self._sync(hp=0, lv=0, st="OUT")
        self.assertEqual(self.game.result, "RED WINS")

    def test_offline_sync_from_old_match_discarded(self):
        self._sync(mid=-1)
        self.assertEqual(self.game.vests["P1"].hp, 5)
        self.assertIn("OFFLINE_SYNC_DISCARDED", [e["event"] for e in self.events])

    def test_offline_sync_bad_values_clamped(self):
        self._sync(hp=99, lv=99, ev=[["x"], [2, "H", 99, 0]])
        v = self.game.vests["P1"]
        self.assertEqual((v.hp, v.lives), (5, 3))

    def test_snapshot_restores_match(self):
        import tempfile
        saved = srv.MATCH_STATE_FILE
        srv.MATCH_STATE_FILE = os.path.join(tempfile.mkdtemp(), "state.json")
        try:
            self.game.process_hit("0xFF38C7", "P1")
            self.game.save_snapshot()
            other = srv.Game()
            self.assertTrue(other.restore_snapshot())
            self.assertEqual((other.phase, other.vests["P1"].hp), ("LIVE", 4))
            self.assertEqual(other.match_id, self.game.match_id)
        finally:
            srv.MATCH_STATE_FILE = saved

    def test_hit_disarms_only_the_victim(self):
        self.assertEqual(self.game.device_state("P1")["ds"], 0)
        self.game.process_hit("0xFF38C7", "P1")
        self.assertGreater(self.game.device_state("P1")["ds"], 9000)
        self.assertLessEqual(self.game.device_state("P1")["ds"], 10000)
        self.assertEqual(self.game.device_state("P2")["ds"], 0)

    def test_heal_and_blocked_shot_do_not_disarm(self):
        self.game.vests["P1"].hp = 3
        self.game.process_hit("0xFF18E7", "P1")
        self.game.vests["P1"].protect_until = time.time() + 3
        self.game.process_hit("0xFF38C7", "P1")
        self.assertEqual(self.game.device_state("P1")["ds"], 0)

    def test_disarm_frozen_by_pause_and_synced(self):
        self.game.process_hit("0xFF38C7", "P1")
        self.game.pause()
        frozen = self.game.device_state("P1")["ds"]
        self.game.paused_at -= 5
        self.game.resume()
        self.assertGreaterEqual(self.game.device_state("P1")["ds"], frozen - 100)
        self.game.sync_offline("P1", {"mid": self.game.match_id, "boot": 1, "ds": 4000, "ev": []})
        self.assertLessEqual(self.game.device_state("P1")["ds"], 4000)

    def test_unknown_vest_rejected(self):
        self.assertIsNone(self.game.touch_vest("P9", "10.0.0.1", {}))


if __name__ == "__main__":
    unittest.main()
