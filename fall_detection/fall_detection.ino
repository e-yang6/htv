// Fall Detection — Arduino Nano 33 BLE Sense
// Uses the onboard IMU (LSM9DS1) to detect falls via G-force analysis.
// If you have the Rev2 board, swap Arduino_LSM9DS1 for Arduino_BMI270_BMM150.

#include <Arduino_LSM9DS1.h>
#include <ArduinoBLE.h>

// --- Tunable thresholds ---
// Freefall: when total G drops below this, you're likely falling
const float FREEFALL_THRESHOLD = 0.4;   // in g (normal standing = 1.0g)
// Impact: when total G spikes above this after freefall, you hit something
const float IMPACT_THRESHOLD = 2.5;     // in g
// How long freefall must last to count (filters out bumps)
const unsigned long FREEFALL_MIN_MS = 80;
// Window after freefall to look for impact
const unsigned long IMPACT_WINDOW_MS = 500;
// Cooldown after a detected fall before we can detect another
const unsigned long COOLDOWN_MS = 5000;

// --- State machine ---
enum State { MONITORING, FREEFALL, IMPACT_WAIT, FALL_DETECTED, COOLDOWN };
State state = MONITORING;
unsigned long stateStartTime = 0;

// --- BLE setup ---
BLEService fallService("19B10000-E8F2-537E-4F6C-D104768A1214");
// 0 = normal, 1 = fall detected
BLEByteCharacteristic fallChar("19B10001-E8F2-537E-4F6C-D104768A1214",
                                BLERead | BLENotify);

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000); // wait up to 3s for serial monitor

  // Onboard LED for visual feedback
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  // Start IMU
  if (!IMU.begin()) {
    Serial.println("ERROR: IMU failed to start");
    while (1) {
      digitalWrite(LED_BUILTIN, HIGH);
      delay(100);
      digitalWrite(LED_BUILTIN, LOW);
      delay(100);
    }
  }
  Serial.print("Accelerometer sample rate: ");
  Serial.print(IMU.accelerationSampleRate());
  Serial.println(" Hz");

  // Start BLE
  if (!BLE.begin()) {
    Serial.println("ERROR: BLE failed to start");
    while (1);
  }

  BLE.setLocalName("FallDetector");
  BLE.setAdvertisedService(fallService);
  fallService.addCharacteristic(fallChar);
  BLE.addService(fallService);
  fallChar.writeValue(0);
  BLE.advertise();

  Serial.println("Fall detector running. Advertising as 'FallDetector' over BLE.");
  Serial.println("Open Serial Monitor to see live G-force readings.");
  Serial.println("---");
}

float getTotalG() {
  float ax, ay, az;
  if (IMU.accelerationAvailable()) {
    IMU.readAcceleration(ax, ay, az);
  }
  return sqrt(ax * ax + ay * ay + az * az);
}

void loop() {
  // Keep BLE connection alive
  BLE.poll();

  float totalG = getTotalG();
  unsigned long now = millis();

  switch (state) {

    case MONITORING:
      if (totalG < FREEFALL_THRESHOLD) {
        state = FREEFALL;
        stateStartTime = now;
        Serial.print("Freefall detected! G=");
        Serial.println(totalG, 2);
      }
      break;

    case FREEFALL:
      if (totalG >= FREEFALL_THRESHOLD) {
        // Freefall ended — was it long enough?
        if (now - stateStartTime >= FREEFALL_MIN_MS) {
          state = IMPACT_WAIT;
          stateStartTime = now;
          Serial.println("Freefall ended, watching for impact...");
        } else {
          // Too short, probably just a bump
          state = MONITORING;
        }
      }
      break;

    case IMPACT_WAIT:
      if (totalG > IMPACT_THRESHOLD) {
        // Impact detected after freefall = fall
        state = FALL_DETECTED;
        stateStartTime = now;
        Serial.println("=============================");
        Serial.print("FALL DETECTED! Impact G=");
        Serial.println(totalG, 2);
        Serial.println("=============================");

        // Signal over BLE
        fallChar.writeValue(1);

        // Flash LED rapidly
        for (int i = 0; i < 10; i++) {
          digitalWrite(LED_BUILTIN, HIGH);
          delay(50);
          digitalWrite(LED_BUILTIN, LOW);
          delay(50);
        }
      } else if (now - stateStartTime > IMPACT_WINDOW_MS) {
        // No impact in time window — false alarm
        state = MONITORING;
        Serial.println("No impact detected, resuming monitoring.");
      }
      break;

    case FALL_DETECTED:
      // Stay in this state briefly, then cooldown
      if (now - stateStartTime > 1000) {
        state = COOLDOWN;
        stateStartTime = now;
        fallChar.writeValue(0); // reset BLE signal
        Serial.println("Cooldown...");
      }
      break;

    case COOLDOWN:
      if (now - stateStartTime > COOLDOWN_MS) {
        state = MONITORING;
        Serial.println("Monitoring resumed.");
        Serial.println("---");
      }
      break;
  }

  // Print live G-force every 500ms when monitoring
  static unsigned long lastPrint = 0;
  if (state == MONITORING && now - lastPrint > 500) {
    lastPrint = now;
    Serial.print("G: ");
    Serial.println(totalG, 2);
  }

  delay(10); // ~100Hz sampling
}
