// ==================================================================
//   LASER TAG — MARK FX PRODUCTION FIRMWARE
//   Ultra-minimalist, competition-grade ESP32 laser tag system.
//   - Gun Enclosure: ESP32 DevKit V1, 1 Trigger Button (D13),
//     Passive Buzzer (D33), 940nm IR LED (D4 via 100R-110R),
//     and 5-LED Unicolor HUD (D18, D19, D21, D22, D23 via 330R).
//   - Vest Harness: 5x TSOP1838 IR receivers (3 front, 2 back)
//     in parallel on D15 via 3-wire umbilical (3V3, GND, D15).
//   - Zero LCD, zero Neopixel strips, zero transistors, zero capacitors.
//   - Hidden failsafe: if the whole sensor bus fails, enemy shots heard
//     over ESP-NOW nearby count (1 in 3): enemies damage, teammates heal.
//     Vests share signal strength per shot; only the closest-sounding
//     vest on a team can be hit, and a real IR hit elsewhere cancels it.
//     The player gets no signal; faults show only on the referee page.
//   - Offline play: a live match continues on the gun's own rules, and
//     what happened is sent to the server on reconnect.
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
#include <esp_now.h>
#include <esp_random.h>
#include <driver/gpio.h>

struct Note { uint16_t freq; uint16_t dur; };
struct __attribute__((packed)) ShotPacket { uint8_t magic[2]; uint8_t shooter; uint16_t seq; };
struct __attribute__((packed)) WitnessPacket { uint8_t magic[2]; uint8_t reporter; uint8_t shooter; uint16_t seq; int8_t rssi; uint8_t claimed; };
struct JournalEntry { uint32_t id; char kind; uint8_t shooter; bool assist; };
struct ShotEvent { bool witness; bool claimed; uint8_t reporter; uint8_t shooter; uint16_t seq; int8_t rssi; unsigned long at; };

// ==========================================
//          PLAYER NODE CONFIGURATION
// ==========================================
// >>> CHANGE THIS LINE FOR EACH GUN BEFORE FLASHING <<<
// Use one of: BLUE1 BLUE2 BLUE3 BLUE4 RED1 RED2 RED3 RED4
#ifndef GUN
#define GUN RED2
#endif

// Names map to the IDs used by the server and IR codes
#define BLUE1 "P1"
#define BLUE2 "P2"
#define BLUE3 "P3"
#define BLUE4 "P4"
#define RED1  "P5"
#define RED2  "P6"
#define RED3  "P7"
#define RED4  "P8"

String nodeId = GUN;

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
const uint8_t  IR_TIMING_TOLERANCE = 40; // Library default is 25; only known player codes are accepted
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
  if (nodeId == "P1") return PLAYER_CODES[0];
  if (nodeId == "P2") return PLAYER_CODES[1];
  if (nodeId == "P3") return PLAYER_CODES[2];
  if (nodeId == "P4") return PLAYER_CODES[3];
  if (nodeId == "P5") return PLAYER_CODES[4];
  if (nodeId == "P6") return PLAYER_CODES[5];
  if (nodeId == "P7") return PLAYER_CODES[6];
  if (nodeId == "P8") return PLAYER_CODES[7];
  return PLAYER_CODES[0];
}

// Evaluates whether an incoming code belongs to the same team.
// Unknown codes and ambient noise are rejected (returns false).
bool isMyTeam(uint32_t code) {
  if (!isKnownPlayer(code)) return false;
  bool iAmBlue = (nodeId == "P1" || nodeId == "P2" || nodeId == "P3" || nodeId == "P4");
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
long tmMs = 0, rsMs = 0, prMs = 0, cdMs = 0, dsMs = 0;
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
const unsigned long NO_SERVER_PLAY_AFTER_MS = 15000;

// Standalone offline referee
bool isStandalone = false;
unsigned long offlineRespawnAt = 0;
unsigned long offlineShieldUntil = 0;
unsigned long offlineCooldownUntil = 0;
unsigned long offlineDisarmUntil = 0;
unsigned long offlineDisarmMs = 10000;
// Match rules, refreshed from the server so offline play stays consistent
unsigned long offlineRespawnMs = 10000, offlineShieldMs = 3000, offlineHitCooldownMs = 3000, offlineMedicMs = 20000;
// Events from a live match played offline, replayed to the server on reconnect
const int JOURNAL_LEN = 40;
JournalEntry journal[JOURNAL_LEN];
int journalCount = 0;
uint32_t journalNextId = 1, bootNonce = 0;
long matchId = 0;
bool offlineMatch = false;
bool offlineMedicUsed[8] = {false};
unsigned long offlineMedicAt[8] = {0};

// Vest health & hidden failsafe (reported in every heartbeat)
const unsigned long STUCK_LOW_MS        = 500;  // Longest valid NEC low is 9ms
const unsigned long SENSOR_PROBE_MS     = 500;
const unsigned long BLASTER_PROBE_MS    = 2000;
const unsigned long PROBE_QUIET_MS      = 300;  // No probes right after firing
const int           PROBE_STRIKES       = 3;
const unsigned long FAULT_RECOVERY_MS   = 5000;
const unsigned long DOUBLE_HIT_WINDOW_MS = 150;
const unsigned long ASSIST_DECISION_MS  = 200;  // Waits for other vests' reports
const int           WITNESS_MARGIN_DB   = 3;    // Another vest must be this much stronger
const int           ASSIST_RSSI_MIN     = -65;  // dBm; rough "nearby" gate
const int           ASSIST_HIT_ODDS     = 3;    // 1 in 3

bool busStuckLow = false;
int  sensorOpenStrikes = 0;
bool sensorFaultLatched = false;
const char* sensorFaultName = "OK";
unsigned long lastSensorFaultAt = 0;
bool blasterOpen = false;
int  blasterOpenStrikes = 0;
bool refereeAssist = false;
bool espNowReady = false;
uint32_t assistHits = 0, assistMisses = 0, assistDoubles = 0, assistNotTarget = 0;
String lastDoublePair = "";
int pendingShooter = -1;

bool assistActive() { return sensorFaultLatched || refereeAssist; }
String sensorStatus() { return sensorFaultLatched ? String(sensorFaultName) : String("OK"); }

// Remaining time for server timers
long remaining(long serverMs) {
  if (ph == "PAUSED") return serverMs;
  long r = serverMs - (long)(millis() - stateAt);
  return r > 0 ? r : 0;
}

// ==========================================
//       NON-BLOCKING AUDIO SOUND ENGINE
// ==========================================

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

// Assigned from the server dashboard and saved to NVS. Active buzzers beep by themselves on DC.
bool buzzerActive = false;

void buzzerOff() {
  if (!buzzerActive) noTone(BUZZER_PIN);
  digitalWrite(BUZZER_PIN, LOW);
}

void startNote() {
  uint16_t f = currentMelody[melodyIdx].freq;
  uint16_t d = currentMelody[melodyIdx].dur;
  if (f > 0) {
    if (buzzerActive) {
      pinMode(BUZZER_PIN, OUTPUT);
      digitalWrite(BUZZER_PIN, HIGH); // Fixed pitch: melodies keep only their rhythm
    } else {
      tone(BUZZER_PIN, f, d);
    }
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

void displayPlayerHUD(int p) {
  // LEDs 1-4 count the gun number; LED 5 on means Red team
  int n = (p - 1) % 4 + 1;
  setHUD(n >= 1, n >= 2, n >= 3, n >= 4, p > 4);
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
const unsigned long FIRE_COOLDOWN_MS = 1000; // One shot per second, every mode

// True while this player is locked out of firing after taking a hit
bool isDisarmed() {
  if (isStandalone) return millis() < offlineDisarmUntil;
  return remaining(dsMs) > 0;
}

void fireWeapon() {
  uint32_t code = getMyShotCode();
  triggerMuzzleFlash();
  irsend.sendNEC(code, 32);
  lastShotAt = millis();
  broadcastShot();
  PLAY(M_SHOT, PRIO_GAMEPLAY);
  Serial.printf("[GUN] Node %s fired 0x%08X\n", nodeId.c_str(), code);
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

        if (now - lastShotAt >= FIRE_COOLDOWN_MS) {
          // Match live checks
          if (net == NET_OK && ph == "LIVE") {
            if (pst == "ALIVE" && remaining(rsMs) == 0) {
              if (isDisarmed()) PLAY(M_WARN, PRIO_GAMEPLAY);
              else fireWeapon();
            }
          } else if (isStandalone) {
            // Standalone mode: only fire when ALIVE and lives remain
            if (pst == "ALIVE" && lives > 0) {
              if (isDisarmed()) PLAY(M_WARN, PRIO_GAMEPLAY);
              else fireWeapon();
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
    hp = mhp;
    offlineShieldUntil = now + offlineShieldMs; // Respawn shield protection
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
  v = parseJson(js, "ds");   if (v.length()) dsMs = v.toInt();
  v = parseJson(js, "sds");  if (v.length()) offlineDisarmMs = v.toInt() * 1000UL;
  v = parseJson(js, "mid");  if (v.length()) matchId = v.toInt();
  v = parseJson(js, "srs");  if (v.length()) offlineRespawnMs = v.toInt() * 1000UL;
  v = parseJson(js, "spr");  if (v.length()) offlineShieldMs = v.toInt() * 1000UL;
  v = parseJson(js, "scd");  if (v.length()) offlineHitCooldownMs = v.toInt() * 1000UL;
  v = parseJson(js, "smd");  if (v.length()) offlineMedicMs = v.toInt() * 1000UL;
  v = parseJson(js, "ast");  if (v.length()) refereeAssist = (v == "1");
  v = parseJson(js, "bz");
  if (v.length() && (v == "1") != buzzerActive) {
    buzzerOff();
    currentMelody = nullptr;
    currentPriority = PRIO_IDLE;
    buzzerActive = (v == "1");
    prefs.putBool("buzzer_active", buzzerActive);
    Serial.printf("[BUZZER] Type set to %s\n", buzzerActive ? "ACTIVE" : "PASSIVE");
    PLAY(M_BOOT, PRIO_CRITICAL); // Confirmation beep from the newly assigned mode
  }
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

void journalAdd(uint32_t code, char kind, bool assisted) {
  if (!offlineMatch) return;
  if (journalCount == JOURNAL_LEN) { // Keep the newest; final HP and lives are sent separately
    memmove(journal, journal + 1, sizeof(JournalEntry) * (JOURNAL_LEN - 1));
    journalCount--;
  }
  uint8_t shooter = 0;
  for (int i = 0; i < 8; i++) if (PLAYER_CODES[i] == code) shooter = i;
  journal[journalCount++] = {journalNextId++, kind, shooter, assisted};
}

// Sends the offline journal; the journal stays until the server confirms it
bool syncOffline() {
  if (!offlineMatch) return true;
  String body = "{\"node_id\":\"" + nodeId + "\",\"boot\":" + String(bootNonce) + ",\"mid\":" + String(matchId) +
                ",\"hp\":" + String(hp) + ",\"lv\":" + String(lives) + ",\"st\":\"" + pst + "\"" +
                ",\"rs\":" + String(pst == "RESPAWN" && millis() < offlineRespawnAt ? offlineRespawnAt - millis() : 0) +
                ",\"pr\":" + String(millis() < offlineShieldUntil ? offlineShieldUntil - millis() : 0) +
                ",\"cd\":" + String(millis() < offlineCooldownUntil ? offlineCooldownUntil - millis() : 0) +
                ",\"ds\":" + String(millis() < offlineDisarmUntil ? offlineDisarmUntil - millis() : 0) + ",\"ev\":[";
  for (int i = 0; i < journalCount; i++) {
    if (i) body += ",";
    body += "[" + String(journal[i].id) + ",\"" + String(journal[i].kind) + "\"," + String(journal[i].shooter) + "," + String(journal[i].assist ? 1 : 0) + "]";
  }
  body += "]}";
  String resp;
  if (!postJson("/sync", body, resp)) return false;
  Serial.printf("[NET] Synced %d offline events\n", journalCount);
  journalCount = 0;
  offlineMatch = false;
  applyState(resp, "");
  return true;
}

bool sendHeartbeat() {
  if (!syncOffline()) return false;
  String body = "{\"node_id\":\"" + nodeId + "\",\"rssi\":" + String(WiFi.RSSI()) +
                ",\"s\":\"" + sensorStatus() + "\",\"b\":\"" + String(blasterOpen ? "OPEN" : "OK") +
                "\",\"en\":" + String(espNowReady ? 1 : 0) + ",\"a\":" + String(assistActive() ? 1 : 0) + ",\"bz\":" + String(buzzerActive ? 1 : 0) +
                ",\"ah\":" + String(assistHits) + ",\"am\":" + String(assistMisses) +
                ",\"an\":" + String(assistNotTarget) + ",\"ad\":" + String(assistDoubles) + ",\"dp\":\"" + lastDoublePair + "\"}";
  String resp;
  if (!postJson("/heartbeat", body, resp)) return false;
  applyState(resp, "");
  return true;
}

void sendHit(uint64_t code, bool assisted) {
  char hexBuf[20];
  snprintf(hexBuf, sizeof(hexBuf), "0x%llX", code);
  String body = "{\"node_id\":\"" + nodeId + "\",\"button_code\":\"" + String(hexBuf) + "\",\"assist\":" + String(assisted ? 1 : 0) + "}";
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
// Rescues a full NEC frame with exactly one damaged bit, only if it can match one player.
// Player codes differ by as little as 2 bits, so anything ambiguous is rejected.
uint32_t repairNecFrame(const decode_results& r) {
  if (r.rawlen < 67) return 0;
  uint32_t hdrMark = r.rawbuf[1] * kRawTick;
  uint32_t hdrSpace = r.rawbuf[2] * kRawTick;
  if (hdrMark < 4500 || hdrMark > 13500 || hdrSpace < 2000 || hdrSpace > 6500) return 0;
  uint32_t value = 0;
  for (int i = 0; i < 32; i++) {
    value = (value << 1) | ((r.rawbuf[4 + 2 * i] * kRawTick) > 1125 ? 1 : 0);
  }
  uint32_t match = 0;
  int matches = 0;
  for (int i = 0; i < 8; i++) {
    int distance = __builtin_popcount(value ^ PLAYER_CODES[i]);
    if (distance == 0) return PLAYER_CODES[i];
    if (distance == 1) {
      match = PLAYER_CODES[i];
      matches++;
    }
  }
  return matches == 1 ? match : 0;
}

void handleIR() {
  if (!irrecv.decode(&results)) return;
  uint64_t code = results.value;
  if (!isKnownPlayer((uint32_t)code)) {
    uint32_t repaired = repairNecFrame(results);
    if (repaired) {
      Serial.printf("[IR] Repaired damaged frame 0x%08X -> 0x%08X\n", (uint32_t)code, repaired);
      code = repaired;
    }
  }
  irrecv.resume();

  // Filter invalid codes, 32-bit and 64-bit NEC repeat codes
  if (code == 0 || (uint32_t)code == 0xFFFFFFFF || code == 0xFFFFFFFFFFFFFFFFULL) return;

  // A clean known code proves the sensor bus is alive
  if (isKnownPlayer((uint32_t)code)) markSensorsAlive();

  // Filter reflections of own shot
  if ((uint32_t)code == getMyShotCode()) return;

  claimShot((uint32_t)code); // Before any blocking HTTP call
  applyShot(code, false);
}

void applyShot(uint64_t code, bool assisted) {
  // Match live mode
  if (net == NET_OK && ph == "LIVE" && pst == "ALIVE") {
    if (!isKnownPlayer((uint32_t)code)) return;
    // Shield and hit cooldown only stop enemy shots; the server rules on teammates
    if (!isMyTeam((uint32_t)code) && (remaining(prMs) > 0 || remaining(cdMs) > 0)) {
      if (remaining(prMs) > 0) PLAY(M_SHIELD, PRIO_EVENT);
      return;
    }
    sendHit(code, assisted);
    return;
  }

  // Standalone / Offline mode referee
  if (isStandalone) {
    if (lives <= 0 || pst == "OUT") return;

    // A match that was live when the connection dropped still has its own clock
    if (offlineMatch && remaining(tmMs) == 0) return;

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
      journalAdd((uint32_t)code, 'D', assisted);

      hp--;
      offlineCooldownUntil = millis() + offlineHitCooldownMs;
      offlineDisarmUntil = millis() + offlineDisarmMs;

      if (hp > 0) {
        if (hp == 1) lastHeartbeatToneAt = 0;
        PLAY(M_HIT, PRIO_EVENT);
      } else {
        lives--;
        if (lives > 0) {
          pst = "RESPAWN";
          hp = 0;
          offlineRespawnAt = millis() + offlineRespawnMs;
          PLAY(M_DEATH, PRIO_CRITICAL);
        } else {
          pst = "OUT";
          hp = 0;
          lives = 0;
          PLAY(M_ELIM, PRIO_CRITICAL);
        }
      }
    } else {
      // Friendly medic heal! One per medic per cooldown, same as the server
      int medic = -1;
      for (int i = 0; i < 8; i++) if (PLAYER_CODES[i] == (uint32_t)code) medic = i;
      if (medic >= 0 && offlineMedicUsed[medic] && millis() - offlineMedicAt[medic] < offlineMedicMs) return;
      if (hp < mhp) {
        journalAdd((uint32_t)code, 'H', assisted);
        if (medic >= 0) {
          offlineMedicUsed[medic] = true;
          offlineMedicAt[medic] = millis();
        }
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
//       SENSOR & BLASTER SELF-CHECKS
// ==========================================
void markSensorsAlive() {
  sensorOpenStrikes = 0;
  sensorFaultLatched = false;
  pendingShooter = -1; // Same shot may also arrive over ESP-NOW
}

// Runs continuously: lobby, pre-match countdown and between shots in a match.
void updateVestHealth() {
  static unsigned long lowSince = 0;
  static uint32_t lowSamples = 0;
  static unsigned long lastSensorProbe = 0;
  static unsigned long lastBlasterProbe = 0;
  unsigned long now = millis();
  bool low = digitalRead(IR_RX_PIN) == LOW;

  // Stuck LOW: requires many consecutive samples so blocking HTTP calls can't fake it
  if (low) {
    if (lowSamples == 0) lowSince = now;
    lowSamples++;
  } else {
    lowSamples = 0;
  }
  busStuckLow = lowSamples >= 20 && (now - lowSince) >= STUCK_LOW_MS;

  bool quiet = (now - lastShotAt) >= PROBE_QUIET_MS;

  // Open bus: TSOP pull-ups beat the weak internal pull-down; a disconnected bus can't
  if (!low && quiet && now - lastSensorProbe >= SENSOR_PROBE_MS) {
    lastSensorProbe = now;
    gpio_set_pull_mode((gpio_num_t)IR_RX_PIN, GPIO_PULLDOWN_ONLY);
    delayMicroseconds(60);
    bool stillHigh = digitalRead(IR_RX_PIN) == HIGH;
    gpio_set_pull_mode((gpio_num_t)IR_RX_PIN, GPIO_PULLUP_ONLY);
    sensorOpenStrikes = stillHigh ? 0 : sensorOpenStrikes + 1;
  }

  bool open = sensorOpenStrikes >= PROBE_STRIKES;
  if (busStuckLow || open) {
    if (!sensorFaultLatched) Serial.printf("[HEALTH] Sensor bus fault: %s -> failsafe on\n", busStuckLow ? "STUCK_LOW" : "OPEN");
    sensorFaultLatched = true;
    sensorFaultName = busStuckLow ? "STUCK_LOW" : "OPEN";
    lastSensorFaultAt = now;
  } else if (sensorFaultLatched && now - lastSensorFaultAt >= FAULT_RECOVERY_MS) {
    sensorFaultLatched = false;
    Serial.println("[HEALTH] Sensor bus recovered -> failsafe off");
  }

  // Blaster: pull-up through a good LED sits near its forward voltage (reads LOW); an open LED reads HIGH
  if (quiet && now - lastBlasterProbe >= BLASTER_PROBE_MS) {
    lastBlasterProbe = now;
    pinMode(IR_LED_PIN, INPUT_PULLUP);
    delayMicroseconds(50);
    bool ledOpen = digitalRead(IR_LED_PIN) == HIGH;
    irsend.begin();
    blasterOpenStrikes = ledOpen ? blasterOpenStrikes + 1 : 0;
    bool nowOpen = blasterOpenStrikes >= PROBE_STRIKES;
    if (nowOpen != blasterOpen) Serial.printf("[HEALTH] Blaster %s\n", nowOpen ? "OPEN" : "OK");
    blasterOpen = nowOpen;
  }
}

// ==========================================
//     HIDDEN FAILSAFE (ESP-NOW PROXIMITY)
// ==========================================
const uint8_t BROADCAST_ADDR[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
const int SHOT_QUEUE_LEN = 16;
volatile ShotEvent shotQueue[SHOT_QUEUE_LEN];
volatile int shotHead = 0, shotTail = 0;
portMUX_TYPE shotMux = portMUX_INITIALIZER_UNLOCKED;
unsigned long lastEspNowInit = 0;
int espNowSendFails = 0;
const unsigned long ESPNOW_RETRY_MS = 5000;
const int ESPNOW_MAX_SEND_FAILS = 3;
uint16_t shotSeq = 0;
int32_t lastSeqSeen[8] = {-1, -1, -1, -1, -1, -1, -1, -1};
uint16_t pendingSeq = 0;
int pendingRssi = 0;
// This vest's signal report for each shooter's latest shot, sent after a random delay
bool reportWaiting[8] = {false};
unsigned long reportDueAt[8] = {0};
uint16_t reportSeq[8] = {0};
int8_t reportRssi[8] = {0};
// Strongest teammate report and latest real IR claim for each shooter
int32_t witnessSeq[8] = {-1, -1, -1, -1, -1, -1, -1, -1};
int witnessBest[8] = {0};
bool claimSeen[8] = {false};
unsigned long claimAt[8] = {0};
unsigned long pendingAt = 0;
bool pendingDouble = false;
String pendingPair = "";

void onShotPacket(const esp_now_recv_info_t* info, const uint8_t* data, int len) {
  ShotEvent e = {};
  if (len == sizeof(ShotPacket)) {
    ShotPacket p;
    memcpy(&p, data, sizeof(p));
    if (p.magic[0] != 'L' || p.magic[1] != 'T' || p.shooter >= 8) return;
    e.shooter = p.shooter;
    e.seq = p.seq;
    e.rssi = info->rx_ctrl ? info->rx_ctrl->rssi : -127;
  } else if (len == sizeof(WitnessPacket)) {
    WitnessPacket p;
    memcpy(&p, data, sizeof(p));
    if (p.magic[0] != 'L' || p.magic[1] != 'W' || p.shooter >= 8 || p.reporter >= 8) return;
    e.witness = true;
    e.claimed = p.claimed;
    e.reporter = p.reporter;
    e.shooter = p.shooter;
    e.seq = p.seq;
    e.rssi = p.rssi;
  } else {
    return;
  }
  portENTER_CRITICAL(&shotMux);
  int next = (shotHead + 1) % SHOT_QUEUE_LEN;
  if (next != shotTail) {
    shotQueue[shotHead].witness = e.witness;
    shotQueue[shotHead].claimed = e.claimed;
    shotQueue[shotHead].reporter = e.reporter;
    shotQueue[shotHead].shooter = e.shooter;
    shotQueue[shotHead].seq = e.seq;
    shotQueue[shotHead].rssi = e.rssi;
    shotQueue[shotHead].at = millis();
    shotHead = next;
  }
  portEXIT_CRITICAL(&shotMux);
}

void initEspNow() {
  lastEspNowInit = millis();
  espNowSendFails = 0;
  esp_now_deinit();
  if (esp_now_init() != ESP_OK) {
    Serial.println("[ESPNOW] Init failed, will retry");
    return;
  }
  esp_now_register_recv_cb(onShotPacket);
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, BROADCAST_ADDR, 6);
  peer.channel = 0; // Follow the current Wi-Fi channel
  peer.ifidx = WIFI_IF_STA;
  peer.encrypt = false;
  espNowReady = esp_now_add_peer(&peer) == ESP_OK;
  Serial.println(espNowReady ? "[ESPNOW] Ready" : "[ESPNOW] Peer failed, will retry");
}

// A send error means the radio link is unusable: mark it down so it restarts
void espNowSend(const uint8_t* data, size_t len) {
  if (esp_now_send(BROADCAST_ADDR, data, len) == ESP_OK) {
    espNowSendFails = 0;
  } else if (++espNowSendFails >= ESPNOW_MAX_SEND_FAILS) {
    espNowReady = false;
    Serial.println("[ESPNOW] Send failing, restarting radio");
  }
}

void updateEspNow() {
  if (!espNowReady && millis() - lastEspNowInit >= ESPNOW_RETRY_MS) initEspNow();
}

void broadcastShot() {
  if (!espNowReady) return;
  int me = nodeId.substring(1).toInt() - 1;
  if (me < 0 || me >= 8) return;
  ShotPacket p = {{'L', 'T'}, (uint8_t)me, shotSeq++};
  espNowSend((const uint8_t*)&p, sizeof(p));
}

void sendWitness(int shooter, uint16_t seq, int8_t rssi, bool claimed) {
  if (!espNowReady) return;
  int me = nodeId.substring(1).toInt() - 1;
  if (me < 0 || me >= 8) return;
  WitnessPacket p = {{'L', 'W'}, (uint8_t)me, (uint8_t)shooter, seq, rssi, (uint8_t)(claimed ? 1 : 0)};
  espNowSend((const uint8_t*)&p, sizeof(p));
}

// Tells failsafe vests this shot physically landed here
void claimShot(uint32_t code) {
  for (int i = 0; i < 8; i++) {
    if (PLAYER_CODES[i] == code) sendWitness(i, 0, 0, true);
  }
}

bool popShot(ShotEvent& e) {
  bool got = false;
  portENTER_CRITICAL(&shotMux);
  if (shotTail != shotHead) {
    e.witness = shotQueue[shotTail].witness;
    e.claimed = shotQueue[shotTail].claimed;
    e.reporter = shotQueue[shotTail].reporter;
    e.shooter = shotQueue[shotTail].shooter;
    e.seq = shotQueue[shotTail].seq;
    e.rssi = shotQueue[shotTail].rssi;
    e.at = shotQueue[shotTail].at;
    shotTail = (shotTail + 1) % SHOT_QUEUE_LEN;
    got = true;
  }
  portEXIT_CRITICAL(&shotMux);
  return got;
}

void updateAssist() {
  bool inGame = (net == NET_OK && ph == "LIVE" && pst == "ALIVE") ||
                (isStandalone && pst == "ALIVE" && lives > 0);
  bool armed = assistActive() && inGame;
  // Outside a match, working sensors just tick on any shot; match that so nothing gives it away
  bool testMode = assistActive() && !inGame && !isStandalone;
  if (!armed) pendingShooter = -1;

  ShotEvent e;
  while (popShot(e)) {
    if (e.witness) {
      if (e.claimed) {
        claimSeen[e.shooter] = true;
        claimAt[e.shooter] = e.at;
      } else if (isMyTeam(PLAYER_CODES[e.reporter])) {
        // Only teammates compete: the shooter's own side always sounds closer
        if (witnessSeq[e.shooter] != e.seq) {
          witnessSeq[e.shooter] = e.seq;
          witnessBest[e.shooter] = e.rssi;
        } else if (e.rssi > witnessBest[e.shooter]) {
          witnessBest[e.shooter] = e.rssi;
        }
      }
      continue;
    }
    if (lastSeqSeen[e.shooter] == e.seq) continue; // Duplicate packet
    lastSeqSeen[e.shooter] = e.seq;
    uint32_t code = PLAYER_CODES[e.shooter];
    if (code == getMyShotCode()) continue;
    if (inGame) {
      reportWaiting[e.shooter] = true;
      reportDueAt[e.shooter] = e.at + 5 + esp_random() % 40; // Spread out so reports don't collide
      reportSeq[e.shooter] = e.seq;
      reportRssi[e.shooter] = e.rssi;
    }
    if (!armed && !testMode) continue;
    if (e.rssi < ASSIST_RSSI_MIN) {
      Serial.printf("[ASSIST] P%d too far (%d dBm)\n", e.shooter + 1, e.rssi);
      continue;
    }
    if (testMode) {
      PLAY(M_TICK, PRIO_GAMEPLAY);
      continue;
    }
    if (pendingShooter < 0) {
      pendingShooter = e.shooter;
      pendingAt = e.at;
      pendingSeq = e.seq;
      pendingRssi = e.rssi;
      pendingDouble = false;
      pendingPair = "P" + String(e.shooter + 1);
    } else if (e.shooter != pendingShooter && e.at - pendingAt <= DOUBLE_HIT_WINDOW_MS) {
      pendingDouble = true;
      pendingPair += "+P" + String(e.shooter + 1);
    }
  }

  for (int i = 0; i < 8; i++) {
    if (reportWaiting[i] && (long)(millis() - reportDueAt[i]) >= 0) {
      reportWaiting[i] = false;
      sendWitness(i, reportSeq[i], reportRssi[i], false);
    }
  }

  // Decide once the window closes, so a second shooter or another vest can still cancel it
  if (pendingShooter < 0 || millis() - pendingAt <= ASSIST_DECISION_MS) return;
  int shooter = pendingShooter;
  pendingShooter = -1;

  if (pendingDouble) {
    assistDoubles++;
    lastDoublePair = pendingPair;
    Serial.printf("[ASSIST] Double hit %s: both ignored\n", pendingPair.c_str());
    return;
  }
  bool claimed = claimSeen[shooter] && labs((long)(claimAt[shooter] - pendingAt)) <= (long)ASSIST_DECISION_MS;
  bool outranked = witnessSeq[shooter] == pendingSeq && witnessBest[shooter] > pendingRssi + WITNESS_MARGIN_DB;
  if (claimed || outranked) {
    assistNotTarget++;
    Serial.printf("[ASSIST] P%d not aimed here (%s)\n", shooter + 1, claimed ? "real hit elsewhere" : "teammate closer");
    return;
  }
  if (esp_random() % ASSIST_HIT_ODDS == 0) {
    assistHits++;
    Serial.printf("[ASSIST] P%d counted as hit\n", shooter + 1);
    applyShot(PLAYER_CODES[shooter], true);
  } else {
    assistMisses++;
    Serial.printf("[ASSIST] P%d rolled miss\n", shooter + 1);
  }
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

// Carries a live match over to the gun's own rules, keeping HP, lives and timers exactly as they are
void enterOffline() {
  unsigned long now = millis();
  if (net == NET_OK && ph == "LIVE" && !offlineMatch) {
    offlineMatch = true;
    offlineRespawnAt = now + remaining(rsMs);
    offlineShieldUntil = now + remaining(prMs);
    offlineCooldownUntil = now + remaining(cdMs);
    offlineDisarmUntil = now + remaining(dsMs);
  }
  isStandalone = true;
}

void updateNetwork() {
  unsigned long now = millis();

  if (WiFi.status() != WL_CONNECTED) {
    udpListening = false;
    if (net == NET_OK || net == NET_DISCOVER) {
      enterOffline();
      net = NET_LOST;
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

  // Server never seen since boot: let the player play instead of waiting
  if (net == NET_DISCOVER && !haveState && !isStandalone && now > NO_SERVER_PLAY_AFTER_MS) {
    isStandalone = true;
    Serial.println("[NET] No server found -> Standalone Mode");
  }

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
        enterOffline();
        net = NET_LOST;
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
  irrecv.setTolerance(IR_TIMING_TOLERANCE);
  irrecv.enableIRIn(true); // Pull-up keeps a broken data wire from floating
  irsend.begin();

  bootNonce = esp_random() >> 1;

  // Player ID comes from GUN above; anything saved by older firmware is ignored
  prefs.begin("lasertag", false);
  buzzerActive = prefs.getBool("buzzer_active", false);
  Serial.printf("[BOOT] Gun: %s %d (%s)\n", nodeId.substring(1).toInt() > 4 ? "RED" : "BLUE",
                (nodeId.substring(1).toInt() - 1) % 4 + 1, nodeId.c_str());

  // Boot Chime & 5-LED Sweep
  PLAY(M_BOOT, PRIO_CRITICAL);

  // Briefly indicate player identity on HUD LEDs
  int pNum = nodeId.substring(1).toInt();
  if (pNum >= 1 && pNum <= 8) {
    displayPlayerHUD(pNum);
    delay(1500);
    setHUD(false, false, false, false, false);
  }

  // Load cached server IP with fallback to MANUAL_SERVER_IP
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

  initEspNow();

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
  updateVestHealth(); // Sensor bus & blaster self-checks
  updateEspNow();     // Restarts the radio link if it failed
  updateAssist();     // Hidden failsafe when the sensor bus is dead
  updateNetwork();    // Match server sync & auto-discovery
}
