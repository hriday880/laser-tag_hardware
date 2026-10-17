from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import time
import subprocess
import re
from datetime import datetime

# ==========================================
#         GAME DATABASE & STATE
# ==========================================
WEAPON_MAP = {
    "0xFF30CF": {"name": "Friend 1", "type": "BLOCKED", "damage": 0},
    "0xFF18E7": {"name": "Friend 2", "type": "BLOCKED", "damage": 0},
    "0xFF7A85": {"name": "Friend 3", "type": "BLOCKED", "damage": 0},
    "0xFF10EF": {"name": "Friend 4", "type": "BLOCKED", "damage": 0},
    "0xFF38C7": {"name": "Enemy 1",  "type": "DAMAGE",  "damage": 1},
    "0xFF5AA5": {"name": "Enemy 2",  "type": "DAMAGE",  "damage": 1},
    "0xFF42BD": {"name": "Enemy 3",  "type": "DAMAGE",  "damage": 1},
    "0xFF4AB5": {"name": "Enemy 4",  "type": "DAMAGE",  "damage": 1},
    "0xFF52AD": {"name": "Enemy 5",  "type": "DAMAGE",  "damage": 1},
}

class GameReferee:
    def __init__(self):
        self.reset_game()

    def reset_game(self):
        self.max_hp = 5
        self.current_hp = 5
        self.hits_taken = 0
        self.deaths = 0
        self.is_eliminated = False
        self.logs = []
        self.add_log("SYSTEM", "Game started! Target node healthy at 5/5 HP.")

    def add_log(self, source, action):
        t = datetime.now().strftime("%H:%M:%S")
        self.logs.insert(0, f"[{t}] {source:12} : {action}")
        if len(self.logs) > 6:
            self.logs.pop()

    def process_button(self, node_id, hex_code):
        # Fix uppercase 'X' issue (0XFF -> 0xFF)
        lookup_code = hex_code.upper().replace("0X", "0x")
        
        weapon = WEAPON_MAP.get(lookup_code, {
            "name": f"Unknown ({hex_code})",
            "type": "DAMAGE",
            "damage": 1,
        })

        event_type = weapon["type"]
        attacker_name = weapon["name"]
        dmg = weapon["damage"]

        if self.is_eliminated:
            return {
                "status": "ignored",
                "event_type": "ELIMINATED",
                "attacker": attacker_name,
                "current_hp": 0,
                "max_hp": self.max_hp,
                "is_eliminated": True,
                "lcd_line1": "=== GAME OVER ==",
                "lcd_line2": "Reset on Server"
            }

        if event_type == "DAMAGE":
            self.current_hp = max(0, self.current_hp - dmg)
            self.hits_taken += 1
            if self.current_hp == 0:
                self.is_eliminated = True
                self.deaths += 1
                self.add_log(attacker_name, f"KILLED {node_id}! (Total deaths: {self.deaths})")
                line1 = "=== KILLED! ==="
                line2 = f"By: {attacker_name[:12]}"
            else:
                self.add_log(attacker_name, f"Hit {node_id} for {dmg} DMG! (HP: {self.current_hp}/{self.max_hp})")
                line1 = f"HIT: -{dmg} HP"
                line2 = f"By: {attacker_name[:12]}"

        elif event_type == "HEAL":
            old_hp = self.current_hp
            self.current_hp = min(self.max_hp, self.current_hp + 1)
            self.add_log(attacker_name, f"Picked up! HP: {old_hp} -> {self.current_hp}")
            line1 = "+1 HP MEDKIT"
            line2 = f"HP: {self.current_hp}/{self.max_hp}"

        elif event_type == "SHIELD":
            self.add_log(attacker_name, "Shield engaged (4s invulnerable)")
            line1 = "SHIELD ACTIVATED"
            line2 = "Invulnerable 4s"

        elif event_type == "BLOCKED":
            self.add_log(attacker_name, "Friendly fire blocked!")
            line1 = "FRIENDLY FIRE"
            line2 = f"By: {attacker_name}"

        elif event_type == "STUN":
            self.add_log(attacker_name, f"Fired EMP! {node_id} stunned for 3s")
            line1 = "! EMP STUNNED !"
            line2 = "Systems Glitched"

        self.render_dashboard()

        return {
            "status": "success",
            "event_type": event_type,
            "attacker": attacker_name,
            "damage_dealt": dmg,
            "current_hp": self.current_hp,
            "max_hp": self.max_hp,
            "is_eliminated": self.is_eliminated,
            "lcd_line1": line1,
            "lcd_line2": line2
        }

    def render_dashboard(self):
        # ANSI terminal clear & redraw
        hp_blocks = "█" * self.current_hp + "░" * (self.max_hp - self.current_hp)
        status_text = "ELIMINATED" if self.is_eliminated else ("HEALTHY" if self.current_hp >= 4 else ("DAMAGED" if self.current_hp >= 2 else "CRITICAL"))

        output = [
            "\033[2J\033[H",
            "==================================================================",
            "           LASER TAG CENTRAL REFEREE - MARK 3 ARENA               ",
            "==================================================================",
            f" TARGET NODE : PLAYER 1",
            f" HEALTH BAR  : [{hp_blocks}] {self.current_hp}/{self.max_hp} HP   (STATUS: {status_text})",
            f" COMBAT STATS: Hits Taken: {self.hits_taken}   |   Deaths: {self.deaths}",
            "------------------------------------------------------------------",
            " COMBAT EVENT LOG:",
        ]
        for l in self.logs:
            output.append(f"  {l}")
        output.append("------------------------------------------------------------------")
        ips = get_all_local_ips()
        display_ip = ips[0] if ips else "127.0.0.1"
        output.append(f" Remote Reset: Open http://{display_ip}:5050/reset in your browser")
        output.append("==================================================================")
        print("\n".join(output))

referee = GameReferee()

def get_all_local_ips():
    try:
        output = subprocess.check_output(['ifconfig']).decode('utf-8')
        return re.findall(r'inet (?!127\.0\.0\.1)(\d+\.\d+\.\d+\.\d+)', output)
    except Exception:
        return []

class LaserTagRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/hit':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)

            try:
                data = json.loads(post_data.decode('utf-8'))
                node_id = data.get('node_id', 'P1')
                code = data.get('button_code', '')

                # Backward compatibility for Mark 2 payload
                if not code and 'attacker' in data:
                    code = "0xFF5AA5" # default rifle

                result = referee.process_button(node_id, code)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == '/reset':
            referee.reset_game()
            referee.render_dashboard()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<h1>Game Reset! Player 1 restored to 5/5 HP.</h1><p><a href='/reset'>Reset Again</a></p>")
        elif self.path == '/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            payload = {
                "current_hp": referee.current_hp,
                "is_eliminated": str(referee.is_eliminated).lower() # false/true
            }
            self.wfile.write(json.dumps(payload).encode('utf-8'))
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<h1>Laser Tag Server Running</h1><p><a href='/reset'>Click to Reset Game</a></p>")

    def log_message(self, format, *args):
        return

class ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True

def run_server(port=5050):
    ips = get_all_local_ips()
    referee.render_dashboard()

    print(f"\nServer active on port {port}.")
    for ip in ips:
        print(f" -> ESP32 URL: http://{ip}:{port}/hit")
        print(f" -> Web Reset: http://{ip}:{port}/reset")

    server_address = ('0.0.0.0', port)
    httpd = ReusableHTTPServer(server_address, LaserTagRequestHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
        httpd.server_close()

if __name__ == '__main__':
    run_server(5050)
