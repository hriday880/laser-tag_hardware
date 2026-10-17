#include <WiFi.h>
#include <ArduinoOTA.h>

const char* ssid = "Hriday";
const char* password = "12345678";

void setup() {
  Serial.begin(115200);
  Serial.println("Booting OTA Test...");

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  Serial.print("Connecting to ");
  Serial.print(ssid);
  
  while (WiFi.waitForConnectResult() != WL_CONNECTED) {
    Serial.println("Connection Failed! Rebooting...");
    delay(5000);
    ESP.restart();
  }

  Serial.println("\nWiFi Connected!");

  // --- OTA SETUP ---
  ArduinoOTA.setHostname("OTA-Test-Node");
  ArduinoOTA.setPassword("admin");

  ArduinoOTA.onStart([]() {
    Serial.println("Start updating...");
  });
  ArduinoOTA.onEnd([]() {
    Serial.println("\nOTA SUCCESS! Rebooting...");
  });
  ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
    Serial.printf("Progress: %u%%\r", (progress / (total / 100)));
  });
  ArduinoOTA.onError([](ota_error_t error) {
    Serial.printf("Error[%u]: ", error);
  });

  ArduinoOTA.begin();
  Serial.println("Ready for OTA!");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  // This is the magic line that listens for wireless updates!
  ArduinoOTA.handle();
  
  // Print a heartbeat every 2 seconds
  static unsigned long lastTime = 0;
  if (millis() - lastTime > 2000) {
    // CHANGE THIS TEXT for your wireless test!
    Serial.println("Running Version 1 (flashed via USB)...");
    lastTime = millis();
  }
}
