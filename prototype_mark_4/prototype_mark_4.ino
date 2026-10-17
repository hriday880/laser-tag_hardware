// ==================================================================
//   LASER TAG - PROTOTYPE MARK 4
//   Same hardware as Mark 3. New: auto server discovery, heartbeat +
//   SERVER LOST mode, server-driven matches (lobby/countdown/live/
//   paused/game over), lives + respawn, LCD icons, melody player.
// ==================================================================
#include <Arduino.h>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRutils.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <HTTPClient.h>
#include <Preferences.h>

struct Note { uint16_t freq; uint16_t dur; };

// ==========================================
//          NETWORK CONFIGURATION
// ==========================================
const char* ssid = "Hriday";
const char* password = "12345678";
const char* NODE_ID = "P1";

// Optional: if your network blocks UDP broadcast, put the Mac IP here
// (e.g. "10.85.207.44"). Leave "" to rely on auto-discovery only.
const char* MANUAL_SERVER_IP = "";
const int SERVER_PORT = 5050;
const int DISCOVERY_PORT = 5051;

// ==========================================
//     BUZZER TYPE (run buzzer_test first)
// ==========================================
// false = active buzzer (fixed beep)   true = passive buzzer (real notes)
const bool BUZZER_PASSIVE = true;

// ==========================================
//               PIN DEFINITIONS
// ==========================================
const uint16_t IR_PIN = 14;
const int RED_PIN = 25;
const int GREEN_PIN = 26;
const int BLUE_PIN = 27;
const int BUZZER_PIN = 33;

// ==========================================
//      REMOTE CODES (same hex as Mark 1)
// ==========================================
#define BTN_1 0xFF30CF // Friend 1 (Medic)
#define BTN_2 0xFF18E7 // Friend 2 (Medic)
#define BTN_3 0xFF7A85 // Friend 3 (Medic)
#define BTN_4 0xFF10EF // Friend 4 (Medic)
#define BTN_5 0xFF38C7 // Enemy 1
#define BTN_6 0xFF5AA5 // Enemy 2
#define BTN_7 0xFF42BD // Enemy 3
#define BTN_8 0xFF4AB5 // Enemy 4
#define BTN_9 0xFF52AD // Enemy 5

bool isKnownCode(uint64_t c) {
  return c == BTN_1 || c == BTN_2 || c == BTN_3 || c == BTN_4 || c == BTN_5 ||
         c == BTN_6 || c == BTN_7 || c == BTN_8 || c == BTN_9;
}

IRrecv irrecv(IR_PIN);
decode_results results;
LiquidCrystal_I2C lcd(0x27, 16, 2);
WiFiUDP udp;
Preferences prefs;

// ==========================================
//         LCD CUSTOM ICONS (slots 1-7)
// ==========================================
#define IC_HEART  1
#define IC_EMPTY  2
#define IC_LIFE   3
#define IC_WIFI0  4
#define IC_WIFI1  5
#define IC_WIFI2  6
#define IC_WIFI3  7

byte iconHeartFull[8]  = {0b00000, 0b01010, 0b11111, 0b11111, 0b11111, 0b01110, 0b00100, 0b00000};
byte iconHeartEmpty[8] = {0b00000, 0b01010, 0b10101, 0b10001, 0b10001, 0b01010, 0b00100, 0b00000};
byte iconLife[8]       = {0b01110, 0b01110, 0b00100, 0b11111, 0b00100, 0b01010, 0b10001, 0b00000};
byte iconWifi0[8]      = {0b00000, 0b10001, 0b01010, 0b00100, 0b01010, 0b10001, 0b00000, 0b00000};
byte iconWifi1[8]      = {0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b10000, 0b10000};
byte iconWifi2[8]      = {0b00000, 0b00000, 0b00000, 0b00000, 0b00100, 0b00100, 0b10100, 0b10100};
byte iconWifi3[8]      = {0b00000, 0b00000, 0b00001, 0b00001, 0b00101, 0b00101, 0b10101, 0b10101};

// ==========================================
//             SERVER GAME STATE
// ==========================================
String ph = "LOBBY";      // LOBBY | COUNTDOWN | LIVE | PAUSED | GAMEOVER
String pst = "ALIVE";     // ALIVE | RESPAWN | OUT
int hp = 5, mhp = 5, lv = 3, mlv = 3, hitsTaken = 0, deaths = 0;
long tmMs = 0, rsMs = 0, prMs = 0, cdMs = 0;
String lastAttacker = "None", resultText = "", mvpText = "";
unsigned long stateAt = 0;
bool haveState = false;

// Network state machine
enum NetState { NET_DISCOVER, NET_OK, NET_LOST };
NetState net = NET_DISCOVER;
String serverIp = "";
int failCount = 0;
unsigned long lastHeartbeat = 0, lastProbe = 0, lastReconnect = 0, lostSince = 0;
const unsigned long HEARTBEAT_MS = 1000;

// LCD
String lcdCache[2] = {"", ""};
unsigned long overlayUntil = 0;
int lastCountdownSec = -1;

// LED
unsigned long lastLedToggle = 0;
bool ledToggle = false;
int rainbowStep = 0;

// ==========================================
//               HELPERS
// ==========================================
void setLED(bool r, bool g, bool b) {
  digitalWrite(RED_PIN, r);
  digitalWrite(GREEN_PIN, g);
  digitalWrite(BLUE_PIN, b);
}

// Only rewrites a row when its content changed (I2C writes are slow)
void printLCD(int row, String text) {
  while (text.length() < 16) text += " ";
  text = text.substring(0, 16);
  if (lcdCache[row] == text) return;
  lcdCache[row] = text;
  lcd.setCursor(0, row);
  lcd.print(text);
}

void showOverlay(String l1, String l2, unsigned long durMs) {
  if (l1.length() == 0 && l2.length() == 0) return;
  printLCD(0, l1);
  printLCD(1, l2);
  overlayUntil = millis() + durMs;
}

String centered(String s) {
  int pad = (16 - (int)s.length()) / 2;
  String out = "";
  for (int i = 0; i < pad; i++) out += " ";
  return out + s;
}

String mmss(long ms) {
  long s = (ms + 999) / 1000;
  char buf[8];
  sprintf(buf, "%02ld:%02ld", s / 60, s % 60);
  return String(buf);
}

// Lightweight JSON field parser (flat JSON, no external library)
String parseJson(const String& json, const String& key) {
  int keyIdx = json.indexOf("\"" + key + "\"");
  if (keyIdx == -1) return "";
  int colonIdx = json.indexOf(":", keyIdx);
  if (colonIdx == -1) return "";
  int startIdx = colonIdx + 1;
  while (startIdx < (int)json.length() && json[startIdx] == ' ') startIdx++;
  bool quoted = startIdx < (int)json.length() && json[startIdx] == '"';
  if (quoted) {
    int endQuote = json.indexOf('"', startIdx + 1);
    if (endQuote == -1) return "";
    return json.substring(startIdx + 1, endQuote);
  }
  int endIdx = startIdx;
  while (endIdx < (int)json.length() && json[endIdx] != ',' && json[endIdx] != '}') endIdx++;
  String v = json.substring(startIdx, endIdx);
  v.trim();
  return v;
}

// Remaining time for a server countdown (frozen while paused)
long remaining(long serverMs) {
  if (ph == "PAUSED") return serverMs;
  long r = serverMs - (long)(millis() - stateAt);
  return r > 0 ? r : 0;
}

// ==========================================
//      NON-BLOCKING MELODY PLAYER
// ==========================================

const Note M_BOOT[]     = {{523, 90}, {0, 30}, {659, 90}, {0, 30}, {784, 160}};
const Note M_TICK[]     = {{880, 90}};
const Note M_GO[]       = {{1047, 450}};
const Note M_HIT[]      = {{330, 110}, {0, 70}, {262, 140}};
const Note M_DEATH[]    = {{784, 180}, {0, 40}, {659, 180}, {0, 40}, {523, 180}, {0, 40}, {392, 450}};
const Note M_ELIM[]     = {{523, 300}, {0, 80}, {392, 300}, {0, 80}, {330, 300}, {0, 80}, {262, 700}};
const Note M_HEAL[]     = {{659, 100}, {0, 30}, {988, 220}};
const Note M_FF[]       = {{1200, 60}, {0, 50}, {1200, 60}, {0, 50}, {1200, 60}};
const Note M_TRAITOR[]  = {{900, 150}, {600, 150}, {900, 150}, {600, 150}, {900, 150}, {600, 300}};
const Note M_BLOCKED[]  = {{1500, 50}};
const Note M_RESPAWN[]  = {{392, 100}, {523, 100}, {659, 100}, {784, 220}};
const Note M_WIN[]      = {{523, 120}, {659, 120}, {784, 120}, {1047, 250}, {0, 60}, {784, 120}, {1047, 450}};
const Note M_LOSE[]     = {{392, 250}, {370, 250}, {349, 250}, {330, 600}};
const Note M_PAUSE[]    = {{600, 150}, {0, 60}, {400, 200}};
const Note M_RESUME[]   = {{400, 150}, {0, 60}, {600, 200}};
const Note M_LOST[]     = {{200, 400}};
const Note M_RECONNECT[]= {{600, 80}, {0, 40}, {900, 120}};
const Note M_RESET[]    = {{700, 100}, {0, 40}, {700, 100}};

#define PLAY(m) playMelody(m, sizeof(m) / sizeof(m[0]))

const Note* melody = nullptr;
int melodyLen = 0, melodyIdx = 0;
unsigned long noteEndsAt = 0;

void buzzerOff();

void buzzerOn(uint16_t freq) {
  if (freq == 0) { buzzerOff(); return; }
  if (BUZZER_PASSIVE) tone(BUZZER_PIN, freq);
  else digitalWrite(BUZZER_PIN, HIGH);
}

void buzzerOff() {
  if (BUZZER_PASSIVE) noTone(BUZZER_PIN);
  digitalWrite(BUZZER_PIN, LOW);
}

void startNote() {
  buzzerOn(melody[melodyIdx].freq);
  noteEndsAt = millis() + melody[melodyIdx].dur;
}

void playMelody(const Note* m, int len) {
  melody = m;
  melodyLen = len;
  melodyIdx = 0;
  startNote();
}

void updateSound() {
  if (!melody) return;
  if (millis() < noteEndsAt) return;
  melodyIdx++;
  if (melodyIdx >= melodyLen) {
    buzzerOff();
    melody = nullptr;
    return;
  }
  // Active buzzer: insert a tiny gap between back-to-back tones so they're distinguishable
  if (!BUZZER_PASSIVE && melody[melodyIdx].freq > 0 && melody[melodyIdx - 1].freq > 0) {
    buzzerOff();
    delayMicroseconds(800);
  }
  startNote();
}

// ==========================================
//          SERVER COMMUNICATION
// ==========================================
String serverUrl(const char* path) {
  return "http://" + serverIp + ":" + String(SERVER_PORT) + path;
}

// Returns true on HTTP 200; response body in `out`
bool postJson(const char* path, const String& body, String& out) {
  if (serverIp.length() == 0 || WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  http.setTimeout(400);       // keeps the game loop responsive
  http.setConnectTimeout(400);
  http.begin(serverUrl(path));
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(body);
  bool ok = (code == 200);
  if (ok) out = http.getString();
  http.end();
  return ok;
}

void applyState(const String& js, const String& ev, const String& l1, const String& l2);

bool sendHeartbeat() {
  String body = "{\"node_id\":\"" + String(NODE_ID) + "\",\"rssi\":" + String(WiFi.RSSI()) + "}";
  String resp;
  if (!postJson("/heartbeat", body, resp)) return false;
  applyState(resp, "", "", "");
  return true;
}

void rememberServer(const String& ip) {
  serverIp = ip;
  prefs.putString("srv", ip);
}

void enterNetOk() {
  if (net == NET_LOST) {
    PLAY(M_RECONNECT);
    showOverlay("  RECONNECTED!", "Server " + serverIp, 1500);
  }
  net = NET_OK;
  failCount = 0;
  Serial.println("[NET] Server OK at " + serverIp);
}

void enterNetLost() {
  net = NET_LOST;
  lostSince = millis();
  PLAY(M_LOST);
  Serial.println("[NET] SERVER LOST");
}

// Listens for "LASERTAG <port>" broadcasts from server.py
bool checkDiscovery() {
  int size = udp.parsePacket();
  if (size <= 0) return false;
  char buf[32];
  int n = udp.read(buf, sizeof(buf) - 1);
  buf[n > 0 ? n : 0] = 0;
  if (strncmp(buf, "LASERTAG", 8) != 0) return false;
  String ip = udp.remoteIP().toString();
  if (ip == serverIp && net == NET_OK) return false;
  Serial.println("[NET] Discovered server at " + ip);
  String old = serverIp;
  serverIp = ip;
  if (sendHeartbeat()) {
    rememberServer(ip);
    enterNetOk();
    return true;
  }
  serverIp = old;
  return false;
}

// Tries cached / manual server addresses
bool probeKnownServers() {
  String candidates[2] = { prefs.getString("srv", ""), String(MANUAL_SERVER_IP) };
  for (int i = 0; i < 2; i++) {
    if (candidates[i].length() == 0) continue;
    serverIp = candidates[i];
    if (sendHeartbeat()) {
      rememberServer(serverIp);
      enterNetOk();
      return true;
    }
  }
  return false;
}

void updateNetwork() {
  unsigned long now = millis();

  // Wi-Fi dropped: keep trying to rejoin (game stays frozen meanwhile)
  if (WiFi.status() != WL_CONNECTED) {
    if (net == NET_OK) enterNetLost();
    if (now - lastReconnect > 5000) {
      lastReconnect = now;
      Serial.println("[NET] Wi-Fi down, reconnecting...");
      WiFi.reconnect();
    }
    return;
  }

  // Broadcasts are checked in every state (handles server IP changes too)
  if (checkDiscovery()) return;

  switch (net) {
    case NET_DISCOVER:
      if (now - lastProbe > 3000) {
        lastProbe = now;
        probeKnownServers();
      }
      break;

    case NET_OK:
      if (now - lastHeartbeat > HEARTBEAT_MS) {
        lastHeartbeat = now;
        if (sendHeartbeat()) {
          failCount = 0;
        } else if (++failCount >= 3) {
          enterNetLost();
        }
      }
      break;

    case NET_LOST:
      if (now - lastProbe > 1500) {
        lastProbe = now;
        if (sendHeartbeat()) enterNetOk();
      }
      break;
  }
}

// ==========================================
//     APPLY AUTHORITATIVE SERVER STATE
// ==========================================
void applyState(const String& js, const String& ev, const String& l1, const String& l2) {
  String prevPh = ph, prevSt = pst;
  bool first = !haveState;

  String v;
  v = parseJson(js, "ph");   if (v.length()) ph = v;
  v = parseJson(js, "st");   if (v.length()) pst = v;
  v = parseJson(js, "hp");   if (v.length()) hp = v.toInt();
  v = parseJson(js, "mhp");  if (v.length()) mhp = v.toInt();
  v = parseJson(js, "lv");   if (v.length()) lv = v.toInt();
  v = parseJson(js, "mlv");  if (v.length()) mlv = v.toInt();
  v = parseJson(js, "tm");   if (v.length()) tmMs = v.toInt();
  v = parseJson(js, "rs");   if (v.length()) rsMs = v.toInt();
  v = parseJson(js, "pr");   if (v.length()) prMs = v.toInt();
  v = parseJson(js, "cd");   if (v.length()) cdMs = v.toInt();
  v = parseJson(js, "ht");   if (v.length()) hitsTaken = v.toInt();
  v = parseJson(js, "dt");   if (v.length()) deaths = v.toInt();
  lastAttacker = parseJson(js, "last");
  resultText = parseJson(js, "res");
  mvpText = parseJson(js, "mvp");
  stateAt = millis();
  haveState = true;

  if (first) return;  // no sounds for the very first sync

  // ---- Phase / player transitions (highest priority sounds) ----
  bool played = false;
  if (ph != prevPh) {
    if (ph == "LOBBY") {
      PLAY(M_RESET); showOverlay("  ARENA RESET", " Back to lobby", 1500); played = true;
    } else if (ph == "LIVE" && prevPh == "COUNTDOWN") {
      PLAY(M_GO); showOverlay("     GO! GO!", "  Match is LIVE", 1200); played = true;
    } else if (ph == "PAUSED") {
      PLAY(M_PAUSE); played = true;
    } else if (prevPh == "PAUSED") {
      PLAY(M_RESUME); played = true;
    } else if (ph == "GAMEOVER") {
      if (resultText == "YOU SURVIVED!") PLAY(M_WIN); else PLAY(M_LOSE);
      played = true;
    }
    if (ph == "COUNTDOWN") lastCountdownSec = -1;
  }

  if (pst != prevSt) {
    if (pst == "RESPAWN") { PLAY(M_DEATH); played = true; }
    else if (pst == "OUT") { PLAY(M_ELIM); played = true; }
    else if (pst == "ALIVE" && prevSt == "RESPAWN") {
      PLAY(M_RESPAWN); showOverlay("  RESPAWNED!", "Spawn shield ON", 1500); played = true;
    }
  }

  // ---- Hit events from /hit response ----
  if (ev.length()) {
    showOverlay(l1, l2, 2200);
    if (!played) {
      if (ev == "HIT") PLAY(M_HIT);
      else if (ev == "HEAL") PLAY(M_HEAL);
      else if (ev == "FF") PLAY(M_FF);
      else if (ev == "TRAITOR") PLAY(M_TRAITOR);
      else if (ev == "BLOCKED" || ev == "FULL") PLAY(M_BLOCKED);
    }
  }
}

// ==========================================
//              IR HANDLING
// ==========================================
void sendHit(uint64_t code) {
  char hexBuffer[20];
  sprintf(hexBuffer, "0x%llX", code);
  String body = "{\"node_id\":\"" + String(NODE_ID) + "\",\"button_code\":\"" + String(hexBuffer) + "\"}";
  Serial.println("[IR] Sending " + String(hexBuffer));

  String resp;
  if (postJson("/hit", body, resp)) {
    Serial.println("[NET] " + resp);
    applyState(resp, parseJson(resp, "ev"), parseJson(resp, "l1"), parseJson(resp, "l2"));
    lastHeartbeat = millis();  // the hit doubled as a heartbeat
    failCount = 0;
  } else {
    Serial.println("[NET] Hit failed to reach server");
    if (++failCount >= 3) enterNetLost();
  }
}

void handleIR() {
  if (!irrecv.decode(&results)) return;
  uint64_t code = results.value;
  irrecv.resume();

  if (code == 0xFFFFFFFF || code == 0 || !isKnownCode(code)) return;  // repeats / noise
  if (net != NET_OK) return;                    // no offline play
  if (ph != "LIVE" || pst != "ALIVE") return;    // only during a live match

  // Server also enforces these; skipping here saves a round-trip
  bool isFriend = (code == BTN_1 || code == BTN_2 || code == BTN_3 || code == BTN_4);
  if (!isFriend && (remaining(prMs) > 0 || remaining(cdMs) > 0)) {
    if (remaining(prMs) > 0) { PLAY(M_BLOCKED); showOverlay("SPAWN SHIELD", "Shot blocked!", 1000); }
    return;
  }
  sendHit(code);
}

// ==========================================
//                 DISPLAY
// ==========================================
char wifiIcon() {
  if (WiFi.status() != WL_CONNECTED) return (char)IC_WIFI0;
  long r = WiFi.RSSI();
  if (r > -60) return (char)IC_WIFI3;
  if (r > -70) return (char)IC_WIFI2;
  if (r > -80) return (char)IC_WIFI1;
  return (char)IC_WIFI0;
}

String hpBar() {
  if (mhp > 5) return "HP" + String(hp) + "/" + String(mhp);
  String s = "";
  for (int i = 0; i < mhp; i++) s += (char)(i < hp ? IC_HEART : IC_EMPTY);
  return s;
}

// Left text + right text, padded to exactly 16 columns
String lr(String left, String right) {
  int gap = 16 - (int)left.length() - (int)right.length();
  if (gap < 1) gap = 1;
  String s = left;
  for (int i = 0; i < gap; i++) s += " ";
  return s + right;
}

void updateDisplay() {
  if (millis() < overlayUntil) return;
  bool alt = (millis() / 2500) % 2;

  if (net == NET_DISCOVER) {
    printLCD(0, lr("Finding server", String(wifiIcon())));
    printLCD(1, "IP " + WiFi.localIP().toString());
    return;
  }
  if (net == NET_LOST) {
    printLCD(0, centered("SERVER LOST"));
    if (WiFi.status() != WL_CONNECTED) printLCD(1, centered("Wi-Fi down..."));
    else printLCD(1, centered("Reconnecting " + String((millis() - lostSince) / 1000) + "s"));
    return;
  }

  if (ph == "LOBBY") {
    printLCD(0, lr("LOBBY  " + String(NODE_ID), String(wifiIcon())));
    printLCD(1, alt ? String("Waiting start...") : String("HP") + String(mhp) + " Lives" + String(mlv) + " " + mmss(tmMs));
  }
  else if (ph == "COUNTDOWN") {
    int sec = (remaining(tmMs) + 999) / 1000;
    if (sec != lastCountdownSec && sec > 0) { lastCountdownSec = sec; PLAY(M_TICK); }
    printLCD(0, centered("MATCH STARTS IN"));
    printLCD(1, centered(String(sec > 0 ? sec : 1)));
  }
  else if (ph == "PAUSED") {
    printLCD(0, centered("GAME PAUSED"));
    printLCD(1, centered("Time left " + mmss(tmMs)));
  }
  else if (ph == "GAMEOVER") {
    if (!alt) {
      printLCD(0, centered("== GAME OVER =="));
      printLCD(1, centered(resultText));
    } else {
      printLCD(0, "MVP: " + mvpText);
      printLCD(1, "Hits" + String(hitsTaken) + " Deaths" + String(deaths));
    }
  }
  else if (ph == "LIVE") {
    String timer = String(wifiIcon()) + mmss(remaining(tmMs));
    if (pst == "OUT") {
      printLCD(0, "== ELIMINATED ==");
      printLCD(1, "By: " + lastAttacker);
    } else if (pst == "RESPAWN") {
      printLCD(0, lr("YOU DIED! " + String((char)IC_LIFE) + String(lv), ""));
      printLCD(1, "Respawn in " + String((remaining(rsMs) + 999) / 1000) + "s");
    } else {
      printLCD(0, lr(hpBar() + " " + String((char)IC_LIFE) + String(lv), timer));
      long pr = remaining(prMs), cd = remaining(cdMs);
      if (pr > 0)                    printLCD(1, "SPAWN SHIELD " + String((pr + 999) / 1000) + "s");
      else if (cd > 0)               printLCD(1, "Recovering.. " + String((cd + 999) / 1000) + "s");
      else if (lv == 1 && mlv > 1 && alt) printLCD(1, centered("!! LAST LIFE !!"));
      else                           printLCD(1, "Last: " + lastAttacker);
    }
  }
}

// ==========================================
//                  LEDS
// ==========================================
bool blink(unsigned long periodMs) { return (millis() / periodMs) % 2; }

void updateLEDs() {
  if (net == NET_DISCOVER) { setLED(LOW, LOW, blink(500)); return; }
  if (net == NET_LOST)     { bool b = blink(300); setLED(b, LOW, !b); return; }

  if (ph == "LOBBY")     { setLED(LOW, LOW, HIGH); return; }
  if (ph == "COUNTDOWN") { bool b = blink(250); setLED(b, b, b); return; }
  if (ph == "PAUSED")    { setLED(HIGH, LOW, HIGH); return; }
  if (ph == "GAMEOVER") {
    if (resultText == "YOU SURVIVED!") {
      int step = (millis() / 200) % 6;   // rainbow cycle
      const bool c[6][3] = {{1,0,0},{1,1,0},{0,1,0},{0,1,1},{0,0,1},{1,0,1}};
      setLED(c[step][0], c[step][1], c[step][2]);
    } else {
      setLED(HIGH, LOW, LOW);
    }
    return;
  }

  // LIVE
  if (pst == "OUT")     { setLED(HIGH, LOW, LOW); return; }
  if (pst == "RESPAWN") { setLED(blink(500), LOW, LOW); return; }
  if (remaining(prMs) > 0) { bool b = blink(150); setLED(b, b, b); return; }
  if (remaining(cdMs) > 0) { bool b = blink(250); setLED(b, b, b); return; }
  if (hp * 5 >= mhp * 4)      setLED(LOW, HIGH, LOW);   // green
  else if (hp * 5 >= mhp * 2) setLED(HIGH, HIGH, LOW);  // yellow
  else                        setLED(blink(350), LOW, LOW); // pulsing red
}

// ==========================================
//                 SETUP
// ==========================================
void setup() {
  Serial.begin(115200);

  pinMode(RED_PIN, OUTPUT);
  pinMode(GREEN_PIN, OUTPUT);
  pinMode(BLUE_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  lcd.init();
  lcd.backlight();
  lcd.createChar(IC_HEART, iconHeartFull);
  lcd.createChar(IC_EMPTY, iconHeartEmpty);
  lcd.createChar(IC_LIFE,  iconLife);
  lcd.createChar(IC_WIFI0, iconWifi0);
  lcd.createChar(IC_WIFI1, iconWifi1);
  lcd.createChar(IC_WIFI2, iconWifi2);
  lcd.createChar(IC_WIFI3, iconWifi3);
  lcd.clear();
  lcdCache[0] = lcdCache[1] = "";

  prefs.begin("lasertag", false);

  setLED(LOW, LOW, HIGH);
  printLCD(0, "LaserTag Mark 4");
  printLCD(1, "Connecting WiFi");

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);          // CRITICAL: modem sleep breaks IR timing
  WiFi.setAutoReconnect(true);
  WiFi.begin(ssid, password);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(400);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() != WL_CONNECTED) {
    // Connection failed mode: never start an offline game
    Serial.println("\n[SETUP] WiFi Failed! Halting.");
    printLCD(0, "NETWORK ERROR");
    printLCD(1, "Please Restart");
    while (true) {
      setLED(HIGH, LOW, LOW); delay(500);
      setLED(LOW, LOW, LOW);  delay(500);
    }
  }

  Serial.println("\n[SETUP] WiFi connected: " + WiFi.localIP().toString());
  printLCD(0, "WiFi Connected!");
  printLCD(1, WiFi.localIP().toString());

  udp.begin(DISCOVERY_PORT);

  // CRITICAL: IR must be enabled AFTER Wi-Fi is up (radio init resets timers)
  irrecv.enableIRIn();

  PLAY(M_BOOT);
  net = NET_DISCOVER;
  probeKnownServers();   // instant reconnect if we remember the server
}

// ==========================================
//               MAIN LOOP
// ==========================================
void loop() {
  updateSound();
  handleIR();
  updateNetwork();
  handleIR();          // check again right after any network wait
  updateDisplay();
  updateLEDs();
}

