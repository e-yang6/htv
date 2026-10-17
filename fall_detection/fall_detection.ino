// Fall Detection — Arduino Nano 33 BLE Sense
// Uses the onboard IMU (LSM9DS1) to detect falls via G-force analysis.

#include <Arduino_LSM9DS1.h>
#include <ArduinoBLE.h>

// --- Tunable thresholds ---
const float FREEFALL_THRESHOLD = 0.55;
const float IMPACT_THRESHOLD = 1.8;
const unsigned long FREEFALL_MIN_MS = 70;
const unsigned long IMPACT_WINDOW_MS = 600;
// After an impact, a real fall ends with the wearer lying still. Walking, jumping or
// dropping onto a chair keeps moving or keeps taking steps, so it's rejected here.
const unsigned long STILL_SETTLE_MS = 500;     // ignore the bounce right after impact
const unsigned long STILL_CHECK_MS = 1500;     // then watch this long
const float STILL_MAX_DEV = 0.3;               // |G - 1| above this counts as "moving"
const float STILL_MAX_MOVING = 0.15;           // more than 15% moving samples = not a fall

// Step detection (for the robot to follow the wearer's path)
const float STEP_HIGH_G = 1.12;                // smoothed G above this = foot strike
const float STEP_LOW_G = 0.95;                 // must dip below this before the next step
const unsigned long STEP_MIN_MS = 280;         // fastest walking cadence
const unsigned long COOLDOWN_MS = 5000;
const unsigned long CONFIRM_WINDOW_MS = 5000;

// Heading.
// false = measure turning around the real vertical (from gravity), so the board can be worn
// any way up: strapped upright on the chest, in a pocket, held flat.
// true = board is always held flat, so yaw is just the Z gyro.
const bool HELD_FLAT = false;
const float GRAVITY_SMOOTH = 0.01;    // ~1 s average at 100 Hz, so walking bounce doesn't tilt "up"
const float YAW_DEADBAND_DPS = 1.5;   // ignore turn rates below this (gyro noise/drift)
const float STILL_DPS = 3.0;          // below this while not walking, slowly re-learn gyro bias

const float TAP_THRESHOLD = 1.8;
const unsigned long DOUBLE_TAP_WINDOW_MS = 800;

// --- State machine ---
enum State { MONITORING, FREEFALL, IMPACT_WAIT, STILL_CHECK, FALL_DETECTED, ALERT, COOLDOWN };
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
float lastAx = 0, lastAy = 0, lastAz = 1;

// --- Follow-me data for the robot (robot/follow_bridge.py) ---
// 8 bytes, little-endian: int16 heading (deg x10, + = turned left),
// int16 yaw rate (deg/s x10), uint8 motion level (milli-g), int8 RSSI of the connected central (dBm),
// uint16 step count (wraps)
BLECharacteristic followChar("19B10003-E8F2-537E-4F6C-D104768A1214",
                             BLERead | BLENotify, 8, true);

float gyroBiasX = 0, gyroBiasY = 0, gyroBiasZ = 0;
float gravX = 0, gravY = 0, gravZ = 1;   // low-passed accel = which way is "up"
float heading = 0;                       // degrees, integrated around "up"
float yawRate = 0;                       // deg/s
float gBaseline = 1.0;
float motionLevel = 0;                   // avg |G - baseline|, rises while walking
int8_t centralRssi = 0;                  // 0 = not measured yet
unsigned long lastGyroMicros = 0;

uint16_t stepCount = 0;
float stepG = 1.0;                       // smoothed G for step detection
bool stepArmed = true;
unsigned long lastStepMs = 0;

uint16_t impactSteps = 0;                // step count at impact (STILL_CHECK)
float impactG = 0;
int stillSamples = 0, movingSamples = 0;

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

  calibrateGyro();

  if (!BLE.begin()) {
    Serial.println("ERROR: BLE failed to start");
    while (1);
  }

  BLE.setLocalName("FallDetector");
  BLE.setAdvertisedService(fallService);
  fallService.addCharacteristic(fallChar);
  fallService.addCharacteristic(gForceChar);
  fallService.addCharacteristic(followChar);
  BLE.addService(fallService);
  fallChar.writeValue(0);
  gForceChar.writeValue(100);
  uint8_t zeros[8] = {0};
  followChar.writeValue(zeros, 8);
  // Advertising doesn't always come back on its own after a central disconnects,
  // which made the board vanish until reset. Restart it explicitly.
  BLE.setEventHandler(BLEDisconnected, onCentralDisconnected);
  BLE.advertise();

  Serial.println("Fall detector running. Advertising as 'FallDetector' over BLE.");
  Serial.print("Sketch: any-orientation heading v3, HELD_FLAT=");
  Serial.println(HELD_FLAT ? "true" : "false");
  Serial.println("BLE values: fall=0/1/2, gforce=x100");
  Serial.println("---");
}

void onCentralDisconnected(BLEDevice central) {
  Serial.println("BLE central disconnected, advertising again");
  BLE.advertise();
}

// The IMU queues samples in a FIFO faster than loop() runs. Reading one per loop meant we
// were always reading old samples (~0.3 s behind), so drain the queue and keep the newest.
float getTotalG() {
  while (IMU.accelerationAvailable()) {
    IMU.readAcceleration(lastAx, lastAy, lastAz);
  }
  return sqrt(lastAx * lastAx + lastAy * lastAy + lastAz * lastAz);
}

// Average the gyro at rest so the heading doesn't drift. Keep the board still on boot.
void calibrateGyro() {
  Serial.println("Calibrating gyro, keep still...");
  int n = 0;
  float sx = 0, sy = 0, sz = 0;
  unsigned long start = millis();
  while (n < 200 && millis() - start < 4000) {
    if (IMU.gyroscopeAvailable()) {
      float gx, gy, gz;
      IMU.readGyroscope(gx, gy, gz);
      sx += gx; sy += gy; sz += gz;
      n++;
    }
  }
  if (n > 0) {
    gyroBiasX = sx / n;
    gyroBiasY = sy / n;
    gyroBiasZ = sz / n;
  }
  // Start "up" from the real resting orientation (the slow filter would take seconds to get there)
  float ax, ay, az;
  unsigned long waitStart = millis();
  while (!IMU.accelerationAvailable() && millis() - waitStart < 100);
  if (IMU.accelerationAvailable()) {
    IMU.readAcceleration(ax, ay, az);
    gravX = lastAx = ax;
    gravY = lastAy = ay;
    gravZ = lastAz = az;
  }
  lastGyroMicros = micros();
  Serial.println("Gyro calibrated.");
}

// Integrate turn rate around the vertical axis.
// Integrates every queued gyro sample (each is 1/sample-rate long), so nothing lags or gets lost.
void updateHeading() {
  const float dt = 1.0 / IMU.gyroscopeSampleRate();
  while (IMU.gyroscopeAvailable()) {
    float rawX, rawY, rawZ;
    IMU.readGyroscope(rawX, rawY, rawZ);
    float gx = rawX - gyroBiasX, gy = rawY - gyroBiasY, gz = rawZ - gyroBiasZ;

    gravX += GRAVITY_SMOOTH * (lastAx - gravX);
    gravY += GRAVITY_SMOOTH * (lastAy - gravY);
    gravZ += GRAVITY_SMOOTH * (lastAz - gravZ);

    float rate;
    if (HELD_FLAT) {
      rate = gravZ >= 0 ? gz : -gz;   // works face up or face down
    } else {
      float n = sqrt(gravX * gravX + gravY * gravY + gravZ * gravZ);
      if (n < 0.1) continue;
      rate = (gx * gravX + gy * gravY + gz * gravZ) / n;
    }

    // Standing still and barely rotating: whatever is left is bias, nudge it out
    if (motionLevel < 0.015 && fabs(rate) < STILL_DPS) {
      gyroBiasX += 0.002 * gx;
      gyroBiasY += 0.002 * gy;
      gyroBiasZ += 0.002 * gz;
    }

    yawRate = fabs(rate) < YAW_DEADBAND_DPS ? 0 : rate;
    heading += yawRate * dt;
    if (heading >= 180) heading -= 360;
    if (heading < -180) heading += 360;
  }
}

void sendFollowData() {
  BLEDevice central = BLE.central();
  if (central && central.connected()) {
    int r = central.rssi();
    if (r < 0 && r > -128) centralRssi = r;
  }

  int16_t h = (int16_t)(heading * 10);
  int16_t yr = (int16_t)constrain(yawRate * 10, -32000, 32000);
  uint8_t buf[8];
  memcpy(buf, &h, 2);
  memcpy(buf + 2, &yr, 2);
  buf[4] = (uint8_t)min(255.0f, motionLevel * 1000);
  buf[5] = (uint8_t)centralRssi;
  memcpy(buf + 6, &stepCount, 2);
  followChar.writeValue(buf, 8);
}

void updateSteps(unsigned long now) {
  stepG += 0.2 * (currentG - stepG);
  if (stepArmed && stepG > STEP_HIGH_G && now - lastStepMs > STEP_MIN_MS) {
    stepCount++;
    lastStepMs = now;
    stepArmed = false;
  } else if (!stepArmed && stepG < STEP_LOW_G) {
    stepArmed = true;
  }
}

void loop() {
  BLE.poll();

  // Belt and braces: if nobody is connected, make sure we're still advertising
  static unsigned long lastAdvCheck = 0;
  if (millis() - lastAdvCheck > 3000) {
    lastAdvCheck = millis();
    if (!BLE.connected()) BLE.advertise();
  }

  currentG = getTotalG();
  updateHeading();
  gBaseline += 0.01 * (currentG - gBaseline);
  motionLevel += 0.05 * (fabs(currentG - gBaseline) - motionLevel);
  unsigned long now = millis();
  updateSteps(now);

  // Send G-force over BLE every 200ms
  static unsigned long lastGSend = 0;
  if (now - lastGSend > 200) {
    lastGSend = now;
    uint16_t gVal = (uint16_t)(currentG * 100);
    gForceChar.writeValue(gVal);
  }

  // Send follow-me data every 50ms
  static unsigned long lastFollowSend = 0;
  if (now - lastFollowSend >= 50) {   // 20 Hz
    lastFollowSend = now;
    sendFollowData();
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
        state = STILL_CHECK;
        stateStartTime = now;
        impactSteps = stepCount;
        impactG = currentG;
        stillSamples = movingSamples = 0;
        Serial.print("Impact G=");
        Serial.print(currentG, 2);
        Serial.println(", checking the wearer stays down...");
      } else if (now - stateStartTime > IMPACT_WINDOW_MS) {
        state = MONITORING;
        Serial.println("No impact detected, resuming monitoring.");
      }
      break;

    case STILL_CHECK:
      if (now - stateStartTime < STILL_SETTLE_MS) break;
      if (fabs(currentG - 1.0) > STILL_MAX_DEV) movingSamples++;
      else stillSamples++;
      // Impact counts as a step strike, so allow one
      if ((uint16_t)(stepCount - impactSteps) > 1 ||
          movingSamples > STILL_MAX_MOVING * (stillSamples + movingSamples) + 5) {
        state = MONITORING;
        Serial.println("Still moving after impact, not a fall.");
        break;
      }
      if (now - stateStartTime >= STILL_SETTLE_MS + STILL_CHECK_MS) {
        state = FALL_DETECTED;
        stateStartTime = now;
        waitingForSecondTap = false;
        Serial.println("=============================");
        Serial.print("FALL DETECTED! Impact G=");
        Serial.println(impactG, 2);
        Serial.println("Double-tap chest piece to cancel!");
        Serial.println("=============================");

        fallChar.writeValue(1);
        BLE.poll();
        BLE.poll();
        BLE.poll();

        digitalWrite(LEDR, LOW);
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
