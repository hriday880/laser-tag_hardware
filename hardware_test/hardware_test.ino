#include <Arduino.h>
#include <Wire.h>

// List of safe pins to test
int pins[] = {2, 4, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33};
int numPins = 17;

void setup() {
  Serial.begin(115200);
  delay(1000); 
  
  Serial.println("\n\n===============================");
  Serial.println("   BRUTE FORCE I2C SCANNER    ");
  Serial.println("===============================");
  Serial.println("Testing every possible pin combination...");
  
  bool found = false;
  
  for (int sda_idx = 0; sda_idx < numPins; sda_idx++) {
    for (int scl_idx = 0; scl_idx < numPins; scl_idx++) {
      if (sda_idx == scl_idx) continue;
      
      int test_sda = pins[sda_idx];
      int test_scl = pins[scl_idx];
      
      Wire.begin(test_sda, test_scl);
      
      // Try to find device at 0x27 or 0x3F
      Wire.beginTransmission(0x27);
      if (Wire.endTransmission() == 0) {
        Serial.print("\n>>> BINGO! LCD FOUND AT 0x27! <<<\n");
        Serial.print("Your SDA wire is actually plugged into GPIO "); Serial.println(test_sda);
        Serial.print("Your SCL wire is actually plugged into GPIO "); Serial.println(test_scl);
        found = true;
        break;
      }
      
      Wire.beginTransmission(0x3F);
      if (Wire.endTransmission() == 0) {
        Serial.print("\n>>> BINGO! LCD FOUND AT 0x3F! <<<\n");
        Serial.print("Your SDA wire is actually plugged into GPIO "); Serial.println(test_sda);
        Serial.print("Your SCL wire is actually plugged into GPIO "); Serial.println(test_scl);
        found = true;
        break;
      }
    }
    if (found) break;
  }
  
  if (!found) {
    Serial.println("\nScan complete. The LCD is completely invisible to the ESP32.");
    Serial.println("This means either the SDA/SCL wires are broken/badly soldered, or the LCD chip was damaged.");
  }
}

void loop() {
  // Do nothing
}
