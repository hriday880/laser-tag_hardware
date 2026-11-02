#!/usr/bin/env python3
"""
LASER TAG CENTRAL SERVER - MARK FX (8 VESTS)
Zero external dependencies (Python standard library only).

  - Authoritative referee: match phases, HP, lives, respawn, scoring
  - Fun rules: Medic friends, Traitors, First Blood, Finisher bonus
  - Web dashboard at http://<IP>:5050/
  - UDP auto-discovery broadcast (ESP32 finds this server by itself)
  - Match history saved to matches.json
  - Per-vest state: HP, lives, team, sensor/blaster health, hidden failsafe
  - Failsafe activity logged to failsafe.log (one JSON object per line)

Still compatible with Mark 3 firmware (/hit and /status).
"""
import json
import os
import re
import secrets
import socket
import subprocess
import threading
import time
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

HTTP_PORT = 5050
DISCOVERY_PORT = 5051
NODE_TIMEOUT_S = 3.5

HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(HERE, "matches.json")
DASHBOARD_FILE = os.path.join(HERE, "dashboard.html")
FAILSAFE_LOG_FILE = os.path.join(HERE, "failsafe.log")
BUZZER_FILE = os.path.join(HERE, "buzzers.json")
REFEREE_KEY_FILE = os.path.join(HERE, "referee_key.txt")
MATCH_STATE_FILE = os.path.join(HERE, "match_state.json")
REFEREE_KEY = None  # Set in main()

# ==========================================
#      PLAYERS (P1-P4 Blue, P5-P8 Red)
# ==========================================
SHOOTERS = {
    "0xFF30CF": ("P1", "BLUE"),
    "0xFF18E7": ("P2", "BLUE"),
    "0xFF7A85": ("P3", "BLUE"),
    "0xFF10EF": ("P4", "BLUE"),
    "0xFF38C7": ("P5", "RED"),
    "0xFF5AA5": ("P6", "RED"),
    "0xFF42BD": ("P7", "RED"),
    "0xFF4AB5": ("P8", "RED"),
}

DEFAULT_SETTINGS = {
    "max_hp": 5,
    "max_lives": 3,
    "respawn_s": 10,
    "protect_s": 3,
    "match_s": 300,
    "cooldown_s": 3,
    "disarm_s": 10,
    "medic_cooldown_s": 20,
    "traitor_strikes": 3,
}
SETTING_LIMITS = {
    "max_hp": (1, 20),
    "max_lives": (1, 10),
    "respawn_s": (0, 60),
    "protect_s": (0, 30),
    "match_s": (30, 3600),
    "cooldown_s": (0, 10),
    "disarm_s": (0, 60),
    "medic_cooldown_s": (0, 120),
    "traitor_strikes": (1, 10),
}

# Scoring
PTS_HIT = 10
PTS_KILL = 50
PTS_FINISHER = 100
PTS_FIRST_BLOOD = 25
PTS_HEAL = 5
PTS_STRIKE = -10

COUNTDOWN_S = 3

REFEREE_ONLY_VEST_FIELDS = ("sensors", "blaster", "assist_active", "assist_manual",
                            "assist_hits", "assist_misses", "assist_doubles", "assist_not_target", "radio",
                            "buzzer", "buzzer_device")


def normalize_code(code):
    code = str(code).strip().upper()
    if code.startswith("0X"):
        code = "0x" + code[2:]
    return code


def load_history():
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(history):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"[WARN] Could not save match history: {e}")


def load_referee_key():
    """Secret for the referee page. Never printed, because the terminal may be on a public screen."""
    try:
        with open(REFEREE_KEY_FILE, "r") as f:
            key = f.read().strip()
            if key:
                return key
    except OSError:
        pass
    key = secrets.token_urlsafe(12)
    fd = os.open(REFEREE_KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key)
    return key


def is_referee_key(key):
    return bool(REFEREE_KEY) and isinstance(key, str) and secrets.compare_digest(key.encode(), REFEREE_KEY.encode())


def load_buzzers():
    try:
        with open(BUZZER_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_buzzers(buzzers):
    try:
        with open(BUZZER_FILE, "w") as f:
            json.dump(buzzers, f, indent=2)
    except OSError as e:
        print(f"[WARN] Could not save buzzer types: {e}")


def failsafe_log(event):
    event = {"t": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), **event}
    try:
        with open(FAILSAFE_LOG_FILE, "a") as f:
            f.write(json.dumps(event) + "\n")
    except OSError as e:
        print(f"[WARN] Could not write failsafe log: {e}")


def get_network_info():
    """Returns (list of local IPs, list of broadcast addresses) using ifconfig."""
    ips, bcasts = [], []
    try:
        out = subprocess.check_output(["ifconfig"], stderr=subprocess.DEVNULL).decode("utf-8", "ignore")
        for m in re.finditer(r"inet (\d+\.\d+\.\d+\.\d+)[^\n]*", out):
            ip = m.group(1)
            if ip.startswith("127."):
                continue
            ips.append(ip)
            b = re.search(r"broadcast (\d+\.\d+\.\d+\.\d+)", m.group(0))
            if b:
                bcasts.append(b.group(1))
    except Exception:
        pass
    return ips, bcasts


def ms(seconds):
    return max(0, int(seconds * 1000))


# ==========================================
#              GAME REFEREE
# ==========================================
class Vest:
    """One player's gun + vest: match state plus device health."""

    def __init__(self, vest_id, team):
        self.id = vest_id
        self.team = team
        self.ip = None
        self.rssi = None
        self.last_seen = 0.0
        self.sensors = "UNKNOWN"  # OK | STUCK_LOW | OPEN
        self.blaster = "UNKNOWN"  # OK | OPEN
        self.assist_active = False  # failsafe currently running on the device
        self.assist_manual = False  # referee forced the failsafe on
        self.assist_hits = 0
        self.assist_misses = 0
        self.assist_doubles = 0
        self.assist_not_target = 0
        self.radio = "UNKNOWN"  # OK | FAILED (ESP-NOW link on the gun)
        self.sync_boot = None
        self.sync_last_id = 0
        self.buzzer = None  # None (not assigned) | PASSIVE | ACTIVE
        self.buzzer_device = None  # What the gun last reported running
        self.joined = False
        self.new_match(5, 3)

    def new_match(self, max_hp, max_lives):
        self.hp = max_hp
        self.lives = max_lives
        self.pstate = "ALIVE"  # ALIVE | RESPAWN | OUT
        self.respawn_at = 0.0
        self.protect_until = 0.0
        self.cooldown_until = 0.0
        self.disarm_until = 0.0
        self.hits_taken = 0
        self.deaths = 0
        self.heals = 0
        self.last_attacker = "None"

    def online(self):
        return (time.time() - self.last_seen) < NODE_TIMEOUT_S


class Game:
    def __init__(self):
        self.lock = threading.RLock()
        self.settings = dict(DEFAULT_SETTINGS)
        self.vests = {name: Vest(name, team) for name, team in SHOOTERS.values()}
        for vest_id, kind in load_buzzers().items():
            if vest_id in self.vests and kind in ("PASSIVE", "ACTIVE"):
                self.vests[vest_id].buzzer = kind
        self.history = load_history()
        self.version = 0  # bumps on every state change (for terminal redraws)
        self.reset()

    # ---------- helpers ----------
    def clock(self):
        """Frozen while paused, so all countdowns stop."""
        return self.paused_at if self.phase == "PAUSED" else time.time()

    def log(self, src, msg, kind="info", referee_only=False, note=""):
        self.feed.insert(0, {"t": datetime.now().strftime("%H:%M:%S"), "src": src, "msg": msg, "kind": kind,
                             "referee_only": referee_only, "note": note})
        del self.feed[40:]
        self.version += 1

    # ---------- admin controls ----------
    def reset(self):
        with self.lock:
            s = self.settings
            self.match_id = 0
            self.phase = "LOBBY"
            self.paused_at = 0.0
            self.paused_from = "LIVE"
            self.countdown_end = 0.0
            self.match_started_at = 0.0
            self.match_end = 0.0
            for v in self.vests.values():
                v.new_match(s["max_hp"], s["max_lives"])
                v.joined = v.online()
            self.first_blood_done = False
            self.result = ""
            self.winner = None
            self.mvp = ""
            self.stats = {
                name: {"name": name, "team": team, "hits": 0, "kills": 0, "heals": 0,
                       "strikes": 0, "score": 0, "traitor": False, "medic_ready_at": 0.0}
                for name, team in SHOOTERS.values()
            }
            self.feed = []
            self.log("SYSTEM", "Arena reset. Waiting in LOBBY.")

    def start(self):
        with self.lock:
            if self.phase in ("COUNTDOWN", "LIVE", "PAUSED"):
                return False
            if self.phase == "GAMEOVER":
                self.reset()
            self.match_id = int(time.time()) % 1000000000
            self.phase = "COUNTDOWN"
            self.countdown_end = time.time() + COUNTDOWN_S
            self.log("SYSTEM", f"Match starting in {COUNTDOWN_S}...", "system")
            for v in self.vests.values():
                v.joined = v.online()
                if not v.joined:
                    continue
                if v.sensors not in ("OK", "UNKNOWN") or v.blaster not in ("OK", "UNKNOWN") or v.assist_active:
                    msg = f"Pre-match check: sensors {v.sensors}, blaster {v.blaster}, failsafe {'ON' if v.assist_active else 'off'}"
                    self.log(v.id, msg, "warn", referee_only=True)
                    failsafe_log({"vest": v.id, "event": "PREMATCH_FAULT", "sensors": v.sensors,
                                  "blaster": v.blaster, "assist": v.assist_active})
            return True

    def pause(self):
        with self.lock:
            if self.phase not in ("LIVE", "COUNTDOWN"):
                return False
            self.paused_from = self.phase
            self.paused_at = time.time()
            self.phase = "PAUSED"
            self.log("SYSTEM", "Match PAUSED", "system")
            return True

    def resume(self):
        with self.lock:
            if self.phase != "PAUSED":
                return False
            d = time.time() - self.paused_at
            self.countdown_end += d
            self.match_end += d
            for v in self.vests.values():
                v.respawn_at += d
                v.protect_until += d
                v.cooldown_until += d
                v.disarm_until += d
            for st in self.stats.values():
                st["medic_ready_at"] += d
            self.phase = self.paused_from
            self.paused_at = 0.0
            self.log("SYSTEM", "Match RESUMED", "system")
            return True

    def end(self):
        with self.lock:
            if self.phase not in ("LIVE", "PAUSED", "COUNTDOWN"):
                return False
            self.finish("ENDED")
            return True

    def apply_settings(self, new):
        with self.lock:
            changed = []
            for k, v in (new or {}).items():
                if k not in SETTING_LIMITS:
                    continue
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    continue
                lo, hi = SETTING_LIMITS[k]
                v = max(lo, min(hi, v))
                if self.settings[k] != v:
                    self.settings[k] = v
                    changed.append(f"{k}={v}")
            if changed:
                self.log("SYSTEM", "Settings: " + ", ".join(changed), "system")
                if self.phase == "LOBBY":
                    for vest in self.vests.values():
                        vest.hp = self.settings["max_hp"]
                        vest.lives = self.settings["max_lives"]
            return changed

    def set_manual_assist(self, vest_id, on):
        with self.lock:
            v = self.vests.get(vest_id)
            if not v:
                return False
            v.assist_manual = bool(on)
            self.log(v.id, f"Referee turned failsafe {'ON' if on else 'off'}", "warn", referee_only=True)
            failsafe_log({"vest": v.id, "event": "REFEREE_ASSIST", "on": bool(on)})
            return True

    def set_buzzer(self, vest_id, kind):
        with self.lock:
            v = self.vests.get(vest_id)
            if not v or kind not in ("PASSIVE", "ACTIVE"):
                return False
            v.buzzer = kind
            save_buzzers({x.id: x.buzzer for x in self.vests.values() if x.buzzer})
            self.log(v.id, f"Buzzer assigned: {kind}", "system", referee_only=True)
            return True

    # ---------- device reports ----------
    def touch_vest(self, vest_id, ip, data):
        """Records a heartbeat/hit from a device and logs any failsafe activity it reports."""
        with self.lock:
            v = self.vests.get(vest_id)
            if not v:
                return None
            was_online = v.online()
            if was_online and v.ip and v.ip != ip:
                self.log(v.id, f"DUPLICATE ID? {v.id} heard from {v.ip} and {ip}", "bad", referee_only=True)
                failsafe_log({"vest": v.id, "event": "DUPLICATE_ID", "ips": [v.ip, ip]})
            v.ip = ip
            if "rssi" in data:
                v.rssi = data.get("rssi")
            v.last_seen = time.time()
            v.joined = True
            if not was_online:
                self.log("NETWORK", f"Vest {v.id} connected from {ip}", "system")

            if "bz" in data:
                v.buzzer_device = "ACTIVE" if data.get("bz") else "PASSIVE"

            if "en" in data:
                radio = "OK" if data.get("en") else "FAILED"
                if radio != v.radio and (radio != "OK" or v.radio != "UNKNOWN"):
                    self.log(v.id, f"Failsafe radio {v.radio} -> {radio}", "warn" if radio != "OK" else "good", referee_only=True)
                    failsafe_log({"vest": v.id, "event": "RADIO_STATE", "from": v.radio, "to": radio})
                v.radio = radio

            sensors = data.get("s")
            if sensors and sensors != v.sensors:
                if sensors != "OK" or v.sensors != "UNKNOWN":
                    self.log(v.id, f"Sensor bus {v.sensors} -> {sensors}", "warn" if sensors != "OK" else "good", referee_only=True)
                    failsafe_log({"vest": v.id, "event": "SENSOR_STATE", "from": v.sensors, "to": sensors})
                v.sensors = sensors
            blaster = data.get("b")
            if blaster and blaster != v.blaster:
                if blaster != "OK" or v.blaster != "UNKNOWN":
                    self.log(v.id, f"Blaster {v.blaster} -> {blaster}", "warn" if blaster != "OK" else "good", referee_only=True)
                    failsafe_log({"vest": v.id, "event": "BLASTER_STATE", "from": v.blaster, "to": blaster})
                v.blaster = blaster
            if "a" in data:
                active = bool(data.get("a"))
                if active != v.assist_active:
                    self.log(v.id, f"Failsafe {'TOOK OVER' if active else 'released'}", "warn", referee_only=True)
                    failsafe_log({"vest": v.id, "event": "ASSIST_ACTIVE", "on": active, "sensors": v.sensors})
                    v.assist_active = active

            doubles = data.get("ad")
            if isinstance(doubles, int):
                if doubles > v.assist_doubles:
                    pair = data.get("dp", "?")
                    self.log(v.id, f"Double hit from {pair}: both ignored", "warn", referee_only=True)
                    failsafe_log({"vest": v.id, "event": "DOUBLE_HIT_IGNORED", "shooters": pair,
                                  "total": doubles})
                v.assist_doubles = doubles
            misses = data.get("am")
            if isinstance(misses, int):
                if misses > v.assist_misses:
                    failsafe_log({"vest": v.id, "event": "ASSIST_MISS_ROLLS",
                                  "new": misses - v.assist_misses, "total": misses})
                v.assist_misses = misses
            not_target = data.get("an")
            if isinstance(not_target, int):
                if not_target > v.assist_not_target:
                    failsafe_log({"vest": v.id, "event": "ASSIST_NOT_TARGET",
                                  "new": not_target - v.assist_not_target, "total": not_target})
                v.assist_not_target = not_target
            if isinstance(data.get("ah"), int):
                v.assist_hits = data["ah"]
            return v

    def sync_offline(self, vest_id, data):
        """Replays what a gun recorded while offline, then takes its final HP, lives and timers."""
        with self.lock:
            self.tick()
            v = self.vests.get(vest_id)
            if not v:
                return False
            events = data.get("ev") if isinstance(data.get("ev"), list) else []
            if data.get("mid") != self.match_id or self.phase not in ("LIVE", "PAUSED"):
                self.log(v.id, f"Offline events from a finished match not applied ({len(events)})", "warn", referee_only=True)
                failsafe_log({"vest": v.id, "event": "OFFLINE_SYNC_DISCARDED", "mid": data.get("mid"), "events": events})
                return True

            if v.sync_boot != data.get("boot"):
                v.sync_boot = data.get("boot")
                v.sync_last_id = 0
            s = self.settings
            shooters = list(SHOOTERS.values())
            applied = 0
            for ev in events:
                try:
                    ev_id, kind, shooter, assist = ev
                    name = shooters[shooter][0]
                except (TypeError, ValueError, IndexError):
                    continue
                if ev_id <= v.sync_last_id:
                    continue  # Already applied; the gun never got our reply
                v.sync_last_id = ev_id
                st = self.stats[name]
                applied += 1
                if kind == "H":
                    v.hp = min(s["max_hp"], v.hp + 1)
                    v.heals += 1
                    st["heals"] += 1
                    st["score"] += PTS_HEAL
                elif kind == "D":
                    v.hits_taken += 1
                    v.last_attacker = name
                    st["hits"] += 1
                    st["score"] += PTS_HIT
                    if not self.first_blood_done:
                        self.first_blood_done = True
                        st["score"] += PTS_FIRST_BLOOD
                    v.hp = max(0, v.hp - 1)
                    if v.hp == 0:
                        v.deaths += 1
                        st["kills"] += 1
                        st["score"] += PTS_KILL
                        v.lives = max(0, v.lives - 1)
                        if v.lives == 0:
                            st["score"] += PTS_FINISHER
                        else:
                            v.hp = s["max_hp"]
                failsafe_log({"vest": v.id, "event": "OFFLINE_EVENT", "kind": kind, "shooter": name, "assist": bool(assist)})

            now = self.clock()
            final_ms = lambda key: max(0, int(data.get(key) or 0)) / 1000.0
            v.hp = max(0, min(s["max_hp"], int(data.get("hp", v.hp))))
            v.lives = max(0, min(s["max_lives"], int(data.get("lv", v.lives))))
            if data.get("st") in ("ALIVE", "RESPAWN", "OUT"):
                v.pstate = data["st"]
            v.respawn_at = now + final_ms("rs")
            v.protect_until = now + final_ms("pr")
            v.cooldown_until = now + final_ms("cd")
            v.disarm_until = now + final_ms("ds")
            self.log("NETWORK", f"Vest {v.id} back online, {applied} offline events synced", "system")
            if v.pstate == "OUT":
                self.check_elimination()
            return True

    # ---------- crash recovery ----------
    SNAPSHOT_VEST_FIELDS = ("hp", "lives", "pstate", "respawn_at", "protect_until", "cooldown_until", "disarm_until", "hits_taken",
                            "deaths", "heals", "last_attacker", "joined", "assist_manual", "sync_boot", "sync_last_id")
    SNAPSHOT_GAME_FIELDS = ("match_id", "phase", "paused_at", "paused_from", "countdown_end", "match_started_at",
                            "match_end", "first_blood_done", "stats", "feed")

    def save_snapshot(self):
        with self.lock:
            if self.phase not in ("COUNTDOWN", "LIVE", "PAUSED"):
                try:
                    os.remove(MATCH_STATE_FILE)
                except OSError:
                    pass
                return
            snap = {k: getattr(self, k) for k in self.SNAPSHOT_GAME_FIELDS}
            snap["settings"] = self.settings
            snap["vests"] = {v.id: {k: getattr(v, k) for k in self.SNAPSHOT_VEST_FIELDS} for v in self.vests.values()}
            tmp = MATCH_STATE_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(snap, f)
            os.replace(tmp, MATCH_STATE_FILE)

    def restore_snapshot(self):
        """Resumes a match after a server crash or restart. Its clock kept running meanwhile."""
        try:
            with open(MATCH_STATE_FILE, "r") as f:
                snap = json.load(f)
        except (OSError, ValueError):
            return False
        with self.lock:
            for k in self.SNAPSHOT_GAME_FIELDS:
                setattr(self, k, snap[k])
            self.settings.update(snap["settings"])
            for vest_id, fields in snap["vests"].items():
                for k, value in fields.items():
                    setattr(self.vests[vest_id], k, value)
            self.log("SYSTEM", "Server restarted: match resumed", "system")
            return True

    # ---------- game clock ----------
    def tick(self):
        with self.lock:
            now = time.time()
            if self.phase == "COUNTDOWN" and now >= self.countdown_end:
                self.phase = "LIVE"
                self.match_started_at = now
                self.match_end = now + self.settings["match_s"]
                self.log("SYSTEM", "MATCH IS LIVE! Fight!", "system")
            if self.phase == "LIVE":
                for v in self.vests.values():
                    if v.pstate == "RESPAWN" and now >= v.respawn_at:
                        v.pstate = "ALIVE"
                        v.hp = self.settings["max_hp"]
                        v.protect_until = now + self.settings["protect_s"]
                        self.log(v.id, f"Respawned with {v.hp} HP ({v.lives} lives left)", "good")
                if now >= self.match_end:
                    self.finish("TIME")

    def team_totals(self, team):
        vests = [v for v in self.vests.values() if v.team == team and v.joined]
        lives = sum(v.lives for v in vests)
        score = sum(st["score"] for st in self.stats.values() if st["team"] == team)
        return vests, lives, score

    def check_elimination(self):
        """Ends the match once every joined vest of a team is OUT."""
        for team, other in (("BLUE", "RED"), ("RED", "BLUE")):
            vests, _, _ = self.team_totals(team)
            if vests and all(v.pstate == "OUT" for v in vests):
                others, _, _ = self.team_totals(other)
                self.winner = other if others else None
                self.finish("ELIMINATED")
                return True
        return False

    def finish(self, reason):
        self.phase = "GAMEOVER"
        self.paused_at = 0.0
        ranked = sorted(self.stats.values(), key=lambda s: s["score"], reverse=True)
        top = ranked[0] if ranked and ranked[0]["score"] > 0 else None
        self.mvp = top["name"] if top else "Nobody"
        if reason == "TIME":
            blue, blue_lives, blue_score = self.team_totals("BLUE")
            red, red_lives, red_score = self.team_totals("RED")
            if blue and red:
                blue_key, red_key = (blue_lives, blue_score), (red_lives, red_score)
                self.winner = "BLUE" if blue_key > red_key else "RED" if red_key > blue_key else None
                self.result = f"{self.winner} WINS" if self.winner else "DRAW"
            else:
                self.result = "YOU SURVIVED!"
            self.log("SYSTEM", f"Time up! {self.result} MVP: {self.mvp}", "system")
        elif reason == "ELIMINATED":
            self.result = f"{self.winner} WINS" if self.winner else "ELIMINATED"
            self.log("SYSTEM", f"Team eliminated! {self.result} MVP: {self.mvp}", "system")
        else:
            self.result = "MATCH ENDED"
            self.log("SYSTEM", f"Match ended by admin. MVP: {self.mvp}", "system")

        played = (time.time() - self.match_started_at) if self.match_started_at else 0
        self.history.insert(0, {
            "ended_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "result": self.result,
            "duration_s": int(played),
            "hits_taken": sum(v.hits_taken for v in self.vests.values()),
            "deaths": sum(v.deaths for v in self.vests.values()),
            "heals": sum(v.heals for v in self.vests.values()),
            "mvp": self.mvp,
            "scoreboard": [{k: s[k] for k in ("name", "team", "hits", "kills", "heals", "strikes", "score", "traitor")}
                           for s in ranked],
        })
        del self.history[50:]
        save_history(self.history)

    # ---------- hits ----------
    def process_hit(self, raw_code, victim_id="P1", assist=False):
        """Returns an event dict: ev, attacker, l1, l2 (LCD lines, max 16 chars, no commas)."""
        with self.lock:
            self.tick()
            code = normalize_code(raw_code)
            info = SHOOTERS.get(code)
            v = self.vests.get(victim_id)
            if not info or not v:
                self.log("SENSOR", f"Unknown IR code {code} on {victim_id} ignored", "dim")
                return {"ev": "IGNORED", "attacker": "", "l1": "", "l2": ""}

            name, team = info
            st = self.stats[name]
            v.joined = True

            if name == v.id:
                return {"ev": "IGNORED", "attacker": name, "l1": "", "l2": ""}
            if self.phase != "LIVE":
                return {"ev": "NOTLIVE", "attacker": name, "l1": "MATCH NOT LIVE", "l2": f"Phase: {self.phase}"}
            if v.pstate != "ALIVE":
                return {"ev": "NOTALIVE", "attacker": name, "l1": "", "l2": ""}

            now = time.time()
            s = self.settings

            # ---- SAME TEAM (medic) ----
            if team == v.team and not st["traitor"]:
                if now < st["medic_ready_at"]:
                    st["strikes"] += 1
                    st["score"] += PTS_STRIKE
                    if st["strikes"] >= s["traitor_strikes"]:
                        st["traitor"] = True
                        self.log(name, f"TURNED TRAITOR after {st['strikes']} friendly-fire strikes!", "bad")
                        return {"ev": "TRAITOR", "attacker": name, "l1": "!! TRAITOR !!", "l2": f"{name} defected"}
                    left = s["traitor_strikes"] - st["strikes"]
                    self.log(name, f"Friendly fire on {v.id}! Strike {st['strikes']} ({left} until TRAITOR)", "warn")
                    return {"ev": "FF", "attacker": name, "l1": "FRIENDLY FIRE!", "l2": f"{name} strike {st['strikes']}"}

                if v.hp >= s["max_hp"]:
                    self.log(name, f"Medic beam wasted - {v.id} HP already full", "dim")
                    return {"ev": "FULL", "attacker": name, "l1": "HP ALREADY FULL", "l2": f"Medic: {name}"}

                v.hp += 1
                v.heals += 1
                st["heals"] += 1
                st["score"] += PTS_HEAL
                st["medic_ready_at"] = now + s["medic_cooldown_s"]
                self.log(name, f"MEDIC healed {v.id} +1 HP (HP {v.hp}/{s['max_hp']})", "good",
                         note=" [FAILSAFE]" if assist else "")
                if assist:
                    failsafe_log({"vest": v.id, "event": "ASSIST_HEAL", "shooter": name, "hp": v.hp})
                return {"ev": "HEAL", "attacker": name, "l1": "+1 HP  MEDIC", "l2": f"By: {name}"}

            # ---- ENEMY (or traitor) ----
            label = f"{name} (T)" if st["traitor"] else name
            if now < v.protect_until:
                self.log(label, f"Shot on {v.id} blocked by spawn shield", "dim")
                return {"ev": "BLOCKED", "attacker": label, "l1": "SPAWN SHIELD", "l2": "Shot blocked!"}
            if now < v.cooldown_until:
                return {"ev": "COOLDOWN", "attacker": label, "l1": "", "l2": ""}

            v.hp = max(0, v.hp - 1)
            v.hits_taken += 1
            v.cooldown_until = now + s["cooldown_s"]
            v.disarm_until = now + s["disarm_s"]
            v.last_attacker = label
            st["hits"] += 1
            st["score"] += PTS_HIT
            how = " [FAILSAFE]" if assist else ""
            if assist:
                failsafe_log({"vest": v.id, "event": "ASSIST_HIT", "shooter": name, "hp": v.hp, "lives": v.lives})

            if not self.first_blood_done:
                self.first_blood_done = True
                st["score"] += PTS_FIRST_BLOOD
                self.log(label, f"FIRST BLOOD! (+{PTS_FIRST_BLOOD} bonus)", "bad")

            if v.hp > 0:
                self.log(label, f"Hit {v.id} -1 HP (HP {v.hp}/{s['max_hp']})", "bad", note=how)
                return {"ev": "HIT", "attacker": label, "l1": f"HIT! -1 HP  {v.hp}/{s['max_hp']}", "l2": f"By: {label}"}

            # life lost
            v.lives -= 1
            v.deaths += 1
            st["kills"] += 1
            st["score"] += PTS_KILL
            if v.lives <= 0:
                st["score"] += PTS_FINISHER
                v.pstate = "OUT"
                self.log(label, f"FINISHER! Eliminated {v.id} (+{PTS_FINISHER})", "bad", note=how)
                self.check_elimination()
                return {"ev": "ELIM", "attacker": label, "l1": "== ELIMINATED ==", "l2": f"By: {label}"}

            v.pstate = "RESPAWN"
            v.respawn_at = now + s["respawn_s"]
            self.log(label, f"KILLED {v.id}! {v.lives} lives left", "bad", note=how)
            return {"ev": "DEATH", "attacker": label, "l1": "=== KILLED! ===", "l2": f"By: {label}"}

    # ---------- views ----------
    def device_state(self, vest_id="P1"):
        """Flat JSON for the ESP32 (short keys, ASCII only, no commas in strings)."""
        with self.lock:
            self.tick()
            now = self.clock()
            s = self.settings
            v = self.vests[vest_id]
            ph = self.phase
            shown_phase = self.paused_from if ph == "PAUSED" else ph
            if shown_phase == "COUNTDOWN":
                tm = ms(self.countdown_end - now)
            elif shown_phase == "LIVE":
                tm = ms(self.match_end - now)
            elif ph == "LOBBY":
                tm = s["match_s"] * 1000
            else:
                tm = 0
            res = self.result
            if self.winner:
                res = "WIN" if v.team == self.winner else "LOSE"
            state = {
                "ph": ph,
                "st": v.pstate,
                "hp": v.hp, "mhp": s["max_hp"],
                "lv": v.lives, "mlv": s["max_lives"],
                "tm": tm,
                "rs": ms(v.respawn_at - now) if v.pstate == "RESPAWN" else 0,
                "pr": ms(v.protect_until - now),
                "cd": ms(v.cooldown_until - now),
                "ds": ms(v.disarm_until - now),
                "last": v.last_attacker,
                "ht": v.hits_taken,
                "dt": v.deaths,
                "res": res,
                "mvp": self.mvp,
                "ast": 1 if v.assist_manual else 0,
                "mid": self.match_id,
                "srs": s["respawn_s"], "spr": s["protect_s"], "scd": s["cooldown_s"], "smd": s["medic_cooldown_s"],
                "sds": s["disarm_s"],
            }
            if v.buzzer:
                state["bz"] = 1 if v.buzzer == "ACTIVE" else 0
            return state

    def vest_rows(self):
        rows = []
        for v in self.vests.values():
            d = self.device_state(v.id)
            rows.append({
                "id": v.id, "team": v.team, "online": v.online(), "joined": v.joined,
                "ip": v.ip, "rssi": v.rssi,
                "last_seen_s": round(time.time() - v.last_seen, 1) if v.last_seen else None,
                "hp": d["hp"], "mhp": d["mhp"], "lv": d["lv"], "mlv": d["mlv"], "st": d["st"],
                "rs": d["rs"], "pr": d["pr"],
                "sensors": v.sensors, "blaster": v.blaster,
                "assist_active": v.assist_active, "assist_manual": v.assist_manual,
                "assist_hits": v.assist_hits, "assist_misses": v.assist_misses,
                "assist_doubles": v.assist_doubles, "assist_not_target": v.assist_not_target,
                "radio": v.radio,
                "buzzer": v.buzzer, "buzzer_device": v.buzzer_device,
            })
        return rows

    def full_state(self, referee=False):
        """Rich JSON for the web dashboard. Failsafe and fault details only go to the referee view."""
        with self.lock:
            dev = self.device_state()
            dev["res"] = self.result
            ranked = sorted(self.stats.values(), key=lambda s: s["score"], reverse=True)
            now = self.clock()
            board = []
            for st in ranked:
                row = {k: st[k] for k in ("name", "team", "hits", "kills", "heals", "strikes", "score", "traitor")}
                row["medic_ready_in"] = round(max(0, st["medic_ready_at"] - now), 1)
                board.append(row)
            vests = self.vest_rows()
            feed = self.feed
            if not referee:
                for row in vests:
                    for key in REFEREE_ONLY_VEST_FIELDS:
                        del row[key]
                feed = [{**e, "note": ""} for e in feed if not e["referee_only"]]
            return {
                "referee": referee,
                "device": dev,
                "settings": self.settings,
                "limits": SETTING_LIMITS,
                "vests": vests,
                "stats": {
                    "hits_taken": sum(v.hits_taken for v in self.vests.values()),
                    "deaths": sum(v.deaths for v in self.vests.values()),
                    "heals": sum(v.heals for v in self.vests.values()),
                },
                "leaderboard": board,
                "feed": feed,
                "history": self.history[:10],
                "server_ips": get_network_info()[0],
            }


game = Game()


# ==========================================
#          UDP AUTO-DISCOVERY
# ==========================================
def discovery_broadcaster():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    msg = f"LASERTAG {HTTP_PORT}".encode()
    targets, last_refresh = [], 0
    while True:
        if time.time() - last_refresh > 10:
            _, bcasts = get_network_info()
            targets = list(dict.fromkeys(bcasts + ["255.255.255.255"]))
            last_refresh = time.time()
        for t in targets:
            try:
                sock.sendto(msg, (t, DISCOVERY_PORT))
            except OSError:
                pass
        time.sleep(1)


# ==========================================
#          TERMINAL DASHBOARD
# ==========================================
def render_terminal():
    st = game.full_state()
    d = st["device"]
    secs = d["tm"] // 1000
    ips = st["server_ips"]
    lines = [
        "\033[2J\033[H",
        "==================================================================",
        "          LASER TAG CENTRAL REFEREE - MARK FX ARENA",
        "==================================================================",
        f" PHASE  : {d['ph']:<10}  TIMER: {secs // 60:02d}:{secs % 60:02d}",
        "------------------------------------------------------------------",
    ]
    for v in st["vests"]:
        if not v["online"] and not v["joined"]:
            continue
        hearts = "█" * v["hp"] + "░" * max(0, v["mhp"] - v["hp"])
        link = "ON " if v["online"] else "OFF"
        lines.append(f" {v['id']} {v['team']:<4} {link} [{hearts}] L{v['lv']} {v['st']}")
    lines.append("------------------------------------------------------------------")
    lines.append(" EVENT LOG:")
    for e in st["feed"][:8]:
        lines.append(f"  [{e['t']}] {e['src']:<12} : {e['msg']}")
    lines.append("------------------------------------------------------------------")
    for ip in ips:
        lines.append(f" Dashboard : http://{ip}:{HTTP_PORT}/   (open on laptop or phone)")
    if not ips:
        lines.append(f" Dashboard : http://127.0.0.1:{HTTP_PORT}/")
    lines.append(" ESP32 finds this server automatically (UDP discovery).")
    lines.append("==================================================================")
    print("\n".join(lines), flush=True)


def terminal_loop():
    last_sig = None
    while True:
        st = game.device_state()
        vests = tuple((v.hp, v.lives, v.pstate, v.online())
                      for v in game.vests.values())
        sig = (game.version, st["ph"], st["tm"] // 1000, vests)
        if sig != last_sig:
            last_sig = sig
            render_terminal()
        time.sleep(0.25)


# ==========================================
#              HTTP HANDLER
# ==========================================
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception:
            return None

    def _touch_node(self, data):
        return game.touch_vest(data.get("node_id", "P1"), self.client_address[0], data)

    def _is_referee(self):
        return is_referee_key(parse_qs(urlparse(self.path).query).get("key", [""])[0])

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            try:
                with open(DASHBOARD_FILE, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, "<h1>dashboard.html missing</h1>", "text/html")
        elif path == "/api/state":
            self._send(200, game.full_state(self._is_referee()))
        elif path == "/status":  # Mark 3 compatibility
            d = game.device_state()
            self._send(200, {"current_hp": d["hp"], "is_eliminated": d["st"] == "OUT"})
        elif path == "/reset":  # browser shortcut
            if not self._is_referee():
                return self._send(403, {"error": "referee key required"})
            game.reset()
            self._send(200, "<h1>Arena reset to LOBBY.</h1><p><a href='/'>Open dashboard</a></p>", "text/html")
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        data = self._json_body()
        if data is None:
            return self._send(400, {"error": "bad json"})

        if path == "/heartbeat":
            vest = self._touch_node(data)
            if not vest:
                return self._send(400, {"error": "unknown node_id"})
            return self._send(200, game.device_state(vest.id))

        if path == "/hit":
            vest = self._touch_node(data)
            if not vest:
                return self._send(400, {"error": "unknown node_id"})
            code = data.get("button_code", "")
            ev = game.process_hit(code, vest.id, bool(data.get("assist")))
            out = game.device_state(vest.id)
            out.update(ev)
            # Mark 3 compatibility fields
            out.update({
                "event_type": ev["ev"], "current_hp": out["hp"],
                "is_eliminated": out["st"] == "OUT",
                "lcd_line1": ev["l1"], "lcd_line2": ev["l2"],
            })
            return self._send(200, out)

        if path == "/sync":
            vest = game.touch_vest(data.get("node_id", ""), self.client_address[0], {})
            if not vest:
                return self._send(400, {"error": "unknown node_id"})
            try:
                game.sync_offline(vest.id, data)
            except (TypeError, ValueError):
                return self._send(400, {"error": "bad sync"})
            return self._send(200, game.device_state(vest.id))

        if path == "/api/control":
            if not is_referee_key(data.get("key")):
                return self._send(403, {"error": "referee key required"})
            action = data.get("action")
            ok = True
            if action == "start":
                ok = game.start()
            elif action == "pause":
                ok = game.pause()
            elif action == "resume":
                ok = game.resume()
            elif action == "end":
                ok = game.end()
            elif action == "reset":
                game.reset()
            elif action == "settings":
                game.apply_settings(data.get("settings"))
            elif action == "assist":
                ok = game.set_manual_assist(data.get("vest"), data.get("on"))
            elif action == "buzzer":
                ok = game.set_buzzer(data.get("vest"), data.get("type"))
            elif action == "clear_history":
                with game.lock:
                    game.history = []
                    save_history(game.history)
            else:
                return self._send(400, {"error": "unknown action"})
            return self._send(200, {"ok": ok, "state": game.full_state()})

        self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        return


class Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def snapshot_loop():
    while True:
        time.sleep(1)
        try:
            game.save_snapshot()
        except OSError as e:
            print(f"[WARN] Could not save match state: {e}")


def main():
    global REFEREE_KEY
    REFEREE_KEY = load_referee_key()
    game.restore_snapshot()
    threading.Thread(target=snapshot_loop, daemon=True).start()
    threading.Thread(target=discovery_broadcaster, daemon=True).start()
    httpd = Server(("0.0.0.0", HTTP_PORT), Handler)
    threading.Thread(target=terminal_loop, daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
        httpd.server_close()


if __name__ == "__main__":
    main()
