#!/usr/bin/env python3
"""
LASER TAG CENTRAL SERVER - MARK 4
Zero external dependencies (Python standard library only).

  - Authoritative referee: match phases, HP, lives, respawn, scoring
  - Fun rules: Medic friends, Traitors, First Blood, Finisher bonus
  - Web dashboard at http://<IP>:5050/
  - UDP auto-discovery broadcast (ESP32 finds this server by itself)
  - Match history saved to matches.json

Still compatible with Mark 3 firmware (/hit and /status).
"""
import json
import os
import re
import socket
import subprocess
import threading
import time
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HTTP_PORT = 5050
DISCOVERY_PORT = 5051
NODE_TIMEOUT_S = 3.5

HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(HERE, "matches.json")
DASHBOARD_FILE = os.path.join(HERE, "dashboard.html")

# ==========================================
#      SHOOTERS (same hex codes as Mark 1)
# ==========================================
SHOOTERS = {
    "0xFF30CF": ("Friend 1", "FRIEND"),
    "0xFF18E7": ("Friend 2", "FRIEND"),
    "0xFF7A85": ("Friend 3", "FRIEND"),
    "0xFF10EF": ("Friend 4", "FRIEND"),
    "0xFF38C7": ("Enemy 1", "ENEMY"),
    "0xFF5AA5": ("Enemy 2", "ENEMY"),
    "0xFF42BD": ("Enemy 3", "ENEMY"),
    "0xFF4AB5": ("Enemy 4", "ENEMY"),
    "0xFF52AD": ("Enemy 5", "ENEMY"),
}

DEFAULT_SETTINGS = {
    "max_hp": 5,
    "max_lives": 3,
    "respawn_s": 10,
    "protect_s": 3,
    "match_s": 300,
    "cooldown_s": 3,
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
class Game:
    def __init__(self):
        self.lock = threading.RLock()
        self.settings = dict(DEFAULT_SETTINGS)
        self.node = {"id": "P1", "ip": None, "rssi": None, "last_seen": 0.0}
        self.history = load_history()
        self.version = 0  # bumps on every state change (for terminal redraws)
        self.reset()

    # ---------- helpers ----------
    def clock(self):
        """Frozen while paused, so all countdowns stop."""
        return self.paused_at if self.phase == "PAUSED" else time.time()

    def log(self, src, msg, kind="info"):
        self.feed.insert(0, {"t": datetime.now().strftime("%H:%M:%S"), "src": src, "msg": msg, "kind": kind})
        del self.feed[40:]
        self.version += 1

    def node_online(self):
        return (time.time() - self.node["last_seen"]) < NODE_TIMEOUT_S

    # ---------- admin controls ----------
    def reset(self):
        with self.lock:
            s = self.settings
            self.phase = "LOBBY"
            self.paused_at = 0.0
            self.paused_from = "LIVE"
            self.countdown_end = 0.0
            self.match_started_at = 0.0
            self.match_end = 0.0
            self.hp = s["max_hp"]
            self.lives = s["max_lives"]
            self.pstate = "ALIVE"  # ALIVE | RESPAWN | OUT
            self.respawn_at = 0.0
            self.protect_until = 0.0
            self.cooldown_until = 0.0
            self.hits_taken = 0
            self.deaths = 0
            self.heals = 0
            self.last_attacker = "None"
            self.first_blood_done = False
            self.result = ""
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
            self.phase = "COUNTDOWN"
            self.countdown_end = time.time() + COUNTDOWN_S
            self.log("SYSTEM", f"Match starting in {COUNTDOWN_S}...", "system")
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
            self.respawn_at += d
            self.protect_until += d
            self.cooldown_until += d
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
                    self.hp = self.settings["max_hp"]
                    self.lives = self.settings["max_lives"]
            return changed

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
                if self.pstate == "RESPAWN" and now >= self.respawn_at:
                    self.pstate = "ALIVE"
                    self.hp = self.settings["max_hp"]
                    self.protect_until = now + self.settings["protect_s"]
                    self.log("P1", f"Respawned with {self.hp} HP ({self.lives} lives left)", "good")
                if now >= self.match_end:
                    self.finish("SURVIVED")

    def finish(self, reason):
        self.phase = "GAMEOVER"
        self.paused_at = 0.0
        ranked = sorted(self.stats.values(), key=lambda s: s["score"], reverse=True)
        top = ranked[0] if ranked and ranked[0]["score"] > 0 else None
        self.mvp = top["name"] if top else "Nobody"
        if reason == "SURVIVED":
            self.result = "YOU SURVIVED!"
            self.log("SYSTEM", f"Time up! P1 SURVIVED. MVP: {self.mvp}", "system")
        elif reason == "ELIMINATED":
            self.result = "ELIMINATED"
            self.log("SYSTEM", f"P1 ELIMINATED. MVP: {self.mvp}", "system")
        else:
            self.result = "MATCH ENDED"
            self.log("SYSTEM", f"Match ended by admin. MVP: {self.mvp}", "system")

        played = (time.time() - self.match_started_at) if self.match_started_at else 0
        self.history.insert(0, {
            "ended_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "result": self.result,
            "duration_s": int(played),
            "hits_taken": self.hits_taken,
            "deaths": self.deaths,
            "heals": self.heals,
            "mvp": self.mvp,
            "scoreboard": [{k: s[k] for k in ("name", "team", "hits", "kills", "heals", "strikes", "score", "traitor")}
                           for s in ranked],
        })
        del self.history[50:]
        save_history(self.history)

    # ---------- hits ----------
    def process_hit(self, raw_code):
        """Returns an event dict: ev, attacker, l1, l2 (LCD lines, max 16 chars, no commas)."""
        with self.lock:
            self.tick()
            code = normalize_code(raw_code)
            info = SHOOTERS.get(code)
            if not info:
                self.log("SENSOR", f"Unknown IR code {code} ignored", "dim")
                return {"ev": "IGNORED", "attacker": "", "l1": "", "l2": ""}

            name, team = info
            st = self.stats[name]

            if self.phase != "LIVE":
                return {"ev": "NOTLIVE", "attacker": name, "l1": "MATCH NOT LIVE", "l2": f"Phase: {self.phase}"}
            if self.pstate != "ALIVE":
                return {"ev": "NOTALIVE", "attacker": name, "l1": "", "l2": ""}

            now = time.time()
            s = self.settings

            # ---- FRIEND (medic) ----
            if team == "FRIEND" and not st["traitor"]:
                if now < st["medic_ready_at"]:
                    st["strikes"] += 1
                    st["score"] += PTS_STRIKE
                    if st["strikes"] >= s["traitor_strikes"]:
                        st["traitor"] = True
                        self.log(name, f"TURNED TRAITOR after {st['strikes']} friendly-fire strikes!", "bad")
                        return {"ev": "TRAITOR", "attacker": name, "l1": "!! TRAITOR !!", "l2": f"{name} defected"}
                    left = s["traitor_strikes"] - st["strikes"]
                    self.log(name, f"Friendly fire! Strike {st['strikes']} ({left} until TRAITOR)", "warn")
                    return {"ev": "FF", "attacker": name, "l1": "FRIENDLY FIRE!", "l2": f"{name} strike {st['strikes']}"}

                if self.hp >= s["max_hp"]:
                    self.log(name, "Medic beam wasted - HP already full", "dim")
                    return {"ev": "FULL", "attacker": name, "l1": "HP ALREADY FULL", "l2": f"Medic: {name}"}

                self.hp += 1
                self.heals += 1
                st["heals"] += 1
                st["score"] += PTS_HEAL
                st["medic_ready_at"] = now + s["medic_cooldown_s"]
                self.log(name, f"MEDIC heal +1 HP (HP {self.hp}/{s['max_hp']})", "good")
                return {"ev": "HEAL", "attacker": name, "l1": "+1 HP  MEDIC", "l2": f"By: {name}"}

            # ---- ENEMY (or traitor) ----
            label = f"{name} (T)" if st["traitor"] else name
            if now < self.protect_until:
                self.log(label, "Shot blocked by spawn shield", "dim")
                return {"ev": "BLOCKED", "attacker": label, "l1": "SPAWN SHIELD", "l2": "Shot blocked!"}
            if now < self.cooldown_until:
                return {"ev": "COOLDOWN", "attacker": label, "l1": "", "l2": ""}

            self.hp = max(0, self.hp - 1)
            self.hits_taken += 1
            self.cooldown_until = now + s["cooldown_s"]
            self.last_attacker = label
            st["hits"] += 1
            st["score"] += PTS_HIT

            if not self.first_blood_done:
                self.first_blood_done = True
                st["score"] += PTS_FIRST_BLOOD
                self.log(label, f"FIRST BLOOD! (+{PTS_FIRST_BLOOD} bonus)", "bad")

            if self.hp > 0:
                self.log(label, f"Hit P1 -1 HP (HP {self.hp}/{s['max_hp']})", "bad")
                return {"ev": "HIT", "attacker": label, "l1": f"HIT! -1 HP  {self.hp}/{s['max_hp']}", "l2": f"By: {label}"}

            # life lost
            self.lives -= 1
            self.deaths += 1
            st["kills"] += 1
            st["score"] += PTS_KILL
            if self.lives <= 0:
                st["score"] += PTS_FINISHER
                self.pstate = "OUT"
                self.log(label, f"FINISHER! Eliminated P1 (+{PTS_FINISHER})", "bad")
                self.finish("ELIMINATED")
                return {"ev": "ELIM", "attacker": label, "l1": "== ELIMINATED ==", "l2": f"By: {label}"}

            self.pstate = "RESPAWN"
            self.respawn_at = now + s["respawn_s"]
            self.log(label, f"KILLED P1! {self.lives} lives left", "bad")
            return {"ev": "DEATH", "attacker": label, "l1": "=== KILLED! ===", "l2": f"By: {label}"}

    # ---------- views ----------
    def device_state(self):
        """Flat JSON for the ESP32 (short keys, ASCII only, no commas in strings)."""
        with self.lock:
            self.tick()
            now = self.clock()
            s = self.settings
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
            return {
                "ph": ph,
                "st": self.pstate,
                "hp": self.hp, "mhp": s["max_hp"],
                "lv": self.lives, "mlv": s["max_lives"],
                "tm": tm,
                "rs": ms(self.respawn_at - now) if self.pstate == "RESPAWN" else 0,
                "pr": ms(self.protect_until - now),
                "cd": ms(self.cooldown_until - now),
                "last": self.last_attacker,
                "ht": self.hits_taken,
                "dt": self.deaths,
                "res": self.result,
                "mvp": self.mvp,
            }

    def full_state(self):
        """Rich JSON for the web dashboard."""
        with self.lock:
            dev = self.device_state()
            ranked = sorted(self.stats.values(), key=lambda s: s["score"], reverse=True)
            now = self.clock()
            board = []
            for st in ranked:
                row = {k: st[k] for k in ("name", "team", "hits", "kills", "heals", "strikes", "score", "traitor")}
                row["medic_ready_in"] = round(max(0, st["medic_ready_at"] - now), 1) if st["team"] == "FRIEND" else None
                board.append(row)
            return {
                "device": dev,
                "settings": self.settings,
                "limits": SETTING_LIMITS,
                "node": {
                    "id": self.node["id"],
                    "ip": self.node["ip"],
                    "rssi": self.node["rssi"],
                    "online": self.node_online(),
                    "last_seen_s": round(time.time() - self.node["last_seen"], 1) if self.node["last_seen"] else None,
                },
                "stats": {"hits_taken": self.hits_taken, "deaths": self.deaths, "heals": self.heals},
                "leaderboard": board,
                "feed": self.feed,
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
    hearts = "█" * d["hp"] + "░" * (d["mhp"] - d["hp"])
    secs = d["tm"] // 1000
    node = st["node"]
    node_txt = f"ONLINE  RSSI {node['rssi']} dBm  IP {node['ip']}" if node["online"] else "OFFLINE"
    ips = st["server_ips"]
    lines = [
        "\033[2J\033[H",
        "==================================================================",
        "          LASER TAG CENTRAL REFEREE - MARK 4 ARENA",
        "==================================================================",
        f" PHASE  : {d['ph']:<10}  TIMER: {secs // 60:02d}:{secs % 60:02d}",
        f" PLAYER : [{hearts}] {d['hp']}/{d['mhp']} HP   Lives {d['lv']}/{d['mlv']}   ({d['st']})",
        f" NODE P1: {node_txt}",
        f" STATS  : Hits taken {st['stats']['hits_taken']} | Deaths {st['stats']['deaths']} | Heals {st['stats']['heals']}",
        "------------------------------------------------------------------",
        " EVENT LOG:",
    ]
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
        sig = (game.version, st["ph"], st["tm"] // 1000, st["hp"], st["lv"], st["st"], game.node_online(), game.node["rssi"])
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
        with game.lock:
            game.node["id"] = data.get("node_id", "P1")
            game.node["ip"] = self.client_address[0]
            if "rssi" in data:
                game.node["rssi"] = data.get("rssi")
            was_online = game.node_online()
            game.node["last_seen"] = time.time()
            if not was_online:
                game.log("NETWORK", f"Node {game.node['id']} connected from {game.node['ip']}", "system")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            try:
                with open(DASHBOARD_FILE, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, "<h1>dashboard.html missing</h1>", "text/html")
        elif path == "/api/state":
            self._send(200, game.full_state())
        elif path == "/status":  # Mark 3 compatibility
            d = game.device_state()
            self._send(200, {"current_hp": d["hp"], "is_eliminated": d["st"] == "OUT"})
        elif path == "/reset":  # browser shortcut
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
            self._touch_node(data)
            return self._send(200, game.device_state())

        if path == "/hit":
            self._touch_node(data)
            code = data.get("button_code", "")
            ev = game.process_hit(code)
            out = game.device_state()
            out.update(ev)
            # Mark 3 compatibility fields
            out.update({
                "event_type": ev["ev"], "current_hp": out["hp"],
                "is_eliminated": out["st"] == "OUT",
                "lcd_line1": ev["l1"], "lcd_line2": ev["l2"],
            })
            return self._send(200, out)

        if path == "/api/control":
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


def main():
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
