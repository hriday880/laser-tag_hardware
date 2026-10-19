#!/usr/bin/env python3
"""
Mark FX Laser Tag - Empirical Firmware & Protocol Adversarial Challenger Suite
Author: Challenger 1 (Firmware & Protocol Adversarial Challenger)
Target: mark_fx/mark_fx.ino

Empirical challenge tests covering:
1. Rapid trigger spam and contact chatter (40ms debounce cutoff, 600ms rate limiter, 500ms test rate limiter)
2. Corrupted NEC codes, 64-bit repeat codes (kRepeat), self-shot beams, noise immunity
3. Low health heartbeat audio tone timing and HUD sync at hp == 1 (BUG DETECTION: Priority preemption dropping heartbeat)
4. Standalone referee state transitions (damage -> 10s respawn -> 3s shield -> elimination)
5. WiFi drop, reconnect, and UDP discovery binding recovery (BUG DETECTION: Net discover drop to limbo)
"""

import os
import sys
import unittest
from typing import List, Tuple, Dict, Any, Optional

# Ensure project root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from mark_fx.tests.models import NECProtocol


# ==============================================================================
# FIRMWARE LOGIC EMULATION (Exact replica of mark_fx.ino C++ implementations)
# ==============================================================================

class FirmwareTrigger:
    """Exact emulation of mark_fx.ino lines 329-383."""
    FIRE_COOLDOWN_MATCH_MS = 600
    FIRE_COOLDOWN_TEST_MS = 500

    def __init__(self, mode="MATCH_LIVE"):
        self.debounced_state = 1  # HIGH (INPUT_PULLUP)
        self.last_reading = 1
        self.last_debounce_ms = 0
        self.last_shot_at = 0
        self.shots_fired = 0
        self.mode = mode
        self.pst = "ALIVE"
        self.lives = 3
        self.rs_ms = 0
        self.state_at = 0
        self.net = "NET_OK" if mode == "MATCH_LIVE" else "NET_LOST"
        self.ph = "LIVE" if mode == "MATCH_LIVE" else "LOBBY"
        self.is_standalone = (mode == "STANDALONE")

    def remaining_rs(self, now):
        r = self.rs_ms - (now - self.state_at)
        return max(0, r)

    def handle_trigger(self, reading: int, now: int) -> bool:
        shot_fired = False
        if reading != self.last_reading:
            self.last_debounce_ms = now
            self.last_reading = reading

        if (now - self.last_debounce_ms) >= 40:
            if reading != self.debounced_state:
                self.debounced_state = reading
                if self.debounced_state == 0:  # Confirmed press (LOW)
                    cooldown = self.FIRE_COOLDOWN_MATCH_MS if (self.net == "NET_OK" and self.ph == "LIVE") else self.FIRE_COOLDOWN_TEST_MS
                    if (now - self.last_shot_at) >= cooldown:
                        if self.net == "NET_OK" and self.ph == "LIVE":
                            if self.pst == "ALIVE" and self.remaining_rs(now) == 0:
                                self.last_shot_at = now
                                self.shots_fired += 1
                                shot_fired = True
                        elif self.is_standalone:
                            if self.pst == "ALIVE" and self.lives > 0:
                                self.last_shot_at = now
                                self.shots_fired += 1
                                shot_fired = True
                        else:
                            self.last_shot_at = now
                            self.shots_fired += 1
                            shot_fired = True
        return shot_fired


class FirmwareHUDAudioEngine:
    """Exact emulation of mark_fx.ino audio priorities, heartbeat, and HUD."""
    M_HIT = [(330, 110), (0, 70), (262, 140)]            # Total: 320ms, PRIO_EVENT = 2
    M_HEARTBEAT = [(220, 80), (0, 80), (220, 80)]        # Total: 240ms, PRIO_GAMEPLAY = 1
    M_DEATH = [(784, 180), (0, 40), (659, 180), (0, 40), (523, 180), (0, 40), (392, 450)] # PRIO_CRITICAL = 3
    M_ELIM = [(523, 300), (0, 80), (392, 300), (0, 80), (330, 300), (0, 80), (262, 700)]   # PRIO_CRITICAL = 3
    M_SHIELD = [(1200, 60), (0, 50), (1200, 60)]         # Total: 170ms, PRIO_EVENT = 2
    M_SHOT = [(1800, 40), (1200, 40)]                    # Total: 80ms, PRIO_GAMEPLAY = 1

    PRIO_IDLE = 0
    PRIO_GAMEPLAY = 1
    PRIO_EVENT = 2
    PRIO_CRITICAL = 3

    def __init__(self, is_standalone=True):
        self.is_standalone = is_standalone
        self.hp = 5
        self.lives = 3
        self.pst = "ALIVE"
        self.ph = "LIVE"
        self.net = "NET_LOST" if is_standalone else "NET_OK"
        
        # Audio state
        self.current_melody: Optional[List[Tuple[int, int]]] = None
        self.melody_idx = 0
        self.current_priority = self.PRIO_IDLE
        self.note_ends_at = 0
        self.last_heartbeat_tone_at = 0
        
        # Observability counters for empirical verification
        self.heartbeat_attempts = 0
        self.heartbeat_successes = 0
        self.heartbeat_dropped = 0
        self.muzzle_flash_until = 0

    def play_sound(self, melody: List[Tuple[int, int]], priority: int, now: int) -> bool:
        if self.current_melody is not None and priority < self.current_priority:
            return False  # Blocked by higher priority active melody
        self.current_melody = melody
        self.melody_idx = 0
        self.current_priority = priority
        self.note_ends_at = now + melody[0][1]
        return True

    def update_sound(self, now: int):
        if self.current_melody is None:
            return
        if now < self.note_ends_at:
            return
        self.melody_idx += 1
        if self.melody_idx >= len(self.current_melody):
            self.current_melody = None
            self.current_priority = self.PRIO_IDLE
            return
        self.note_ends_at = now + self.current_melody[self.melody_idx][1]

    def update_heartbeat(self, now: int):
        in_game = (self.net == "NET_OK" and self.ph == "LIVE") or (self.is_standalone and self.lives > 0)
        if in_game and self.pst == "ALIVE" and self.hp == 1:
            if now - self.last_heartbeat_tone_at >= 1000:
                self.last_heartbeat_tone_at = now
                self.heartbeat_attempts += 1
                ok = self.play_sound(self.M_HEARTBEAT, self.PRIO_GAMEPLAY, now)
                if ok:
                    self.heartbeat_successes += 1
                else:
                    self.heartbeat_dropped += 1

    def trigger_hit(self, now: int):
        """Firmware logic when hit is taken."""
        self.hp = max(0, self.hp - 1)
        if self.hp == 1:
            self.last_heartbeat_tone_at = 0  # Line 469 and Line 553
        self.play_sound(self.M_HIT, self.PRIO_EVENT, now)

    def get_hud_state(self, now: int) -> List[int]:
        """Firmware HUD update matching mark_fx.ino lines 247-326."""
        if now < self.muzzle_flash_until:
            return [1, 1, 1, 1, 1]

        if self.is_standalone:
            if self.lives <= 0 or self.pst == "OUT":
                return [0, 0, 0, 0, 0]
            if self.pst == "RESPAWN":
                b = 1 if ((now // 250) % 2) == 0 else 0
                return [b, b, b, b, b]
            if self.hp >= 5: return [1, 1, 1, 1, 1]
            if self.hp == 4: return [1, 1, 1, 1, 0]
            if self.hp == 3: return [1, 1, 1, 0, 0]
            if self.hp == 2: return [1, 1, 0, 0, 0]
            if self.hp == 1:
                b = 1 if ((now // 150) % 2) == 0 else 0
                return [b, 0, 0, 0, 0]
            return [0, 0, 0, 0, 0]
        else:
            if self.net == "NET_DISCOVER" or self.ph == "LOBBY":
                seq = [0, 1, 2, 3, 4, 3, 2, 1]
                idx = seq[(now // 100) % 8]
                return [1 if i == idx else 0 for i in range(5)]
            if self.hp == 1:
                b = 1 if ((now // 150) % 2) == 0 else 0
                return [b, 0, 0, 0, 0]
            if self.hp >= 5: return [1, 1, 1, 1, 1]
            return [1 if i < self.hp else 0 for i in range(5)]


class FirmwareStandaloneReferee:
    """Exact emulation of mark_fx.ino lines 523-579 and 388-397."""
    PLAYER_CODES = [
        0x00FF30CF, 0x00FF18E7, 0x00FF7A85, 0x00FF10EF,
        0x00FF38C7, 0x00FF5AA5, 0x00FF42BD, 0x00FF4AB5
    ]

    def __init__(self, node_id="P1"):
        self.node_id = node_id
        self.hp = 5
        self.lives = 3
        self.pst = "ALIVE"
        self.offline_respawn_at = 0
        self.offline_shield_until = 0
        self.offline_cooldown_until = 0
        self.last_heartbeat_tone_at = 0
        self.audio = FirmwareHUDAudioEngine(is_standalone=True)
        self.events_logged: List[str] = []

    def get_my_shot_code(self):
        idx = int(self.node_id[1]) - 1
        return self.PLAYER_CODES[idx]

    def is_known_player(self, code: int) -> bool:
        return code in self.PLAYER_CODES

    def is_my_team(self, code: int) -> bool:
        if not self.is_known_player(code):
            return False
        i_am_blue = self.node_id in ["P1", "P2", "P3", "P4"]
        code_is_blue = code in self.PLAYER_CODES[:4]
        return i_am_blue == code_is_blue

    def update_standalone(self, now: int):
        if self.pst == "RESPAWN" and now >= self.offline_respawn_at:
            self.pst = "ALIVE"
            self.hp = 5
            self.offline_shield_until = now + 3000
            self.audio.play_sound(FirmwareHUDAudioEngine.M_SHIELD, FirmwareHUDAudioEngine.PRIO_EVENT, now)
            self.events_logged.append(f"RESPAWN_DONE@{now}")

    def handle_ir(self, code: int, now: int) -> str:
        # Filter invalid codes, 32-bit and 64-bit NEC repeat codes (Line 508)
        if code == 0 or (code & 0xFFFFFFFF) == 0xFFFFFFFF or code == 0xFFFFFFFFFFFFFFFF:
            return "FILTERED_REPEAT_OR_ZERO"

        # Filter reflections of own shot (Line 511)
        if (code & 0xFFFFFFFF) == self.get_my_shot_code():
            return "FILTERED_SELF_SHOT"

        if self.lives <= 0 or self.pst == "OUT":
            return "IGNORED_DEAD"

        if not self.is_known_player(code & 0xFFFFFFFF):
            return "IGNORED_UNKNOWN"

        if self.pst == "RESPAWN":
            return "IGNORED_RESPAWNING"

        friendly = self.is_my_team(code & 0xFFFFFFFF)

        if not friendly:
            # Enemy hit
            if now < self.offline_shield_until:
                self.audio.play_sound(FirmwareHUDAudioEngine.M_SHIELD, FirmwareHUDAudioEngine.PRIO_EVENT, now)
                return "BLOCKED_SHIELD"

            if now < self.offline_cooldown_until:
                return "BLOCKED_COOLDOWN"

            self.hp -= 1
            self.offline_cooldown_until = now + 3000
            self.audio.hp = self.hp
            self.audio.lives = self.lives
            self.audio.pst = self.pst

            if self.hp > 0:
                if self.hp == 1:
                    self.last_heartbeat_tone_at = 0
                self.audio.play_sound(FirmwareHUDAudioEngine.M_HIT, FirmwareHUDAudioEngine.PRIO_EVENT, now)
                return "HIT"
            else:
                self.lives -= 1
                self.audio.lives = self.lives
                if self.lives > 0:
                    self.pst = "RESPAWN"
                    self.hp = 0
                    self.audio.hp = 0
                    self.audio.pst = "RESPAWN"
                    self.offline_respawn_at = now + 10000
                    self.audio.play_sound(FirmwareHUDAudioEngine.M_DEATH, FirmwareHUDAudioEngine.PRIO_CRITICAL, now)
                    return "DEATH_RESPAWN"
                else:
                    self.pst = "OUT"
                    self.hp = 0
                    self.lives = 0
                    self.audio.hp = 0
                    self.audio.lives = 0
                    self.audio.pst = "OUT"
                    self.audio.play_sound(FirmwareHUDAudioEngine.M_ELIM, FirmwareHUDAudioEngine.PRIO_CRITICAL, now)
                    return "ELIMINATED"
        else:
            # Medic heal
            if self.hp < 5:
                self.hp += 1
                self.audio.play_sound(FirmwareHUDAudioEngine.M_HEAL, FirmwareHUDAudioEngine.PRIO_EVENT, now)
                return "HEAL"
            else:
                self.audio.play_sound(FirmwareHUDAudioEngine.M_SHIELD, FirmwareHUDAudioEngine.PRIO_EVENT, now)
                return "HEAL_FULL"


class FirmwareNetworkManager:
    """Exact emulation of mark_fx.ino lines 608-662."""
    def __init__(self, boot_wifi_connected=True):
        self.wifi_connected = boot_wifi_connected
        self.server_ip = ""
        self.net = "NET_DISCOVER" if boot_wifi_connected else "NET_LOST"
        self.is_standalone = not boot_wifi_connected
        self.udp_listening = boot_wifi_connected
        self.fail_count = 0
        self.last_heartbeat = 0
        self.last_probe = 0
        self.last_reconnect = 0

    def update_network(self, now: int, server_discovered: bool = False, server_responds: bool = False):
        if not self.wifi_connected:
            self.udp_listening = False
            if self.net == "NET_OK":
                self.net = "NET_LOST"
                self.is_standalone = True
            # WiFi reconnect attempt every 5000ms (Line 617)
            if (now - self.last_reconnect) > 5000:
                self.last_reconnect = now
            return

        if not self.udp_listening:
            self.udp_listening = True
            if self.net == "NET_LOST" or self.net == "NET_DISCOVER":
                self.net = "NET_DISCOVER"

        if server_discovered and self.server_ip == "":
            self.server_ip = "192.168.1.100"
            if server_responds:
                self.net = "NET_OK"
                self.fail_count = 0
                self.is_standalone = False

        if self.net in ["NET_DISCOVER", "NET_LOST"]:
            if (now - self.last_probe) > 2000:
                self.last_probe = now
                if len(self.server_ip) > 0 and server_responds:
                    self.net = "NET_OK"
                    self.is_standalone = False
                    self.fail_count = 0
        elif self.net == "NET_OK":
            if (now - self.last_heartbeat) > 1000:
                self.last_heartbeat = now
                if server_responds:
                    self.fail_count = 0
                else:
                    self.fail_count += 1
                    if self.fail_count >= 3:
                        self.net = "NET_LOST"
                        self.is_standalone = True


# ==============================================================================
# EMPIRICAL ADVERSARIAL TEST SUITE
# ==============================================================================

class TestFirmwareAdversarialTrigger(unittest.TestCase):
    """Stress tests trigger chatter, debounce cutoff, rate limiter, and modes."""

    def test_contact_bounce_burst_suppression(self):
        """Empirically verify high-frequency contact bounce (0/1 oscillations < 40ms) fires ZERO shots."""
        trigger = FirmwareTrigger(mode="MATCH_LIVE")
        now = 1000
        # Oscillate every 3ms for 30ms (simulating cheap mechanical chatter)
        for i in range(10):
            val = 0 if i % 2 == 0 else 1
            shot = trigger.handle_trigger(reading=val, now=now)
            self.assertFalse(shot, f"Spurious shot fired during chatter at {now}ms!")
            now += 3
        self.assertEqual(trigger.shots_fired, 0)

    def test_exact_40ms_debounce_boundary(self):
        """Empirically test exact boundary: 39ms is rejected, 40ms is accepted."""
        trigger = FirmwareTrigger(mode="MATCH_LIVE")
        t_press = 1000
        # Pin goes LOW at t=1000
        trigger.handle_trigger(0, now=t_press)
        
        # Test at t=1039 (39ms elapsed) -> MUST NOT FIRE
        shot_39 = trigger.handle_trigger(0, now=t_press + 39)
        self.assertFalse(shot_39, "Shot fired prematurely at 39ms (<40ms cutoff)!")
        self.assertEqual(trigger.shots_fired, 0)

        # Test at t=1040 (40ms elapsed) -> MUST FIRE
        shot_40 = trigger.handle_trigger(0, now=t_press + 40)
        self.assertTrue(shot_40, "Shot failed to fire at exactly 40ms debounce cutoff!")
        self.assertEqual(trigger.shots_fired, 1)

    def test_continuous_trigger_hold_no_runaway_fire(self):
        """Empirically verify holding trigger for 10 seconds fires exactly ONE shot."""
        trigger = FirmwareTrigger(mode="MATCH_LIVE")
        trigger.handle_trigger(0, now=1000)
        trigger.handle_trigger(0, now=1040)
        self.assertEqual(trigger.shots_fired, 1)

        # Continuously sample every 10ms up to t=10000ms
        for t in range(1050, 10000, 10):
            shot = trigger.handle_trigger(0, now=t)
            self.assertFalse(shot, f"Runaway shot fired at {t}ms while holding trigger!")
        self.assertEqual(trigger.shots_fired, 1)

    def test_trigger_spam_rate_limiter_match_mode(self):
        """Verify rapid repeated trigger pulls in match mode are limited to 600ms cooldown."""
        trigger = FirmwareTrigger(mode="MATCH_LIVE")
        now = 1000
        # Shot 1 at t=1040ms
        trigger.handle_trigger(0, now=now)
        shot1 = trigger.handle_trigger(0, now=now + 40)
        self.assertTrue(shot1)
        self.assertEqual(trigger.shots_fired, 1)

        # Release trigger at t=1100ms, debounce release at t=1140ms
        trigger.handle_trigger(1, now=1100)
        trigger.handle_trigger(1, now=1140)

        # Attempt Shot 2 at t=1500ms (elapsed since Shot 1 = 460ms < 600ms)
        trigger.handle_trigger(0, now=1500)
        shot_early = trigger.handle_trigger(0, now=1540)
        self.assertFalse(shot_early, "Rate limiter failed to block shot before 600ms!")
        self.assertEqual(trigger.shots_fired, 1)

        # Release and wait until t=1650ms (elapsed since Shot 1 = 610ms > 600ms)
        trigger.handle_trigger(1, now=1560)
        trigger.handle_trigger(1, now=1600)
        trigger.handle_trigger(0, now=1610)
        shot_ok = trigger.handle_trigger(0, now=1650)
        self.assertTrue(shot_ok, "Rate limiter failed to fire valid shot after 600ms!")
        self.assertEqual(trigger.shots_fired, 2)

    def test_standalone_mode_cooldown_discrepancy(self):
        """
        Verify that in Standalone Mode, the rate limiter uses FIRE_COOLDOWN_TEST_MS (500ms)
        instead of FIRE_COOLDOWN_MATCH_MS (600ms) because net != NET_OK.
        """
        trigger = FirmwareTrigger(mode="STANDALONE")
        now = 1000
        # Shot 1 at t=1040ms
        trigger.handle_trigger(0, now=now)
        trigger.handle_trigger(0, now=now + 40)
        self.assertEqual(trigger.shots_fired, 1)

        # Release trigger
        trigger.handle_trigger(1, now=1100)
        trigger.handle_trigger(1, now=1140)

        # In standalone mode, cooldown is 500ms!
        # At t=1550ms (510ms elapsed), a shot is ACCEPTED:
        trigger.handle_trigger(0, now=1510)
        shot_standalone_510 = trigger.handle_trigger(0, now=1550)
        self.assertTrue(
            shot_standalone_510,
            "Standalone mode should accept shot at 510ms due to 500ms test cooldown!"
        )


class TestFirmwareAdversarialIRAndProtocol(unittest.TestCase):
    """Stress tests IR decoding, repeat codes, self-shot beams, and noise immunity."""

    def setUp(self):
        self.ref = FirmwareStandaloneReferee(node_id="P1")

    def test_64bit_repeat_code_krepeat_rejected(self):
        """Verify 64-bit NEC repeat code 0xFFFFFFFFFFFFFFFF (kRepeat) is filtered."""
        res = self.ref.handle_ir(0xFFFFFFFFFFFFFFFF, now=1000)
        self.assertEqual(res, "FILTERED_REPEAT_OR_ZERO")
        self.assertEqual(self.ref.hp, 5)

    def test_32bit_repeat_code_rejected(self):
        """Verify 32-bit NEC repeat code 0xFFFFFFFF is filtered."""
        res = self.ref.handle_ir(0xFFFFFFFF, now=1000)
        self.assertEqual(res, "FILTERED_REPEAT_OR_ZERO")
        self.assertEqual(self.ref.hp, 5)

    def test_zero_code_rejected(self):
        """Verify 0x00000000 is filtered."""
        res = self.ref.handle_ir(0, now=1000)
        self.assertEqual(res, "FILTERED_REPEAT_OR_ZERO")
        self.assertEqual(self.ref.hp, 5)

    def test_self_shot_beam_reflection_rejected_all_8_players(self):
        """Verify that for every player P1..P8, their own IR beam reflection is filtered."""
        for p_idx in range(1, 9):
            p_id = f"P{p_idx}"
            ref_node = FirmwareStandaloneReferee(node_id=p_id)
            own_code = ref_node.get_my_shot_code()
            res = ref_node.handle_ir(own_code, now=1000)
            self.assertEqual(
                res, "FILTERED_SELF_SHOT",
                f"Player {p_id} failed to filter own shot reflection 0x{own_code:08X}!"
            )
            self.assertEqual(ref_node.hp, 5)

    def test_corrupted_nec_single_bit_flip_ignored(self):
        """Verify single-bit corrupted enemy code (e.g. 0x00FF38C7 ^ 1) is rejected in standalone mode."""
        enemy_code = 0x00FF38C7  # P5 Enemy 1
        corrupted_code = enemy_code ^ 0x01
        res = self.ref.handle_ir(corrupted_code, now=1000)
        self.assertEqual(res, "IGNORED_UNKNOWN")
        self.assertEqual(self.ref.hp, 5)

    def test_foreign_tv_remote_noise_rejection(self):
        """Verify foreign remote / optical noise (e.g. 0x20DF10EF) is rejected in standalone mode."""
        res = self.ref.handle_ir(0x20DF10EF, now=1000)
        self.assertEqual(res, "IGNORED_UNKNOWN")
        self.assertEqual(self.ref.hp, 5)


class TestFirmwareAdversarialHeartbeatAndHUD(unittest.TestCase):
    """
    Stress tests low-health heartbeat audio tone timing and HUD synchronization at hp == 1.
    Includes empirical demonstration of the Priority Preemption Bug and Phase Drift.
    """

    def test_heartbeat_drop_bug_empirical_reproduction(self):
        """
        EMPIRICAL BUG REPRODUCTION:
        When a hit drops HP to 1:
        1. handle_ir calls: if (hp == 1) lastHeartbeatToneAt = 0; PLAY(M_HIT, PRIO_EVENT);
        2. M_HIT is now playing with PRIO_EVENT (2).
        3. On the next loop tick, updateHeartbeat() sees now - 0 >= 1000.
        4. It sets lastHeartbeatToneAt = now, and calls PLAY(M_HEARTBEAT, PRIO_GAMEPLAY).
        5. Because PRIO_GAMEPLAY (1) < PRIO_EVENT (2), playSound() REJECTS the heartbeat!
        6. Result: The initial heartbeat is dropped, and no heartbeat plays for 1000ms!
        """
        engine = FirmwareHUDAudioEngine(is_standalone=True)
        engine.hp = 2  # At 2 HP
        now = 5000

        # Player takes hit at now=5000ms, dropping to 1 HP
        engine.trigger_hit(now=now)
        self.assertEqual(engine.hp, 1)
        self.assertEqual(engine.last_heartbeat_tone_at, 0)
        self.assertEqual(engine.current_priority, FirmwareHUDAudioEngine.PRIO_EVENT)

        # On the very next tick at now=5001ms, loop() calls updateHeartbeat()
        engine.update_heartbeat(now=5001)

        # BUG CONFIRMED EMPIRICALLY:
        self.assertEqual(engine.heartbeat_attempts, 1, "Heartbeat should have attempted to play")
        self.assertEqual(engine.heartbeat_dropped, 1, "Heartbeat was dropped due to priority preemption by M_HIT!")
        self.assertEqual(engine.heartbeat_successes, 0, "Zero heartbeat sounds succeeded on transition to 1 HP!")
        self.assertEqual(engine.last_heartbeat_tone_at, 5001, "Timer was advanced despite sound being dropped!")

        # Over the next 900ms (while M_HIT completes), no heartbeat is attempted because timer was advanced
        for t in range(5002, 6000, 50):
            engine.update_sound(now=t)
            engine.update_heartbeat(now=t)
        self.assertEqual(engine.heartbeat_successes, 0, "Player suffered 1000ms of silence at 1 HP without warning tone!")

        # Only at t=6001ms (1000ms later) does heartbeat finally play:
        engine.update_heartbeat(now=6001)
        self.assertEqual(engine.heartbeat_successes, 1)

    def test_hud_panic_pulse_vs_heartbeat_phase_drift(self):
        """
        EMPIRICAL CHALLENGE: Verify phase relationship between HUD LED 1 and Heartbeat tone.
        HUD LED 1 pulses at period 300ms ((now / 150) % 2).
        Heartbeat sounds every 1000ms.
        Demonstrate that at t=2000ms and t=5000ms, the audio heartbeat fires while the LED is OFF!
        """
        engine = FirmwareHUDAudioEngine(is_standalone=True)
        engine.hp = 1
        
        # Test LED state at exact 1000ms intervals when heartbeat fires:
        phases = {}
        for t in [1000, 2000, 3000, 4000, 5000]:
            hud = engine.get_hud_state(now=t)
            d18_state = hud[0]
            phases[t] = d18_state

        # At t=1000ms: 1000//150 = 6 (even) -> ON (1)
        self.assertEqual(phases[1000], 1)
        # At t=2000ms: 2000//150 = 13 (odd) -> OFF (0)
        self.assertEqual(phases[2000], 0, "At t=2000ms, Heartbeat fires while HUD LED 1 is OFF!")
        # At t=3000ms: 3000//150 = 20 (even) -> ON (1)
        self.assertEqual(phases[3000], 1)
        # At t=5000ms: 5000//150 = 33 (odd) -> OFF (0)
        self.assertEqual(phases[5000], 0, "At t=5000ms, Heartbeat fires while HUD LED 1 is OFF!")


class TestFirmwareAdversarialStandaloneTransitions(unittest.TestCase):
    """Stress tests the complete standalone referee finite state machine."""

    def setUp(self):
        self.ref = FirmwareStandaloneReferee(node_id="P1")
        self.enemy_shot = 0x00FF38C7  # P5
        self.friend_shot = 0x00FF18E7 # P2

    def test_full_damage_to_respawn_transition(self):
        """Verify 5 hits transition from ALIVE to RESPAWN, deducting 1 life."""
        now = 1000
        for i in range(4):
            res = self.ref.handle_ir(self.enemy_shot, now=now)
            self.assertEqual(res, "HIT")
            now += 3500  # Advance past 3s cooldown

        self.assertEqual(self.ref.hp, 1)
        self.assertEqual(self.ref.lives, 3)

        # 5th hit: triggers death and 10s respawn
        res5 = self.ref.handle_ir(self.enemy_shot, now=now)
        self.assertEqual(res5, "DEATH_RESPAWN")
        self.assertEqual(self.ref.hp, 0)
        self.assertEqual(self.ref.lives, 2)
        self.assertEqual(self.ref.pst, "RESPAWN")
        self.assertEqual(self.ref.offline_respawn_at, now + 10000)

    def test_10s_respawn_lockout_blocks_hits_and_shots(self):
        """Verify that during 10s respawn, all incoming hits and outgoing shots are blocked."""
        # Put into respawn
        self.ref.pst = "RESPAWN"
        self.ref.hp = 0
        self.ref.lives = 2
        self.ref.offline_respawn_at = 10000

        # Incoming hits are ignored
        res = self.ref.handle_ir(self.enemy_shot, now=5000)
        self.assertEqual(res, "IGNORED_RESPAWNING")
        self.assertEqual(self.ref.hp, 0)

        # Outgoing trigger is blocked
        trig = FirmwareTrigger(mode="STANDALONE")
        trig.pst = "RESPAWN"
        trig.lives = 2
        trig.handle_trigger(0, now=5000)
        shot = trig.handle_trigger(0, now=5040)
        self.assertFalse(shot, "Weapon fired while in RESPAWN state!")

    def test_respawn_shield_3s_invulnerability(self):
        """Verify that after 10s respawn completes, a 3s shield blocks damage but allows shooting."""
        self.ref.pst = "RESPAWN"
        self.ref.hp = 0
        self.ref.lives = 2
        self.ref.offline_respawn_at = 10000

        # Complete respawn at t=10000ms
        self.ref.update_standalone(now=10000)
        self.assertEqual(self.ref.pst, "ALIVE")
        self.assertEqual(self.ref.hp, 5)
        self.assertEqual(self.ref.offline_shield_until, 13000)

        # Incoming hit during shield at t=11000ms is BLOCKED
        res = self.ref.handle_ir(self.enemy_shot, now=11000)
        self.assertEqual(res, "BLOCKED_SHIELD")
        self.assertEqual(self.ref.hp, 5)

        # Outgoing shot during shield is ALLOWED
        trig = FirmwareTrigger(mode="STANDALONE")
        trig.pst = "ALIVE"
        trig.lives = 2
        trig.handle_trigger(0, now=11000)
        shot = trig.handle_trigger(0, now=11040)
        self.assertTrue(shot, "Weapon should be able to fire during 3s spawn shield!")

        # After shield expires at t=13001ms, damage is taken
        res_after = self.ref.handle_ir(self.enemy_shot, now=13001)
        self.assertEqual(res_after, "HIT")
        self.assertEqual(self.ref.hp, 4)

    def test_elimination_after_all_lives_exhausted(self):
        """Verify losing last life transitions to OUT, setting all HUD LEDs OFF and permanent lockout."""
        self.ref.lives = 1
        self.ref.hp = 1
        res = self.ref.handle_ir(self.enemy_shot, now=1000)
        self.assertEqual(res, "ELIMINATED")
        self.assertEqual(self.ref.lives, 0)
        self.assertEqual(self.ref.hp, 0)
        self.assertEqual(self.ref.pst, "OUT")

        # HUD must be completely off
        hud = self.ref.audio.get_hud_state(now=1000)
        self.assertEqual(hud, [0, 0, 0, 0, 0])

        # Any further hits must be ignored
        res_after = self.ref.handle_ir(self.enemy_shot, now=5000)
        self.assertEqual(res_after, "IGNORED_DEAD")


class TestFirmwareAdversarialNetworkRecovery(unittest.TestCase):
    """Stress tests WiFi drop, reconnect, and UDP discovery binding recovery."""

    def test_boot_without_wifi_enters_standalone(self):
        """Verify booting without WiFi immediately initializes standalone referee."""
        net = FirmwareNetworkManager(boot_wifi_connected=False)
        self.assertTrue(net.is_standalone)
        self.assertEqual(net.net, "NET_LOST")
        self.assertFalse(net.udp_listening)

    def test_wifi_drop_from_net_ok_enters_standalone(self):
        """Verify WiFi dropping during an active match enters standalone mode."""
        net = FirmwareNetworkManager(boot_wifi_connected=True)
        # Connected to server
        net.update_network(now=1000, server_discovered=True, server_responds=True)
        self.assertEqual(net.net, "NET_OK")
        self.assertFalse(net.is_standalone)

        # WiFi drops at t=2000ms
        net.wifi_connected = False
        net.update_network(now=2000)
        self.assertEqual(net.net, "NET_LOST")
        self.assertTrue(net.is_standalone)
        self.assertFalse(net.udp_listening)

    def test_wifi_reconnect_recovers_udp_and_server(self):
        """Verify WiFi reconnecting re-binds UDP and recovers NET_OK upon server response."""
        net = FirmwareNetworkManager(boot_wifi_connected=True)
        net.update_network(now=1000, server_discovered=True, server_responds=True)
        net.wifi_connected = False
        net.update_network(now=2000)
        self.assertEqual(net.net, "NET_LOST")

        # WiFi reconnects at t=8000ms
        net.wifi_connected = True
        net.update_network(now=8000, server_discovered=False, server_responds=False)
        self.assertTrue(net.udp_listening)
        self.assertEqual(net.net, "NET_DISCOVER")

        # Server probe succeeds at t=10100ms
        net.update_network(now=10100, server_discovered=False, server_responds=True)
        self.assertEqual(net.net, "NET_OK")
        self.assertFalse(net.is_standalone)

    def test_net_discover_wifi_drop_limbo_bug_reproduction(self):
        """
        EMPIRICAL BUG REPRODUCTION:
        If device boots with WiFi connected to an AP, but server is offline (net == NET_DISCOVER),
        and then WiFi drops:
        mark_fx.ino Line 613 checks:
            if (net == NET_OK) {
                net = NET_LOST;
                isStandalone = true;
            }
        Because net is NET_DISCOVER (not NET_OK), isStandalone remains FALSE!
        The device is stuck in NET_DISCOVER limbo without WiFi and never falls back to Standalone!
        """
        net = FirmwareNetworkManager(boot_wifi_connected=True)
        self.assertEqual(net.net, "NET_DISCOVER")
        self.assertFalse(net.is_standalone)

        # WiFi drops before server was ever connected
        net.wifi_connected = False
        net.update_network(now=2000)

        # BUG CONFIRMED EMPIRICALLY:
        self.assertFalse(
            net.is_standalone,
            "Due to line 613 checking only 'net == NET_OK', isStandalone remains FALSE when WiFi drops during discovery!"
        )
        self.assertEqual(
            net.net, "NET_DISCOVER",
            "net remained NET_DISCOVER instead of transitioning to NET_LOST!"
        )


if __name__ == "__main__":
    unittest.main()
