#include <Arduino.h>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRutils.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// --- PIN SETUP ---
const uint16_t IR_PIN = 14;      
const int RED_PIN = 25;          
const int GREEN_PIN = 26;        
const int BLUE_PIN = 27;         
const int BUZZER_PIN = 33;       
// LCD uses default I2C pins: SDA = 21, SCL = 22

// --- LCD SETUP ---
// 0x27 is the standard I2C address. (If the screen stays blank, try 0x3F)
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

int hitCount = 0;
bool isEliminated = false;

// Helper to easily change LED colors
void setLED(bool r, bool g, bool b) {
  digitalWrite(RED_PIN, r);
  digitalWrite(GREEN_PIN, g);
  digitalWrite(BLUE_PIN, b);
}

// Helper to update the LCD screen
void updateDisplay() {
  lcd.clear();
  if (hitCount == 0) {
    lcd.setCursor(0, 0);
    lcd.print("Status: HEALTHY");
    lcd.setCursor(0, 1);
    lcd.print("Lives: 5");
  } else if (hitCount >= 5) {
    lcd.setCursor(0, 0);
    lcd.print("--- PLAYER ---");
    lcd.setCursor(0, 1);
    lcd.print(" ELIMINATED! ");
  } else {
    lcd.setCursor(0, 0);
    lcd.print("Status: DAMAGED");
    lcd.setCursor(0, 1);
    lcd.print("Lives: ");
    lcd.print(5 - hitCount);
  }
}

void setup() {
  Serial.begin(115200);
  irrecv.enableIRIn();  
  
  pinMode(RED_PIN, OUTPUT);
  pinMode(GREEN_PIN, OUTPUT);
  pinMode(BLUE_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  
  // Initialize the LCD
  lcd.init();
  lcd.backlight();
  updateDisplay();
  
  // Default State: GREEN
  setLED(LOW, HIGH, LOW); 
}

void loop() {
  if (isEliminated) {
    return; // Game over, freeze everything
  }

  if (irrecv.decode(&results)) {
    uint64_t code = results.value;
    
    // Ignore held-down button codes
    if (code == 0xFFFFFFFF || code == 0) {
      irrecv.resume();
      return; 
    }

    // Shield (Buttons 1-4)
    if (code == BTN_1 || code == BTN_2 || code == BTN_3 || code == BTN_4) {
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("Attack Blocked!");
      delay(1000);
      updateDisplay(); // Restore normal health screen
    } 
    
    // Damage (Buttons 5-9)
    else if (code == BTN_5 || code == BTN_6 || code == BTN_7 || code == BTN_8 || code == BTN_9) {
      hitCount++;
      
      if (hitCount >= 5) {
        updateDisplay();
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
        updateDisplay();
        setLED(HIGH, LOW, LOW);         
        digitalWrite(BUZZER_PIN, HIGH); 
        delay(200);                     
        digitalWrite(BUZZER_PIN, LOW);
        
        // Visual Cooldown Timer on LCD
        for(int i = 4; i > 0; i--) {
          lcd.setCursor(0,0);
          lcd.print("COOLDOWN: ");
          lcd.print(i);
          lcd.print("s   ");
          delay(1000);
        }
        delay(800); // Finish out the 4.8s delay
        
        setLED(LOW, HIGH, LOW); // Back to GREEN
        updateDisplay();
      }
    }
    irrecv.resume(); 
  }
}