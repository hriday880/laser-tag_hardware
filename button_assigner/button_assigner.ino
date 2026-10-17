#include <Arduino.h>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRutils.h>

const uint16_t kRecvPin = 14; 
IRrecv irrecv(kRecvPin);
decode_results results;

int currentButton = 1;
uint64_t buttonCodes[10]; // Array to store codes for buttons 1-9
bool scanComplete = false;

void setup() {
  Serial.begin(115200);
  irrecv.enableIRIn();  
  
  delay(2000); // Give the serial monitor time to open
  Serial.println("\n==================================");
  Serial.println("   LASER TAG REMOTE SETUP WIZARD  ");
  Serial.println("==================================");
  Serial.println("\nPlease press button 1 on your remote...");
}

void loop() {
  if (scanComplete) {
    return; // Stop running once all 9 buttons are scanned
  }

  if (irrecv.decode(&results)) {
    uint64_t code = results.value;
    
    // Ignore repeating codes (button held down) and null reads
    if (code != 0xFFFFFFFF && code != 0) { 
      
      // Save the code
      buttonCodes[currentButton] = code;
      
      Serial.print("SUCCESS: Captured Button ");
      Serial.println(currentButton);
      
      currentButton++; // Move to the next button
      
      if (currentButton <= 9) {
        Serial.print("\nNow press button ");
        Serial.print(currentButton);
        Serial.println("...");
      } else {
        // We have all 9 buttons, print the final block!
        scanComplete = true;
        Serial.println("\n\n==================================");
        Serial.println("SCAN COMPLETE! COPY THE TEXT BELOW");
        Serial.println("==================================\n");
        
        Serial.println("// Codes that do nothing (Buttons 1, 2, 3, 4)");
        for(int i = 1; i <= 4; i++) {
          Serial.print("#define BTN_");
          Serial.print(i);
          Serial.print(" 0x");
          serialPrintUint64(buttonCodes[i], HEX);
          Serial.println();
        }
        
        Serial.println("\n// Codes that cause damage (Buttons 5, 6, 7, 8, 9)");
        for(int i = 5; i <= 9; i++) {
          Serial.print("#define BTN_");
          Serial.print(i);
          Serial.print(" 0x");
          serialPrintUint64(buttonCodes[i], HEX);
          Serial.println();
        }
        Serial.println("\n==================================");
      }
    }
    // Resume listening for the next signal
    irrecv.resume();  
  }
  delay(100);
}