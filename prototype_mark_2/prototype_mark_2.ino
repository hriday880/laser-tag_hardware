#include <Arduino.h>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRutils.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <WiFi.h>
#include <HTTPClient.h>

// --- NETWORK CONFIGURATION ---
// Update these with your phone hotspot credentials
const char* ssid = "Hriday";
const char* password = "12345678";

// Replace with the IP address printed by server.py
const char* serverUrl = "http://10.85.207.44:5050/hit";


// --- PIN SETUP ---
const uint16_t IR_PIN = 14;      
const int RED_PIN = 25;          
const int GREEN_PIN = 26;        
const int BLUE_PIN = 27;         
const int BUZZER_PIN = 33;       

LiquidCrystal_I2C lcd(0x27, 16, 2); 

// --- YOUR RECORDED REMOTE CODES ---
#define BTN_1 0xFF30CF
#define BTN_2 0xFF18E7
#define BTN_3 0xFF7A85
#define BTN_4 0xFF10EF
#define BTN_5 0xFF38C7
#define BTN_6 0xFF5AA5
#define BTN_7 0xFF42BD
#define BTN_8 0xFF4AB5
#define BTN_9 0xFF52AD

IRrecv irrecv(IR_PIN);
decode_results results;

int maxLives = 5;
int hitCount = 0;
bool isEliminated = false;

String getAttackerName(uint64_t code) {
  switch(code) {
    case BTN_1: return "Shield P1";
    case BTN_2: return "Shield P2";
    case BTN_3: return "Medkit";
    case BTN_4: return "Deflect";
    case BTN_5: return "Sniper Bob";
    case BTN_6: return "Laser Rifle";
    case BTN_7: return "Player 3";
    case BTN_8: return "Alpha Team";
    case BTN_9: return "Boss Enemy";
    default: return "Unknown";
  }
}

void setLED(bool r, bool g, bool b) {
  digitalWrite(RED_PIN, r);
  digitalWrite(GREEN_PIN, g);
  digitalWrite(BLUE_PIN, b);
}

void printLCD(int col, int row, String text) {
  lcd.setCursor(col, row);
  while(text.length() < 16) { text += " "; }
  lcd.print(text);
}

// --- NETWORK HELPER ---
void sendHitToServer(String attackerName) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.setTimeout(500); // 500ms max timeout so it NEVER freezes the game loop
    http.begin(serverUrl);
    http.addHeader("Content-Type", "application/json");
    
    // Construct JSON payload
    String payload = "{\"attacker\":\"" + attackerName + "\", \"target\":\"ESP32_Node_1\", \"hitCount\":" + String(hitCount) + "}";
    
    Serial.println("Sending HTTP POST to server...");
    int httpResponseCode = http.POST(payload);
    
    if (httpResponseCode > 0) {
      Serial.print("HTTP Response code: ");
      Serial.println(httpResponseCode);
    } else {
      Serial.print("Error code: ");
      Serial.println(httpResponseCode);
    }
    
    http.end();
  } else {
    Serial.println("Error: WiFi not connected");
  }
}

void setup() {
  Serial.begin(115200);
  
  pinMode(RED_PIN, OUTPUT);
  pinMode(GREEN_PIN, OUTPUT);
  pinMode(BLUE_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  
  lcd.init();
  lcd.backlight();
  
  // --- WIFI CONNECTION ---
  printLCD(0, 0, "Connecting WiFi");
  printLCD(0, 1, "Please wait...");
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false); // CRITICAL: Prevents ESP32 CPU throttling so IR receiver never drops pulses!
  WiFi.begin(ssid, password);
  
  Serial.print("Connecting to: ");
  Serial.println(ssid);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi connected!");
    Serial.print("ESP32 IP: ");
    Serial.println(WiFi.localIP());

    printLCD(0, 0, "WiFi Connected!");
    printLCD(0, 1, WiFi.localIP().toString());
    delay(2000);
  } else {
    Serial.println("\n[ERROR] Failed to connect to WiFi!");
    Serial.print("Status code: ");
    Serial.println(WiFi.status());
    
    printLCD(0, 0, "WiFi FAILED!");
    printLCD(0, 1, "Check 2.4GHz/PW");
    delay(3000);
  }
  // -----------------------

  // Enable IR reception AFTER Wi-Fi setup so radio calibration doesn't corrupt hardware timers
  irrecv.enableIRIn();  

  setLED(LOW, HIGH, LOW); 
  printLCD(0, 0, "HP: 5/5 HEALTHY");
  printLCD(0, 1, "Awaiting targets");
}

void loop() {
  if (isEliminated) return; 

  if (irrecv.decode(&results)) {
    uint64_t code = results.value;
    
    if (code == 0xFFFFFFFF || code == 0) {
      irrecv.resume();
      return; 
    }

    String attackerName = getAttackerName(code);

    if (code == BTN_1 || code == BTN_2 || code == BTN_3 || code == BTN_4) {
      printLCD(0, 0, "ATTACK BLOCKED!");
      printLCD(0, 1, "By: " + attackerName);
      setLED(LOW, LOW, HIGH);
      delay(1000);
      setLED(LOW, HIGH, LOW); 
      printLCD(0, 0, "HP: " + String(maxLives - hitCount) + "/" + String(maxLives));
      printLCD(0, 1, "Ready...");
    } 
    else if (code == BTN_5 || code == BTN_6 || code == BTN_7 || code == BTN_8 || code == BTN_9) {
      hitCount++;
      
      // Notify the central server over Wi-Fi
      sendHitToServer(attackerName);
      
      if (hitCount >= maxLives) {
        printLCD(0, 0, "--- PLAYER ---");
        printLCD(0, 1, "Killed By: " + attackerName.substring(0, 5)); 
        
        for (int i = 0; i < 3; i++) {
          setLED(HIGH, HIGH, LOW); 
          digitalWrite(BUZZER_PIN, HIGH);
          delay(500);
          setLED(LOW, LOW, LOW); 
          digitalWrite(BUZZER_PIN, LOW);
          delay(500);
        }
        isEliminated = true;
      } else {
        setLED(HIGH, LOW, LOW); 
        digitalWrite(BUZZER_PIN, HIGH); 
        delay(200);                     
        digitalWrite(BUZZER_PIN, LOW);
        
        printLCD(0, 0, "HIT: " + attackerName);
        
        for(int i = 4; i > 0; i--) {
          printLCD(0, 1, "Cooldown: " + String(i) + "s");
          delay(1000);
        }
        delay(800); 
        
        setLED(LOW, HIGH, LOW); 
        printLCD(0, 0, "HP: " + String(maxLives - hitCount) + "/" + String(maxLives));
        printLCD(0, 1, "Last: " + attackerName);
      }
    }
    irrecv.resume(); 
  }
}
