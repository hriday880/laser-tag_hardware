"""
Mark FX Laser Tag - Test Models and Emulators
Pure-Python specification models for electrical physics, NEC IR protocol,
HUD state machine, audio engine, trigger debounce, and standalone referee.
"""

import time
import math
from typing import Dict, List, Tuple, Optional, Any


# ==============================================================================
# 1. ELECTRICAL & HARDWARE PHYSICS MODEL
# ==============================================================================

class ElectricalModel:
    """
    Authoritative electrical calculations based on ORIGINAL_REQUEST.md
    and ESP32 DevKit V1 hardware specifications.
    """
    VDD = 3.3  # ESP32 3.3V logic supply
    RDS_ON_NOMINAL = 12.0  # Internal PMOS channel resistance (Ω)
    RDS_ON_MIN = 10.0
    RDS_ON_MAX = 14.0
    
    # Forward voltages (Vf)
    VF_IR_940NM = 1.35  # Nominal Vf for 940nm AlGaAs 5mm LED at 15-20mA
    VF_IR_MIN = 1.25
    VF_IR_MAX = 1.45
    
    VF_RED_LED = 1.90   # Nominal Vf for standard 3mm/5mm Red LED
    VF_GREEN_LED = 2.10 # Nominal Vf for standard 3mm/5mm Green LED
    
    # Absolute limits
    ESP32_GPIO_MAX_MA = 40.0       # Absolute maximum rating per GPIO pin
    ESP32_GPIO_RECOMMENDED_MA = 20.0 # Recommended safe maximum continuous current
    HUD_TOTAL_BUDGET_MA = 25.0     # Acceptance criteria AC-2: total HUD current < 25mA
    TSOP_MAX_BUDGET_MA = 5.0       # Acceptance criteria: TSOP vest array current < 5mA
    
    @classmethod
    def calculate_ir_led_current(cls, r_ext: float, r_ds: float = RDS_ON_NOMINAL, vf: float = VF_IR_940NM) -> float:
        """Calculate IR LED forward current in mA: I = (VDD - Vf) / (R_ext + R_ds) * 1000"""
        total_r = r_ext + r_ds
        if total_r <= 0:
            raise ValueError("Total circuit resistance must be positive")
        current_a = (cls.VDD - vf) / total_r
        return current_a * 1000.0  # Return mA

    @classmethod
    def calculate_ir_resistor_dissipation(cls, r_ext: float, current_ma: float, duty_cycle: float = 1.0) -> float:
        """Calculate power dissipation in mW: P = I^2 * R * duty_cycle"""
        current_a = current_ma / 1000.0
        power_w = (current_a ** 2) * r_ext * duty_cycle
        return power_w * 1000.0  # Return mW

    @classmethod
    def calculate_hud_led_current(cls, r_ext: float, led_type: str = "red", r_ds: float = RDS_ON_NOMINAL) -> float:
        """Calculate single HUD LED forward current in mA."""
        vf = cls.VF_RED_LED if led_type.lower() == "red" else cls.VF_GREEN_LED
        total_r = r_ext + r_ds
        current_a = (cls.VDD - vf) / total_r
        return current_a * 1000.0

    @classmethod
    def calculate_hud_total_current(cls, count: int, r_ext: float, led_type: str = "red") -> float:
        """Calculate total simultaneous HUD current for `count` lit LEDs."""
        return count * cls.calculate_hud_led_current(r_ext, led_type)

    @classmethod
    def calculate_tsop_array_current(cls, sensor_count: int = 5, per_sensor_ma: float = 0.7) -> float:
        """Calculate total quiescent current draw of parallel TSOP1838 vest array."""
        return sensor_count * per_sensor_ma

    @classmethod
    def calculate_umbilical_voltage_drop(cls, length_m: float = 1.5, wire_gauge_awg: int = 28, current_ma: float = 3.5) -> float:
        """Calculate round-trip voltage drop over umbilical cable in mV."""
        # Resistance of 28 AWG copper wire is ~0.213 Ω/m
        resistance_per_meter = 0.213 if wire_gauge_awg == 28 else 0.134  # 26 AWG
        total_resistance = 2 * length_m * resistance_per_meter  # Round-trip (power + ground)
        current_a = current_ma / 1000.0
        v_drop = current_a * total_resistance
        return v_drop * 1000.0  # Return mV


# ==============================================================================
# 2. 8-PLAYER 32-BIT NEC IR PROTOCOL MODEL
# ==============================================================================

class NECProtocol:
    """
    NEC 32-bit protocol encoder, decoder, and integrity validator.
    Strictly follows: [Address 8b] [~Address 8b] [Command 8b] [~Command 8b]
    """
    PLAYER_CODES: Dict[str, Dict[str, Any]] = {
        "P1": {"code": 0x00FF30CF, "hex": "0xFF30CF", "team": "FRIEND", "role": "Friend 1", "addr": 0x00, "cmd": 0x30},
        "P2": {"code": 0x00FF18E7, "hex": "0xFF18E7", "team": "FRIEND", "role": "Friend 2", "addr": 0x00, "cmd": 0x18},
        "P3": {"code": 0x00FF7A85, "hex": "0xFF7A85", "team": "FRIEND", "role": "Friend 3", "addr": 0x00, "cmd": 0x7A},
        "P4": {"code": 0x00FF10EF, "hex": "0xFF10EF", "team": "FRIEND", "role": "Friend 4", "addr": 0x00, "cmd": 0x10},
        "P5": {"code": 0x00FF38C7, "hex": "0xFF38C7", "team": "ENEMY",  "role": "Enemy 1",  "addr": 0x00, "cmd": 0x38},
        "P6": {"code": 0x00FF5AA5, "hex": "0xFF5AA5", "team": "ENEMY",  "role": "Enemy 2",  "addr": 0x00, "cmd": 0x5A},
        "P7": {"code": 0x00FF42BD, "hex": "0xFF42BD", "team": "ENEMY",  "role": "Enemy 3",  "addr": 0x00, "cmd": 0x42},
        "P8": {"code": 0x00FF4AB5, "hex": "0xFF4AB5", "team": "ENEMY",  "role": "Enemy 4",  "addr": 0x00, "cmd": 0x4A},
    }

    @classmethod
    def decompose(cls, code: int) -> Tuple[int, int, int, int]:
        """Decomposes 32-bit NEC code into (addr, inv_addr, cmd, inv_cmd)."""
        addr = (code >> 24) & 0xFF
        inv_addr = (code >> 16) & 0xFF
        cmd = (code >> 8) & 0xFF
        inv_cmd = code & 0xFF
        return addr, inv_addr, cmd, inv_cmd

    @classmethod
    def validate_nec_integrity(cls, code: int) -> bool:
        """Validates that addr ^ inv_addr == 0xFF and cmd ^ inv_cmd == 0xFF."""
        addr, inv_addr, cmd, inv_cmd = cls.decompose(code)
        addr_valid = (addr ^ inv_addr) == 0xFF
        cmd_valid = (cmd ^ inv_cmd) == 0xFF
        return addr_valid and cmd_valid

    @classmethod
    def encode_nec(cls, addr: int, cmd: int) -> int:
        """Constructs a valid 32-bit NEC word with automatic bitwise complements."""
        inv_addr = (~addr) & 0xFF
        inv_cmd = (~cmd) & 0xFF
        return (addr << 24) | (inv_addr << 16) | (cmd << 8) | inv_cmd

    @classmethod
    def lookup_code(cls, raw_code: Any) -> Optional[Dict[str, Any]]:
        """Look up player details from integer or hex string."""
        if isinstance(raw_code, str):
            code_str = raw_code.strip().upper()
            if code_str.startswith("0X"):
                code_int = int(code_str, 16)
            else:
                code_int = int(code_str, 16)
        else:
            code_int = int(raw_code)
            
        for player_id, data in cls.PLAYER_CODES.items():
            if data["code"] == code_int or (code_int & 0xFFFFFF) == (data["code"] & 0xFFFFFF):
                return {"id": player_id, **data}
        return None

    @classmethod
    def format_code_for_server(cls, code: int) -> str:
        """Format 32-bit integer code as expected by server.py sprintf(hexBuffer, '0x%llX', code)."""
        return f"0x{code:X}"


# ==============================================================================
# 3. 5-LED UNICOLOR HUD STATE MACHINE EMULATOR
# ==============================================================================

class HUDStateEngine:
    """
    Emulates the 5-LED HUD finite state machine.
    PINS: LED1=D18 (1 HP / Crit), LED2=D19 (2 HP), LED3=D21 (3 HP), LED4=D22 (4 HP), LED5=D23 (5 HP / Full)
    States: LOBBY, FULL_HP, DAMAGE, CRITICAL, RESPAWN_SHIELD, ELIMINATED, MUZZLE_FLASH
    """
    PINS = [18, 19, 21, 22, 23]

    def __init__(self):
        self.hp = 5
        self.lives = 3
        self.state = "LOBBY"
        self.led_states = [0, 0, 0, 0, 0]  # 0=LOW/OFF, 1=HIGH/ON
        self.flash_timer = 0
        self.flash_active = False
        self.panic_pulse_interval = 150  # ms
        self.respawn_pulse_interval = 250  # ms
        self.sweep_index = 0
        self.sweep_dir = 1
        self.last_update_ms = 0

    def set_hp(self, hp: int, lives: int = 3):
        self.hp = max(0, min(5, hp))
        self.lives = max(0, lives)
        if self.lives <= 0 or self.hp == 0:
            self.state = "ELIMINATED"
        elif self.hp == 1:
            self.state = "CRITICAL"
        elif self.hp == 5:
            self.state = "FULL_HP"
        else:
            self.state = "DAMAGE"

    def trigger_muzzle_flash(self, duration_ms: int = 50, now_ms: int = 0):
        self.flash_active = True
        self.flash_timer = now_ms + duration_ms

    def set_respawn_shield(self):
        self.state = "RESPAWN_SHIELD"

    def update(self, now_ms: int) -> List[int]:
        """Calculates pin output levels [D18, D19, D21, D22, D23] at given millisecond timestamp."""
        # 1. Muzzle flash takes instantaneous priority
        if self.flash_active:
            if now_ms < self.flash_timer:
                self.led_states = [1, 1, 1, 1, 1]
                return list(self.led_states)
            else:
                self.flash_active = False

        # 2. Main state machine
        if self.state == "LOBBY":
            # Knight Rider sweep back and forth
            # Step every 100ms
            step = (now_ms // 100) % 8
            # sequence: 0, 1, 2, 3, 4, 3, 2, 1
            seq = [0, 1, 2, 3, 4, 3, 2, 1]
            pos = seq[step]
            self.led_states = [1 if i == pos else 0 for i in range(5)]

        elif self.state == "FULL_HP":
            self.led_states = [1, 1, 1, 1, 1]

        elif self.state == "DAMAGE":
            # Progressively turn off from LED 5 down to LED 1
            self.led_states = [1 if i < self.hp else 0 for i in range(5)]

        elif self.state == "CRITICAL":
            # 1 HP: LED 1 (index 0, D18) pulses rapidly, others OFF
            phase = (now_ms // self.panic_pulse_interval) % 2
            self.led_states = [1 if phase == 0 else 0, 0, 0, 0, 0]

        elif self.state == "RESPAWN_SHIELD":
            # All 5 LEDs flash in unison
            phase = (now_ms // self.respawn_pulse_interval) % 2
            val = 1 if phase == 0 else 0
            self.led_states = [val, val, val, val, val]

        elif self.state == "ELIMINATED":
            # All LEDs OFF
            self.led_states = [0, 0, 0, 0, 0]

        return list(self.led_states)


# ==============================================================================
# 4. NON-BLOCKING AUDIO ENGINE MODEL
# ==============================================================================

class AudioEngineModel:
    """
    Emulates the non-blocking note scheduler and tone generator on GPIO 33.
    Tracks active tone frequency, duration, melody queue, and priorities.
    """
    PRIORITY_IDLE = 0
    PRIORITY_CHIRP = 1
    PRIORITY_MELODY = 2
    PRIORITY_DEATH = 3

    MELODIES = {
        "BOOT": [(523, 100), (659, 100), (784, 150), (1047, 250)],
        "SHOT": [(1800, 30), (2400, 40)],
        "HIT": [(880, 80), (440, 120)],
        "HEAL": [(587, 80), (880, 120)],
        "SHIELD": [(1047, 100), (1319, 100)],
        "HEARTBEAT": [(220, 80), (0, 80), (220, 80)],
        "DEATH": [(440, 150), (370, 150), (311, 200), (220, 400)],
        "MATCH_START": [(523, 100), (659, 100), (784, 100), (1047, 300)],
        "WIN": [(523, 150), (659, 150), (784, 150), (1047, 400)],
        "DEFEAT": [(440, 200), (330, 200), (220, 500)],
    }

    def __init__(self):
        self.active_freq = 0
        self.note_end_ms = 0
        self.current_melody: List[Tuple[int, int]] = []
        self.melody_index = 0
        self.current_priority = self.PRIORITY_IDLE
        self.is_playing = False

    def play(self, melody_name: str, priority: int = PRIORITY_MELODY, now_ms: int = 0) -> bool:
        """Attempt to play melody. Higher priority preempts lower priority."""
        if melody_name not in self.MELODIES:
            return False
            
        if self.is_playing and priority < self.current_priority:
            return False  # Blocked by higher priority playback
            
        self.current_melody = list(self.MELODIES[melody_name])
        self.melody_index = 0
        self.current_priority = priority
        self.is_playing = True
        
        freq, dur = self.current_melody[0]
        self.active_freq = freq
        self.note_end_ms = now_ms + dur
        return True

    def stop(self):
        self.active_freq = 0
        self.note_end_ms = 0
        self.current_melody = []
        self.melody_index = 0
        self.current_priority = self.PRIORITY_IDLE
        self.is_playing = False

    def update(self, now_ms: int):
        """Advances non-blocking tone scheduler."""
        if not self.is_playing:
            return

        if now_ms >= self.note_end_ms:
            self.melody_index += 1
            if self.melody_index < len(self.current_melody):
                freq, dur = self.current_melody[self.melody_index]
                self.active_freq = freq
                self.note_end_ms = now_ms + dur
            else:
                self.stop()


# ==============================================================================
# 5. TRIGGER DEBOUNCE & RATE LIMITER MODEL
# ==============================================================================

class TriggerEngine:
    """
    Single tactile trigger on GPIO 13 with 40ms software debounce
    and 600ms non-blocking rate limiter.
    """
    DEBOUNCE_MS = 40
    COOLDOWN_MS = 600

    def __init__(self):
        self.pin_state = 1  # 1=HIGH (released with INPUT_PULLUP), 0=LOW (pressed)
        self.debounced_state = 1
        self.last_debounce_time = 0
        self.last_fire_time = -self.COOLDOWN_MS
        self.shots_fired = 0

    def feed_pin_sample(self, raw_pin_val: int, now_ms: int) -> bool:
        """
        Feeds a raw digitalRead sample. Returns True if a valid shot is triggered.
        """
        shot_triggered = False

        if raw_pin_val != self.pin_state:
            self.last_debounce_time = now_ms
            self.pin_state = raw_pin_val

        if (now_ms - self.last_debounce_time) >= self.DEBOUNCE_MS:
            if self.pin_state != self.debounced_state:
                self.debounced_state = self.pin_state
                # Check for falling edge (press)
                if self.debounced_state == 0:
                    if (now_ms - self.last_fire_time) >= self.COOLDOWN_MS:
                        self.last_fire_time = now_ms
                        self.shots_fired += 1
                        shot_triggered = True

        return shot_triggered


# ==============================================================================
# 6. STANDALONE FALLBACK REFEREE MODEL
# ==============================================================================

class StandaloneReferee:
    """
    Autonomous internal referee for offline operation (backyard skirmish).
    5 HP, 3 Lives, 10s respawn, 3s protection shield, 3s hit cooldown.
    """
    def __init__(self, max_hp: int = 5, max_lives: int = 3):
        self.max_hp = max_hp
        self.max_lives = max_lives
        self.hp = max_hp
        self.lives = max_lives
        self.state = "ALIVE"  # ALIVE | RESPAWN | OUT
        self.protect_until = 0
        self.cooldown_until = 0
        self.respawn_at = 0
        self.hits_taken = 0
        self.deaths = 0

    def process_hit(self, code: int, now_ms: int) -> Dict[str, Any]:
        """Processes incoming IR code and updates health, lives, and timing."""
        player_info = NECProtocol.lookup_code(code)
        if not player_info:
            return {"ev": "IGNORED", "hp": self.hp, "lives": self.lives, "state": self.state}

        if self.state == "OUT":
            return {"ev": "NOTALIVE", "hp": self.hp, "lives": self.lives, "state": self.state}

        if self.state == "RESPAWN":
            if now_ms >= self.respawn_at:
                self.state = "ALIVE"
                self.hp = self.max_hp
                self.protect_until = now_ms + 3000
            else:
                return {"ev": "NOTALIVE", "hp": self.hp, "lives": self.lives, "state": self.state}

        team = player_info["team"]

        # 1. Friendly medic heal
        if team == "FRIEND":
            if self.hp >= self.max_hp:
                return {"ev": "FULL", "hp": self.hp, "lives": self.lives, "state": self.state}
            self.hp = min(self.max_hp, self.hp + 1)
            return {"ev": "HEAL", "hp": self.hp, "lives": self.lives, "state": self.state}

        # 2. Enemy hit
        if now_ms < self.protect_until:
            return {"ev": "BLOCKED", "hp": self.hp, "lives": self.lives, "state": self.state}

        if now_ms < self.cooldown_until:
            return {"ev": "COOLDOWN", "hp": self.hp, "lives": self.lives, "state": self.state}

        self.hp = max(0, self.hp - 1)
        self.hits_taken += 1
        self.cooldown_until = now_ms + 3000

        if self.hp > 0:
            return {"ev": "HIT", "hp": self.hp, "lives": self.lives, "state": self.state}

        # Life lost
        self.lives -= 1
        self.deaths += 1
        if self.lives <= 0:
            self.state = "OUT"
            return {"ev": "ELIM", "hp": 0, "lives": 0, "state": "OUT"}

        self.state = "RESPAWN"
        self.respawn_at = now_ms + 10000
        return {"ev": "DEATH", "hp": 0, "lives": self.lives, "state": "RESPAWN"}

    def update(self, now_ms: int):
        """Ticks standalone state (e.g. completes respawn)."""
        if self.state == "RESPAWN" and now_ms >= self.respawn_at:
            self.state = "ALIVE"
            self.hp = self.max_hp
            self.protect_until = now_ms + 3000
