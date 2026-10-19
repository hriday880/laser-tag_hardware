// ==================================================================
//   LASER TAG — MARK FX PRODUCTION FIRMWARE
//   Ultra-minimalist, competition-grade ESP32 laser tag system.
//   - Gun Enclosure: ESP32 DevKit V1, 1 Trigger Button (D13),
//     Passive Buzzer (D33), 940nm IR LED (D4 via 100R-110R),
//     and 5-LED Unicolor HUD (D18, D19, D21, D22, D23 via 330R).
//   - Vest Harness: 5x TSOP1838 IR receivers (3 front, 2 back)
//     in parallel on D15 via 3-wire umbilical (3V3, GND, D15).
//   - Zero LCD, zero Neopixel strips, zero transistors, zero capacitors.
// ==================================================================

#include <Arduino.h>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRsend.h>
#include <IRutils.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <HTTPClient.h>
#include <Preferences.h>

// ==========================================
//          PLAYER NODE CONFIGURATION
// ==========================================
// Change this single definition for each player board: "P1" through "P8"
#ifndef NODE_ID
#define NODE_ID "P1"
#endif

// Wi-Fi credentials
const char* ssid = "Hriday";
const char* password = "12345678";

// Arena Server Configuration
const int SERVER_PORT = 5050;
const int DISCOVERY_PORT = 5051;
const char* MANUAL_SERVER_IP = "";

// ==========================================
//              PIN DEFINITIONS
// ==========================================
// ESP32 DOIT DevKit V1 (30-pin) Pin Mapping:
const uint16_t IR_RX_PIN      = 15;  // Board Pin D15 -> 5x TSOP1838 OUT joined
const uint16_t IR_LED_PIN     = 4;   // Board Pin D4  -> 940nm IR LED (+) via 100R-110R
const int      TRIGGER_PIN    = 13;  // Board Pin D13 -> Push switch to GND (INPUT_PULLUP)
const int      BUZZER_PIN     = 33;  // Board Pin D33 -> Passive Piezo Buzzer (+)
const int      HUD_PINS[5]    = {18, 19, 21, 22, 23}; // Board Pins D18(1HP), D19(2HP), D21(3HP), D22(4HP), D23(5HP)

// ==========================================
//       8-PLAYER 32-BIT NEC IR CODES
// ==========================================
// Orthogonal 32-bit NEC words recognized by server.py:
// P1-P4 = Blue Team (Friends / Medics), P5-P8 = Red Team (Enemies)
const uint32_t PLAYER_CODES[8] = {
  0x00FF30CF,  // P1: Blue / Friend 1
  0x00FF18E7,  // P2: Blue / Friend 2
  0x00FF7A85,  // P3: Blue / Friend 3
  0x00FF10EF,  // P4: Blue / Friend 4
  0x00FF38C7,  // P5: Red / Enemy 1
  0x00FF5AA5,  // P6: Red / Enemy 2
  0x00FF42BD,  // P7: Red / Enemy 3
  0x00FF4AB5   // P8: Red / Enemy 4
};

// Returns true if code matches one of the 8 recognized players
bool isKnownPlayer(uint32_t code) {
  for (int i = 0; i < 8; i++) {
    if (code == PLAYER_CODES[i]) return true;
  }
  return false;
}

// Returns the 32-bit transmit code for this node
uint32_t getMyShotCode() {
  String id = String(NODE_ID);
  if (id == "P1") return PLAYER_CODES[0];
  if (id == "P2") return PLAYER_CODES[1];
  if (id == "P3") return PLAYER_CODES[2];
  if (id == "P4") return PLAYER_CODES[3];
  if (id == "P5") return PLAYER_CODES[4];
  if (id == "P6") return PLAYER_CODES[5];
  if (id == "P7") return PLAYER_CODES[6];
  if (id == "P8") return PLAYER_CODES[7];
  return PLAYER_CODES[0];
}

// Evaluates whether an incoming code belongs to the same team.
// Unknown codes and ambient noise are rejected (returns false).
bool isMyTeam(uint32_t code) {
  if (!isKnownPlayer(code)) return false;
  String id = String(NODE_ID);
  bool iAmBlue = (id == "P1" || id == "P2" || id == "P3" || id == "P4");
  bool codeIsBlue = (code == PLAYER_CODES[0] || code == PLAYER_CODES[1] ||
                     code == PLAYER_CODES[2] || code == PLAYER_CODES[3]);
  return iAmBlue == codeIsBlue;
}

// Peripheral instances
IRrecv irrecv(IR_RX_PIN);
IRsend irsend(IR_LED_PIN);
decode_results results;
WiFiUDP udp;
Preferences prefs;
bool udpListening = false;

// ==========================================
//             GAME & PLAYER STATE
// ==========================================
String ph = "LOBBY";      // LOBBY | COUNTDOWN | LIVE | PAUSED | GAMEOVER
String pst = "ALIVE";     // ALIVE | RESPAWN | OUT
int hp = 5, mhp = 5;
int lives = 3, mlv = 3;
long tmMs = 0, rsMs = 0, prMs = 0, cdMs = 0;
unsigned long stateAt = 0;
bool haveState = false;

// Network State Machine
enum NetState { NET_DISCOVER, NET_OK, NET_LOST };
NetState net = NET_DISCOVER;
String serverIp = "";
unsigned long lastHeartbeat = 0;
unsigned long lastProbe = 0;
unsigned long lastReconnect = 0;
const unsigned long HEARTBEAT_MS = 1000;
int failCount = 0;

// Standalone offline referee
bool isStandalone = false;
unsigned long offlineRespawnAt = 0;
unsigned long offlineShieldUntil = 0;
unsigned long offlineCooldownUntil = 0;

// Remaining time for server timers
long remaining(long serverMs) {
  if (ph == "PAUSED") return serverMs;
  long r = serverMs - (long)(millis() - stateAt);
  return r > 0 ? r : 0;
}

// ==========================================
//       NON-BLOCKING AUDIO SOUND ENGINE
// ==========================================
struct Note { uint16_t freq; uint16_t dur; };

// Melodies
const Note M_BOOT[]      = {{523, 90}, {0, 30}, {659, 90}, {0, 30}, {784, 160}};
const Note M_SHOT[]      = {{1800, 40}, {1200, 40}};
const Note M_HIT[]       = {{330, 110}, {0, 70}, {262, 140}};
const Note M_HEAL[]      = {{659, 100}, {0, 30}, {988, 220}};
const Note M_SHIELD[]    = {{1200, 60}, {0, 50}, {1200, 60}};
const Note M_HEARTBEAT[] = {{220, 80}, {0, 80}, {220, 80}};
const Note M_DEATH[]     = {{784, 180}, {0, 40}, {659, 180}, {0, 40}, {523, 180}, {0, 40}, {392, 450}};
const Note M_ELIM[]      = {{523, 300}, {0, 80}, {392, 300}, {0, 80}, {330, 300}, {0, 80}, {262, 700}};
const Note M_GO[]        = {{1047, 450}};
const Note M_WIN[]       = {{523, 120}, {659, 120}, {784, 120}, {1047, 250}, {0, 60}, {784, 120}, {1047, 450}};
const Note M_LOSE[]      = {{392, 250}, {370, 250}, {349, 250}, {330, 600}};
const Note M_TICK[]      = {{880, 80}};
const Note M_WARN[]      = {{1500, 60}};
const Note M_PAUSE[]     = {{600, 150}, {0, 60}, {400, 200}};
const Note M_RESUME[]    = {{400, 150}, {0, 60}, {600, 200}};

// Priority levels
#define PRIO_IDLE      0
#define PRIO_GAMEPLAY  1  // shots, ticks, heartbeat
#define PRIO_EVENT     2  // hits, heals, shield blocked
#define PRIO_CRITICAL  3  // death, elim, match win/lose

const Note* currentMelody = nullptr;
int melodyLen = 0;
int melodyIdx = 0;
int currentPriority = PRIO_IDLE;
unsigned long noteEndsAt = 0;
unsigned long lastHeartbeatToneAt = 0;

void buzzerOff() {
  noTone(BUZZER_PIN);
  digitalWrite(BUZZER_PIN, LOW);
}

void startNote() {
  uint16_t f = currentMelody[melodyIdx].freq;
  uint16_t d = currentMelody[melodyIdx].dur;
  if (f > 0) {
    tone(BUZZER_PIN, f, d);
  } else {
    buzzerOff();
  }
  noteEndsAt = millis() + d;
}

bool playSound(const Note* m, int len, int priority) {
  if (currentMelody && priority < currentPriority) {
    return false; // Blocked by higher priority active melody
  }
  currentMelody = m;
  melodyLen = len;
  melodyIdx = 0;
  currentPriority = priority;
  startNote();
  return true;
}

#define PLAY(m, p) playSound(m, sizeof(m) / sizeof(m[0]), p)

void updateSound() {
  if (!currentMelody) return;
  if (millis() < noteEndsAt) return;

  melodyIdx++;
  if (melodyIdx >= melodyLen) {
    buzzerOff();
    currentMelody = nullptr;
    currentPriority = PRIO_IDLE;
    return;
  }
  startNote();
}

// Non-blocking acoustic low-health warning (lub-dub heartbeat every 1000ms at 1 HP)
void updateHeartbeat() {
  unsigned long now = millis();
  bool inGame = (net == NET_OK && ph == "LIVE") || (isStandalone && lives > 0);
  if (inGame && pst == "ALIVE" && hp == 1) {
    if (now - lastHeartbeatToneAt >= 1000) {
      if (PLAY(M_HEARTBEAT, PRIO_GAMEPLAY)) {
        lastHeartbeatToneAt = now;
      }
    }
  }
}

// ==========================================
//        NON-BLOCKING 5-LED UNICOLOR HUD
// ==========================================
unsigned long muzzleFlashUntil = 0;

void triggerMuzzleFlash() {
  muzzleFlashUntil = millis() + 50; // 50ms high-intensity flash on trigger
}

void setHUD(bool l1, bool l2, bool l3, bool l4, bool l5) {
  digitalWrite(HUD_PINS[0], l1 ? HIGH : LOW);
  digitalWrite(HUD_PINS[1], l2 ? HIGH : LOW);
  digitalWrite(HUD_PINS[2], l3 ? HIGH : LOW);
  digitalWrite(HUD_PINS[3], l4 ? HIGH : LOW);
  digitalWrite(HUD_PINS[4], l5 ? HIGH : LOW);
}

void updateHUD() {
  unsigned long now = millis();

  // 1. Muzzle Flash Priority
  if (now < muzzleFlashUntil) {
    setHUD(true, true, true, true, true);
    return;
  }

  // 2. Offline / Standalone Logic
  if (isStandalone) {
    if (lives <= 0 || pst == "OUT") {
      setHUD(false, false, false, false, false);
      return;
    }
    if (pst == "RESPAWN" || now < offlineShieldUntil) {
      bool b = ((now / 250) % 2) == 0;
      setHUD(b, b, b, b, b);
      return;
    }
    if (hp >= 5)      setHUD(true, true, true, true, true);
    else if (hp == 4) setHUD(true, true, true, true, false);
    else if (hp == 3) setHUD(true, true, true, false, false);
    else if (hp == 2) setHUD(true, true, false, false, false);
    else if (hp == 1) {
      // Synchronous Heartbeat Pulse: LED 1 pulses in exact lockstep with acoustic heartbeat (200ms ON, 800ms OFF)
      bool b = (lastHeartbeatToneAt > 0) && ((now - lastHeartbeatToneAt) < 200);
      setHUD(b, false, false, false, false);
    } else {
      setHUD(false, false, false, false, false);
    }
    return;
  }

  // 3. Match / Connected Logic
  if (net == NET_DISCOVER || ph == "LOBBY") {
    // Knight Rider sweep back and forth (100ms per step)
    const int seq[8] = {0, 1, 2, 3, 4, 3, 2, 1};
    int activeIdx = seq[(now / 100) % 8];
    setHUD(activeIdx == 0, activeIdx == 1, activeIdx == 2, activeIdx == 3, activeIdx == 4);
    return;
  }

  if (ph == "COUNTDOWN") {
    bool b = ((now / 250) % 2) == 0;
    setHUD(b, b, b, b, b);
    return;
  }

  if (ph == "PAUSED") {
    bool b = ((now / 500) % 2) == 0;
    setHUD(b, false, b, false, b);
    return;
  }

  if (ph == "GAMEOVER" || pst == "OUT" || lives <= 0) {
    setHUD(false, false, false, false, false);
    return;
  }

  // LIVE GAMEPLAY
  if (pst == "RESPAWN" || remaining(rsMs) > 0 || remaining(prMs) > 0) {
    // Invulnerability / Respawn Shield strobe
    bool b = ((now / 250) % 2) == 0;
    setHUD(b, b, b, b, b);
    return;
  }

  // Health levels
  if (hp >= 5)      setHUD(true, true, true, true, true);
  else if (hp == 4) setHUD(true, true, true, true, false);
  else if (hp == 3) setHUD(true, true, true, false, false);
  else if (hp == 2) setHUD(true, true, false, false, false);
  else if (hp == 1) {
    // Critical Panic Pulse: D18 in lockstep with acoustic heartbeat (200ms ON, 800ms OFF)
    bool b = (lastHeartbeatToneAt > 0) && ((now - lastHeartbeatToneAt) < 200);
    setHUD(b, false, false, false, false);
  } else {
    setHUD(false, false, false, false, false);
  }
}

// ==========================================
//        GUN TRIGGER (TACTILE SWITCH)
// ==========================================
unsigned long lastShotAt = 0;
const unsigned long FIRE_COOLDOWN_MATCH_MS = 600;
const unsigned long FIRE_COOLDOWN_TEST_MS  = 500;

void fireWeapon() {
  uint32_t code = getMyShotCode();
  triggerMuzzleFlash();
  irsend.sendNEC(code, 32);
  lastShotAt = millis();
  PLAY(M_SHOT, PRIO_GAMEPLAY);
  Serial.printf("[GUN] Node %s fired 0x%08X\n", NODE_ID, code);
}

void handleTrigger() {
  static bool debouncedState = HIGH;
  static bool lastReading = HIGH;
  static unsigned long lastDebounceMs = 0;

  bool reading = digitalRead(TRIGGER_PIN);

  if (reading != lastReading) {
    lastDebounceMs = millis();
    lastReading = reading;
  }

  if ((millis() - lastDebounceMs) >= 40) { // 40ms strict debounce
    if (reading != debouncedState) {
      debouncedState = reading;
      if (debouncedState == LOW) {
        // Confirmed button press (falling edge)
        unsigned long now = millis();
        unsigned long cooldown = (net == NET_OK && ph == "LIVE") ? FIRE_COOLDOWN_MATCH_MS : FIRE_COOLDOWN_TEST_MS;

        if (now - lastShotAt >= cooldown) {
          // Match live checks
          if (net == NET_OK && ph == "LIVE") {
            if (pst == "ALIVE" && remaining(rsMs) == 0) {
              fireWeapon();
            }
          } else if (isStandalone) {
            // Standalone mode: only fire when ALIVE and lives remain
            if (pst == "ALIVE" && lives > 0) {
              fireWeapon();
            }
          } else {
            // Offline / Lobby test firing
            fireWeapon();
          }
        }
      }
    }
  }
}

// ==========================================
//       STANDALONE REFEREE TIMERS
// ==========================================
void updateStandalone() {
  if (!isStandalone) return;
  unsigned long now = millis();
  if (pst == "RESPAWN" && now >= offlineRespawnAt) {
    pst = "ALIVE";
    hp = 5;
    offlineShieldUntil = now + 3000; // 3s respawn shield protection
    PLAY(M_SHIELD, PRIO_EVENT);
  }
}

// ==========================================
//          SERVER COMMUNICATION & JSON
// ==========================================
String parseJson(const String& json, const String& key) {
  String k = "\"" + key + "\":";
  int idx = json.indexOf(k);
  if (idx < 0) return "";
  idx += k.length();
  while (idx < (int)json.length() && (json[idx] == ' ' || json[idx] == '\"')) idx++;
  int endIdx = idx;
  while (endIdx < (int)json.length() && json[endIdx] != ',' && json[endIdx] != '\"' && json[endIdx] != '}') endIdx++;
  String v = json.substring(idx, endIdx);
  v.trim();
  return v;
}

bool postJson(const char* path, const String& body, String& out) {
  if (serverIp.length() == 0 || WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  http.setTimeout(400); // 400ms non-blocking timeout
  http.setConnectTimeout(400);
  http.begin("http://" + serverIp + ":" + String(SERVER_PORT) + path);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(body);
  bool ok = (code == 200);
  if (ok) out = http.getString();
  http.end();
  return ok;
}

void applyState(const String& js, const String& ev) {
  String prevPh = ph, prevSt = pst;
  int prevHp = hp;
  bool first = !haveState;

  String v;
  v = parseJson(js, "ph");   if (v.length()) ph = v;
  v = parseJson(js, "st");   if (v.length()) pst = v;
  v = parseJson(js, "hp");   if (v.length()) hp = v.toInt();
  v = parseJson(js, "mhp");  if (v.length()) mhp = v.toInt();
  v = parseJson(js, "lv");   if (v.length()) lives = v.toInt();
  v = parseJson(js, "mlv");  if (v.length()) mlv = v.toInt();
  v = parseJson(js, "tm");   if (v.length()) tmMs = v.toInt();
  v = parseJson(js, "rs");   if (v.length()) rsMs = v.toInt();
  v = parseJson(js, "pr");   if (v.length()) prMs = v.toInt();
  v = parseJson(js, "cd");   if (v.length()) cdMs = v.toInt();
  stateAt = millis();
  haveState = true;

  if (first) return;

  // Transitions & Events
  if (ph != prevPh) {
    if (ph == "LIVE" && prevPh == "COUNTDOWN") PLAY(M_GO, PRIO_CRITICAL);
    else if (ph == "PAUSED") PLAY(M_PAUSE, PRIO_EVENT);
    else if (prevPh == "PAUSED") PLAY(M_RESUME, PRIO_EVENT);
    else if (ph == "GAMEOVER") {
      String res = parseJson(js, "res");
      if (res == "YOU SURVIVED!" || res == "WIN") PLAY(M_WIN, PRIO_CRITICAL);
      else PLAY(M_LOSE, PRIO_CRITICAL);
    }
  }

  if (pst != prevSt) {
    if (pst == "RESPAWN") PLAY(M_DEATH, PRIO_CRITICAL);
    else if (pst == "OUT") PLAY(M_ELIM, PRIO_CRITICAL);
  }

  if (ev.length()) {
    if (ev == "HIT") {
      if (hp == 1) lastHeartbeatToneAt = 0;
      PLAY(M_HIT, PRIO_EVENT);
    }
    else if (ev == "HEAL") PLAY(M_HEAL, PRIO_EVENT);
    else if (ev == "BLOCKED" || ev == "FULL") PLAY(M_SHIELD, PRIO_EVENT);
  }
}

bool sendHeartbeat() {
  String body = "{\"node_id\":\"" + String(NODE_ID) + "\",\"rssi\":" + String(WiFi.RSSI()) + "}";
  String resp;
  if (!postJson("/heartbeat", body, resp)) return false;
  applyState(resp, "");
  return true;
}

void sendHit(uint64_t code) {
  char hexBuf[20];
  snprintf(hexBuf, sizeof(hexBuf), "0x%llX", code);
  String body = "{\"node_id\":\"" + String(NODE_ID) + "\",\"button_code\":\"" + String(hexBuf) + "\"}";
  Serial.printf("[IR] Received hit %s, sending to server...\n", hexBuf);

  String resp;
  if (postJson("/hit", body, resp)) {
    applyState(resp, parseJson(resp, "ev"));
    lastHeartbeat = millis();
    failCount = 0;
  }
}

// ==========================================
//           TSOP1838 IR RECEPTION
// ==========================================
void handleIR() {
  if (!irrecv.decode(&results)) return;
  uint64_t code = results.value;
  irrecv.resume();

  // Filter invalid codes, 32-bit and 64-bit NEC repeat codes
  if (code == 0 || (uint32_t)code == 0xFFFFFFFF || code == 0xFFFFFFFFFFFFFFFFULL) return;

  // Filter reflections of own shot
  if ((uint32_t)code == getMyShotCode()) return;

  // Match live mode
  if (net == NET_OK && ph == "LIVE" && pst == "ALIVE") {
    if (remaining(prMs) > 0 || remaining(cdMs) > 0) {
      if (remaining(prMs) > 0) PLAY(M_SHIELD, PRIO_EVENT);
      return;
    }
    sendHit(code);
    return;
  }

  // Standalone / Offline mode referee
  if (isStandalone) {
    if (lives <= 0 || pst == "OUT") return;

    // Reject unknown codes / ambient noise in standalone mode
    if (!isKnownPlayer((uint32_t)code)) return;

    // Block hits while respawning
    if (pst == "RESPAWN") return;

    // Determine friend or enemy hit
    bool friendly = isMyTeam((uint32_t)code);

    if (!friendly) {
      // Enemy hit taken!
      // Check spawn shield / invulnerability
      if (millis() < offlineShieldUntil) {
        PLAY(M_SHIELD, PRIO_EVENT);
        return;
      }

      // Check 3s damage cooldown
      if (millis() < offlineCooldownUntil) {
        return;
      }

      hp--;
      offlineCooldownUntil = millis() + 3000; // 3s hit cooldown

      if (hp > 0) {
        if (hp == 1) lastHeartbeatToneAt = 0;
        PLAY(M_HIT, PRIO_EVENT);
      } else {
        lives--;
        if (lives > 0) {
          pst = "RESPAWN";
          hp = 0;
          offlineRespawnAt = millis() + 10000; // 10s respawn penalty
          PLAY(M_DEATH, PRIO_CRITICAL);
        } else {
          pst = "OUT";
          hp = 0;
          lives = 0;
          PLAY(M_ELIM, PRIO_CRITICAL);
        }
      }
    } else {
      // Friendly medic heal!
      if (hp < 5) {
        hp++;
        PLAY(M_HEAL, PRIO_EVENT);
      } else {
        PLAY(M_SHIELD, PRIO_EVENT);
      }
    }
    return;
  }

  // Lobby test mode
  PLAY(M_TICK, PRIO_GAMEPLAY);
}

// ==========================================
//            NETWORK & DISCOVERY
// ==========================================
void checkDiscovery() {
  int size = udp.parsePacket();
  if (size <= 0) return;
  char buf[32];
  int n = udp.read(buf, sizeof(buf) - 1);
  buf[n > 0 ? n : 0] = 0;
  if (strncmp(buf, "LASERTAG", 8) != 0) return;
  String ip = udp.remoteIP().toString();
  if (ip == serverIp && net == NET_OK) return;

  serverIp = ip;
  if (sendHeartbeat()) {
    net = NET_OK;
    failCount = 0;
    isStandalone = false;
    prefs.putString("server_ip", serverIp);
    Serial.println("[NET] Connected to referee server: " + serverIp + " (saved to NVS)");
  }
}

void updateNetwork() {
  unsigned long now = millis();

  if (WiFi.status() != WL_CONNECTED) {
    udpListening = false;
    if (net == NET_OK) {
      net = NET_LOST;
      isStandalone = true;
    }
    if (now - lastReconnect > 5000) {
      lastReconnect = now;
      WiFi.reconnect();
    }
    return;
  }

  // WiFi is connected. Ensure UDP discovery listener is bound
  if (!udpListening) {
    udp.stop();
    if (udp.begin(DISCOVERY_PORT)) {
      udpListening = true;
      Serial.printf("[NET] UDP bound to port %d\n", DISCOVERY_PORT);
    }
    if (net == NET_LOST || net == NET_DISCOVER) {
      net = NET_DISCOVER;
    }
  }

  checkDiscovery();

  if (net == NET_DISCOVER || net == NET_LOST) {
    if (now - lastProbe > 2000) {
      lastProbe = now;
      if (serverIp.length() > 0 && sendHeartbeat()) {
        net = NET_OK;
        isStandalone = false;
        failCount = 0;
        prefs.putString("server_ip", serverIp);
        Serial.println("[NET] Connected to referee server: " + serverIp);
      }
    }
  } else if (net == NET_OK) {
    if (now - lastHeartbeat > HEARTBEAT_MS) {
      lastHeartbeat = now;
      if (sendHeartbeat()) {
        failCount = 0;
      } else if (++failCount >= 3) {
        net = NET_LOST;
        isStandalone = true;
        Serial.println("[NET] Server lost -> Fallback to Standalone Mode");
      }
    }
  }
}

// ==========================================
//                   SETUP
// ==========================================
void setup() {
  Serial.begin(115200);

  // Pin Configurations
  pinMode(TRIGGER_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  for (int i = 0; i < 5; i++) {
    pinMode(HUD_PINS[i], OUTPUT);
    digitalWrite(HUD_PINS[i], LOW);
  }

  // IR Subsystem (Receivers enabled on D15, Emitter on D4)
  irrecv.enableIRIn();
  irsend.begin();

  // Boot Chime & 5-LED Sweep
  PLAY(M_BOOT, PRIO_CRITICAL);

  // NVS Preferences: Load cached server IP with fallback to MANUAL_SERVER_IP
  prefs.begin("lasertag", false);
  String fallbackIp = (MANUAL_SERVER_IP != nullptr) ? String(MANUAL_SERVER_IP) : "";
  serverIp = prefs.getString("server_ip", fallbackIp);
  if (serverIp.length() == 0 && fallbackIp.length() > 0) {
    serverIp = fallbackIp;
  }
  if (serverIp.length() > 0) {
    Serial.println("[NVS] Loaded server IP: " + serverIp);
  }

  // WiFi Initialization
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false); // CRITICAL: Modem sleep ruins IR modulation timing!
  WiFi.setAutoReconnect(true);
  WiFi.begin(ssid, password);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 10) {
    delay(200);
    updateHUD();
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("[WIFI] Connected: " + WiFi.localIP().toString());
    udp.begin(DISCOVERY_PORT);
    udpListening = true;
    net = NET_DISCOVER;
    isStandalone = false;
  } else {
    Serial.println("[WIFI] Standalone Mode active (no Wi-Fi found). Ready to play!");
    net = NET_LOST;
    isStandalone = true;
    hp = 5;
    lives = 3;
    pst = "ALIVE";
  }
}

// ==========================================
//                 MAIN LOOP
// ==========================================
void loop() {
  updateSound();      // Non-blocking polyphonic buzzer
  updateHeartbeat();  // Acoustic low-health warning (hp == 1)
  updateHUD();        // Non-blocking 5-LED health bar
  updateStandalone(); // Standalone respawn and shield timers
  handleTrigger();    // 40ms debounced weapon trigger
  handleIR();         // TSOP1838 vest array reception
  updateNetwork();    // Match server sync & auto-discovery
}
