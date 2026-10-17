// Servo test: swing daisy-chained servos 2 and 3 up and down in a loop.
// Same wiring and numbering as meccanoid_follow (chain on pin 8, "your servo 1" = index 0).
#include <Meccanoid.h>

Chain chain(8);
MeccanoServo servo2 = chain.getServo(1);   // your servo 2
MeccanoServo servo3 = chain.getServo(2);   // your servo 3 (reversed)

const int ARM_UP   = 150;   // swap these two if "up" moves the wrong way
const int ARM_DOWN = 30;
const unsigned long HOLD_MS = 1000;   // time at each end

bool up = false;
unsigned long lastSwitch = 0;

void setAngle(MeccanoServo &s, int angle, bool reversed) {
  angle = constrain(angle, 0, 180);
  if (reversed) angle = 180 - angle;
  s.setPosition(angle);
}

void setup() {
  Serial.begin(9600);
  Serial.println("Servo test: servos 2 and 3 up/down");
}

void loop() {
  chain.update();   // must run constantly, so no delay() in here

  if (servo2.justConnected()) { servo2.setColor(0, 1, 0); Serial.println("Servo 2 found"); }
  if (servo3.justConnected()) { servo3.setColor(0, 1, 0); Serial.println("Servo 3 found"); }

  if (millis() - lastSwitch >= HOLD_MS) {
    lastSwitch = millis();
    up = !up;
    int angle = up ? ARM_UP : ARM_DOWN;
    if (servo2.isConnected()) setAngle(servo2, angle, false);
    if (servo3.isConnected()) setAngle(servo3, angle, true);
    Serial.println(up ? "Up" : "Down");
  }
}
