#include <WiFi.h>

void setup() {
  Serial.begin(115200);
  delay(1000); // Give serial monitor time to open
  
  // Set WiFi to station mode and force radio initialization
  WiFi.mode(WIFI_STA);
  WiFi.begin(); 
  delay(500); // Wait for the Wi-Fi chip to fully wake up
  
  Serial.println();
  Serial.println("=================================");
  Serial.print("YOUR ESP32 MAC ADDRESS: ");
  Serial.println(WiFi.macAddress());
  Serial.println("=================================");
}

void loop() {
  // Do nothing
}
