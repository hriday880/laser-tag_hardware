#include <Arduino.h>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRutils.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <WiFi.h>
#include <HTTPClient.h>

// ==========================================
//          NETWORK CONFIGURATION
// ==========================================
const char* ssid = "Hriday";
const char* password = "12345678";
const char* serverUrl = "http://10.85.207.44:5050/hit";

// ==========================================
//               PIN DEFINITIONS
// ==========================================
const uint16_t IR_PIN = 14;      
const int RED_PIN = 25;          
const int GREEN_PIN = 26;        
const int BLUE_PIN = 27;         
const int BUZZER_PIN = 33;       

// ==========================================
//               REMOTE CODES
// ==========================================
#define BTN_1 0xFF30CF // Shield P1
#define BTN_2 0xFF18E7 // Shield P2
#define BTN_3 0xFF7A85 // Medkit (+1 HP)
#define BTN_4 0xFF10EF // EMP Stun
#define BTN_5 0xFF38C7 // Sniper (2 DMG)
#define BTN_6 0xFF5AA5 // Laser Rifle (1 DMG)
#define BTN_7 0xFF42BD // Player 3 (1 DMG)
#define BTN_8 0xFF4AB5 // Alpha Team (1 DMG)
#define BTN_9 0xFF52AD // Boss Rocket (3 DMG)

IRrecv irrecv(IR_PIN);
decode_results results;
LiquidCrystal_I2C lcd(0x27, 16, 2); 

// ==========================================
//            GAME STATE VARIABLES
// ==========================================
int maxHP = 5;
int currentHP = 5;
bool isEliminated = false;
String lastAttacker = "None";

// Non-blocking Timers
unsigned long cooldownUntil = 0;
unsigned long shieldUntil = 0;
unsigned long stunnedUntil = 0;
unsigned long tempLcdUntil = 0;

// Non-blocking Buzzer Pattern Player
int buzzerRemainingBeeps = 0;
unsigned long buzzerNextToggle = 0;
bool buzzerState = false;
int buzzerOnDuration = 100;
int buzzerOffDuration = 100;

// Non-blocking LED Animation
unsigned long lastLedPulse = 0;
bool ledPulseState = false;

// Helpers
void setLED(bool r, bool g, bool b) {
  digitalWrite(RED_PIN, r);
  digitalWrite(GREEN_PIN, g);
  digitalWrite(BLUE_PIN, b);
}

void printLCD(int col, int row, String text) {
  lcd.setCursor(col, row);
  while(text.length() < 16) { text += " "; }
  lcd.print(text.substring(0, 16));
}

void triggerBuzzerPattern(int beeps, int onTimeMs, int offTimeMs) {
  buzzerRemainingBeeps = beeps;
  buzzerOnDuration = onTimeMs;
  buzzerOffDuration = offTimeMs;
  buzzerState = true;
  digitalWrite(BUZZER_PIN, HIGH);
  buzzerNextToggle = millis() + onTimeMs;
}

void updateBuzzer() {
  if (buzzerRemainingBeeps <= 0) return;
  
  unsigned long now = millis();
  if (now >= buzzerNextToggle) {
    if (buzzerState) {
      // Turn OFF
      digitalWrite(BUZZER_PIN, LOW);
      buzzerState = false;
      buzzerRemainingBeeps--;
      if (buzzerRemainingBeeps > 0) {
        buzzerNextToggle = now + buzzerOffDuration;
      }
    } else {
      // Turn ON for next beep
      digitalWrite(BUZZER_PIN, HIGH);
      buzzerState = true;
      buzzerNextToggle = now + buzzerOnDuration;
    }
  }
}

void updateLEDs() {
  unsigned long now = millis();

  if (isEliminated) {
    setLED(HIGH, LOW, LOW); // Solid Red on death
    return;
  }

  // Active Shield: Cyan (Green + Blue)
  if (now < shieldUntil) {
    setLED(LOW, HIGH, HIGH);
    return;
  }

  // Stunned: Amber/Yellow Flashing
  if (now < stunnedUntil) {
    if (now - lastLedPulse > 150) {
      lastLedPulse = now;
      ledPulseState = !ledPulseState;
      setLED(ledPulseState, ledPulseState, LOW);
    }
    return;
  }

  // Cooldown Grace Period: Flashing White
  if (now < cooldownUntil) {
    if (now - lastLedPulse > 200) {
      lastLedPulse = now;
      ledPulseState = !ledPulseState;
      setLED(ledPulseState, ledPulseState, ledPulseState);
    }
    return;
  }

  // Normal Health-based LED
  if (currentHP >= 4) {
    setLED(LOW, HIGH, LOW); // Green
  } else if (currentHP >= 2) {
    setLED(HIGH, HIGH, LOW); // Yellow
  } else {
    // Critical (1 HP): Pulsing Red
    if (now - lastLedPulse > 350) {
      lastLedPulse = now;
      ledPulseState = !ledPulseState;
      setLED(ledPulseState, LOW, LOW);
    }
  }
}

void updateDefaultDisplay() {
  if (millis() < tempLcdUntil) return;

  if (isEliminated) {
    printLCD(0, 0, "=== ELIMINATED ==");
    printLCD(0, 1, "By: " + lastAttacker);
    return;
  }

  if (millis() < shieldUntil) {
    int sLeft = (shieldUntil - millis()) / 1000 + 1;
    printLCD(0, 0, "SHIELD ACTIVE!");
    printLCD(0, 1, "Time Left: " + String(sLeft) + "s");
    return;
  }

  if (millis() < stunnedUntil) {
    int sLeft = (stunnedUntil - millis()) / 1000 + 1;
    printLCD(0, 0, "! EMP STUNNED !");
    printLCD(0, 1, "Disabled: " + String(sLeft) + "s");
    return;
  }

  // Standard HUD
  String hpBar = "HP: " + String(currentHP) + "/" + String(maxHP);
  printLCD(0, 0, hpBar + "  NODE:P1");
  printLCD(0, 1, "Last: " + lastAttacker);
}

// Lightweight JSON field parser (zero external library required)
String parseJson(String json, String key) {
  int keyIdx = json.indexOf("\"" + key + "\"");
  if (keyIdx == -1) return "";
  int colonIdx = json.indexOf(":", keyIdx);
  if (colonIdx == -1) return "";
  int startIdx = colonIdx + 1;
  while (startIdx < json.length() && (json[startIdx] == ' ' || json[startIdx] == '\"')) {
    startIdx++;
  }
  int endIdx = startIdx;
  while (endIdx < json.length() && json[endIdx] != '\"' && json[endIdx] != ',' && json[endIdx] != '}') {
    endIdx++;
  }
  return json.substring(startIdx, endIdx);
}

// ==========================================
//          SERVER COMMUNICATION
// ==========================================
void sendHitToServer(uint64_t code) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[NET] WiFi not connected");
    return;
  }

  HTTPClient http;
  http.setTimeout(400); // 400ms max timeout so game loop remains non-blocking
  http.begin(serverUrl);
  http.addHeader("Content-Type", "application/json");

  // Format hex string for server
  char hexBuffer[20];
  sprintf(hexBuffer, "0x%llX", code);

  String payload = "{\"node_id\":\"P1\",\"button_code\":\"" + String(hexBuffer) + "\"}";
  Serial.print("[NET] Sending: ");
  Serial.println(payload);

  int httpCode = http.POST(payload);

  if (httpCode == 200) {
    String response = http.getString();
    Serial.println("[NET] Server Response: " + response);

    // Extract authoritative referee data from server
    String eventType = parseJson(response, "event_type");
    String attacker = parseJson(response, "attacker");
    String hpStr = parseJson(response, "current_hp");
    String elimStr = parseJson(response, "is_eliminated");
    String line1 = parseJson(response, "lcd_line1");
    String line2 = parseJson(response, "lcd_line2");

    if (hpStr.length() > 0) currentHP = hpStr.toInt();
    if (elimStr == "true") isEliminated = true;
    if (attacker.length() > 0) lastAttacker = attacker;

    // Temporary alert on LCD
    if (line1.length() > 0) printLCD(0, 0, line1);
    if (line2.length() > 0) printLCD(0, 1, line2);
    tempLcdUntil = millis() + 2500;

    // React to authoritative event
    if (isEliminated) {
      triggerBuzzerPattern(4, 300, 150);
    } else if (eventType == "DAMAGE") {
      triggerBuzzerPattern(2, 120, 80);
      cooldownUntil = millis() + 3000; // 3-second non-blocking cooldown grace period
    } else if (eventType == "HEAL") {
      triggerBuzzerPattern(1, 400, 100);
    } else if (eventType == "SHIELD") {
      shieldUntil = millis() + 4000; // 4 seconds of invulnerability
      triggerBuzzerPattern(3, 80, 60);
    } else if (eventType == "STUN") {
      stunnedUntil = millis() + 3000;
      triggerBuzzerPattern(5, 60, 40);
    } else if (eventType == "BLOCKED") {
      triggerBuzzerPattern(1, 80, 50);
    }
  } else {
    Serial.print("[NET] HTTP failed, code: ");
    Serial.println(httpCode);
  }

  http.end();
}

void pollStatusFromServer() {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  http.setTimeout(400); 

  String statusUrl = String(serverUrl);
  statusUrl.replace("/hit", "/status");
  
  http.begin(statusUrl);
  int httpCode = http.GET();
  
  if (httpCode == 200) {
    String response = http.getString();
    String elimStr = parseJson(response, "is_eliminated");
    String hpStr = parseJson(response, "current_hp");
    
    if (elimStr == "false") {
      isEliminated = false;
      if (hpStr.length() > 0) currentHP = hpStr.toInt();
      lastAttacker = "None"; // Clear last attacker
      
      printLCD(0, 0, "=== GAME RESET =");
      printLCD(0, 1, "Player Revived! ");
      tempLcdUntil = millis() + 2500;
      triggerBuzzerPattern(2, 200, 100);
      Serial.println("[NET] Polled status: Game reset by server.");
    }
  }
  http.end();
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

  lcd.init();
  lcd.backlight();
  setLED(LOW, LOW, HIGH); // Blue during boot

  printLCD(0, 0, "LaserTag Mark 3");
  printLCD(0, 1, "Connecting WiFi");

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false); // Disable modem sleep for maximum IR responsiveness
  WiFi.begin(ssid, password);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(400);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[SETUP] WiFi connected!");
    printLCD(0, 0, "WiFi Connected!");
    printLCD(0, 1, WiFi.localIP().toString());
    delay(1500);
  } else {
    Serial.println("\n[SETUP] WiFi Failed! Halting.");
    printLCD(0, 0, "NETWORK ERROR   ");
    printLCD(0, 1, "Please Restart  ");
    
    // Fatal Error Loop: Blink RED forever, never start the game
    while (true) {
      setLED(HIGH, LOW, LOW);
      delay(500);
      setLED(LOW, LOW, LOW);
      delay(500);
    }
  }

  // Initialize IR AFTER Wi-Fi to keep hardware timers pristine
  irrecv.enableIRIn();

  setLED(LOW, HIGH, LOW);
  updateDefaultDisplay();
  triggerBuzzerPattern(1, 150, 0); // Boot chime
}

// ==========================================
//               MAIN LOOP
// ==========================================
unsigned long lastStatusPoll = 0;

void loop() {
  // Always service non-blocking hardware subsystems
  updateBuzzer();
  updateLEDs();
  updateDefaultDisplay();

  if (isEliminated) {
    // Only poll the server every 2 seconds when eliminated to check for a reset
    if (millis() - lastStatusPoll > 2000) {
      lastStatusPoll = millis();
      pollStatusFromServer();
    }
    return;
  }

  // Process incoming IR signals
  if (irrecv.decode(&results)) {
    uint64_t code = results.value;

    // Ignore repeat codes (held button) & zero reads
    if (code == 0xFFFFFFFF || code == 0) {
      irrecv.resume();
      return;
    }

    unsigned long now = millis();

    // Check if player is currently in cooldown or shielded
    if (now < cooldownUntil) {
      Serial.println("[IR] Attack ignored: Node is in cooldown grace period");
      irrecv.resume();
      return;
    }

    if (now < shieldUntil && (code >= BTN_5 && code <= BTN_9)) {
      Serial.println("[IR] Attack DEFLECTED by active shield!");
      printLCD(0, 0, "ATTACK DEFLECTED");
      printLCD(0, 1, "Shield Absorb!");
      tempLcdUntil = now + 1500;
      triggerBuzzerPattern(1, 60, 0);
      irrecv.resume();
      return;
    }

    // Valid signal: Forward to server referee
    sendHitToServer(code);

    irrecv.resume();
  }
}
