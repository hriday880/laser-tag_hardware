// ==========================================
//   BUZZER TYPE TEST (Active vs Passive)
// ==========================================
// Upload, open Serial Monitor @115200 and LISTEN.
//
// TEST 1: Pin held HIGH for 1 second.
//   - Loud steady BEEP  -> ACTIVE buzzer
//   - Just a tiny click -> PASSIVE buzzer
//
// TEST 2: Plays a rising scale (C4 -> C6) with tone().
//   - You hear clearly DIFFERENT pitches going up -> PASSIVE buzzer
//   - Same buzzy pitch every note                -> ACTIVE buzzer
//
// Then set BUZZER_PASSIVE in prototype_mark_4.ino accordingly.

const int BUZZER_PIN = 33;

const int scaleNotes[] = {262, 294, 330, 349, 392, 440, 494, 523, 659, 784, 1047};
const int scaleLen = sizeof(scaleNotes) / sizeof(scaleNotes[0]);

void setup() {
  Serial.begin(115200);
  delay(1000);
  pinMode(BUZZER_PIN, OUTPUT);
}

void loop() {
  Serial.println("\n=== TEST 1: digitalWrite HIGH for 1s ===");
  Serial.println("Loud beep = ACTIVE | small click = PASSIVE");
  digitalWrite(BUZZER_PIN, HIGH);
  delay(1000);
  digitalWrite(BUZZER_PIN, LOW);
  delay(1500);

  Serial.println("=== TEST 2: rising scale with tone() ===");
  Serial.println("Pitch rises = PASSIVE | same pitch = ACTIVE");
  for (int i = 0; i < scaleLen; i++) {
    tone(BUZZER_PIN, scaleNotes[i]);
    delay(250);
  }
  noTone(BUZZER_PIN);
  digitalWrite(BUZZER_PIN, LOW);

  Serial.println("Repeating in 4 seconds...");
  delay(4000);
}
