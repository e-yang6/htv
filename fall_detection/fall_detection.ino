// Fall Detection — Arduino Nano 33 BLE Sense
// Uses the onboard IMU (LSM9DS1) to detect falls via G-force analysis.

#include <Arduino_LSM9DS1.h>
#include <ArduinoBLE.h>

// --- Tunable thresholds ---
const float FREEFALL_THRESHOLD = 0.6;
const float IMPACT_THRESHOLD = 1.5;
const unsigned long FREEFALL_MIN_MS = 50;
const unsigned long IMPACT_WINDOW_MS = 500;
const unsigned long COOLDOWN_MS = 5000;
const unsigned long CONFIRM_WINDOW_MS = 5000;

const float TAP_THRESHOLD = 1.8;
const unsigned long DOUBLE_TAP_WINDOW_MS = 800;

// --- State machine ---
enum State { MONITORING, FREEFALL, IMPACT_WAIT, FALL_DETECTED, ALERT, COOLDOWN };
State state = MONITORING;
unsigned long stateStartTime = 0;

unsigned long firstTapTime = 0;
bool waitingForSecondTap = false;

// --- BLE setup ---
BLEService fallService("19B10000-E8F2-537E-4F6C-D104768A1214");
// 0 = normal, 1 = fall detected (waiting), 2 = confirmed emergency
BLEByteCharacteristic fallChar("19B10001-E8F2-537E-4F6C-D104768A1214",
                                BLERead | BLENotify);
// G-force as uint16 (value * 100, so 1.0g = 100)
BLEUnsignedShortCharacteristic gForceChar("19B10002-E8F2-537E-4F6C-D104768A1214",
                                           BLERead | BLENotify);

float currentG = 1.0;

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000);

  pinMode(LEDR, OUTPUT);
  pinMode(LEDG, OUTPUT);
  pinMode(LEDB, OUTPUT);
  digitalWrite(LEDR, HIGH);
  digitalWrite(LEDG, HIGH);
  digitalWrite(LEDB, HIGH);

  if (!IMU.begin()) {
    Serial.println("ERROR: IMU failed to start");
    while (1);
  }
  Serial.print("Accelerometer sample rate: ");
  Serial.print(IMU.accelerationSampleRate());
  Serial.println(" Hz");

  if (!BLE.begin()) {
    Serial.println("ERROR: BLE failed to start");
    while (1);
  }

  BLE.setLocalName("FallDetector");
  BLE.setAdvertisedService(fallService);
  fallService.addCharacteristic(fallChar);
  fallService.addCharacteristic(gForceChar);
  BLE.addService(fallService);
  fallChar.writeValue(0);
  gForceChar.writeValue(100);
  BLE.advertise();

  Serial.println("Fall detector running. Advertising as 'FallDetector' over BLE.");
  Serial.println("BLE values: fall=0/1/2, gforce=x100");
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
  BLE.poll();

  currentG = getTotalG();
  unsigned long now = millis();

  // Send G-force over BLE every 200ms
  static unsigned long lastGSend = 0;
  if (now - lastGSend > 200) {
    lastGSend = now;
    uint16_t gVal = (uint16_t)(currentG * 100);
    gForceChar.writeValue(gVal);
  }

  switch (state) {

    case MONITORING:
      if (currentG < FREEFALL_THRESHOLD) {
        state = FREEFALL;
        stateStartTime = now;
        Serial.print("Freefall detected! G=");
        Serial.println(currentG, 2);
      }
      break;

    case FREEFALL:
      if (currentG >= FREEFALL_THRESHOLD) {
        if (now - stateStartTime >= FREEFALL_MIN_MS) {
          state = IMPACT_WAIT;
          stateStartTime = now;
          Serial.println("Freefall ended, watching for impact...");
        } else {
          state = MONITORING;
        }
      }
      break;

    case IMPACT_WAIT:
      if (currentG > IMPACT_THRESHOLD) {
        state = FALL_DETECTED;
        stateStartTime = now;
        waitingForSecondTap = false;
        Serial.println("=============================");
        Serial.print("FALL DETECTED! Impact G=");
        Serial.println(currentG, 2);
        Serial.println("Double-tap chest piece to cancel!");
        Serial.println("=============================");

        fallChar.writeValue(1);
        BLE.poll();
        BLE.poll();
        BLE.poll();

        digitalWrite(LEDR, LOW);
      } else if (now - stateStartTime > IMPACT_WINDOW_MS) {
        state = MONITORING;
        Serial.println("No impact detected, resuming monitoring.");
      }
      break;

    case FALL_DETECTED: {
      if ((now / 250) % 2 == 0) {
        digitalWrite(LEDR, LOW);
      } else {
        digitalWrite(LEDR, HIGH);
      }

      if (currentG > TAP_THRESHOLD) {
        if (!waitingForSecondTap) {
          firstTapTime = now;
          waitingForSecondTap = true;
          Serial.println("First tap detected...");
        } else if (now - firstTapTime > 150 && now - firstTapTime < DOUBLE_TAP_WINDOW_MS) {
          Serial.println("Double-tap! Fall cancelled by user.");
          state = COOLDOWN;
          stateStartTime = now;
          waitingForSecondTap = false;
          digitalWrite(LEDR, HIGH);
          digitalWrite(LEDG, LOW);
          delay(300);
          digitalWrite(LEDG, HIGH);
          fallChar.writeValue(0);
          BLE.poll();
        }
      }

      if (waitingForSecondTap && now - firstTapTime > DOUBLE_TAP_WINDOW_MS) {
        waitingForSecondTap = false;
        Serial.println("Tap timed out, waiting for double-tap...");
      }

      if (now - stateStartTime > CONFIRM_WINDOW_MS) {
        state = ALERT;
        stateStartTime = now;
        Serial.println("!!! NO RESPONSE — SENDING EMERGENCY ALERT !!!");

        fallChar.writeValue(2);
        BLE.poll();
        BLE.poll();
        BLE.poll();

        digitalWrite(LEDR, LOW);
      }
      break;
    }

    case ALERT:
      if (now - stateStartTime > 3000) {
        state = COOLDOWN;
        stateStartTime = now;
        digitalWrite(LEDR, HIGH);
        fallChar.writeValue(0);
        BLE.poll();
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

  static unsigned long lastPrint = 0;
  if (state == MONITORING && now - lastPrint > 500) {
    lastPrint = now;
    Serial.print("G: ");
    Serial.println(currentG, 2);
  }

  delay(10);
}
