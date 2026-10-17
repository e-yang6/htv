#include <Meccanoid.h>

const int LEFT_MOTOR  = 5;
const int RIGHT_MOTOR = 6;
const int SPEED = 255;   // full speed works best with the 5N65 MOSFETs

Chain chain(8);
MeccanoServo servos[4] = {
  chain.getServo(0),   // your servo 1
  chain.getServo(1),   // your servo 2
  chain.getServo(2),   // your servo 3 (reversed)
  chain.getServo(3)    // your servo 4 (reversed)
};
const bool reversed[4] = { false, false, true, true };

const int ARM_UP   = 150;   // swap these two if "up" moves the wrong way
const int ARM_DOWN = 30;

// Follow mode: robot/follow_bridge.py reads the wearable BLE33 and streams
// motor frames "<left,right>" (0-255 each) over this serial port.
// Any frame turns follow mode on; w/s/a/d take back manual control.
const unsigned long FOLLOW_TIMEOUT_MS = 700;   // stop if the bridge goes quiet
bool following = false;
unsigned long lastFrameMs = 0;

char frameBuf[12];
int frameLen = -1;   // -1 = not inside a frame

void setServo(int i, int angle) {
  angle = constrain(angle, 0, 180);
  if (reversed[i]) angle = 180 - angle;
  servos[i].setPosition(angle);
}

void setAllArms(int angle) {
  for (int i = 0; i < 4; i++) {
    if (servos[i].isConnected()) setServo(i, angle);
  }
}

void setMotors(int l, int r) {
  analogWrite(LEFT_MOTOR, l);
  analogWrite(RIGHT_MOTOR, r);
}

void stopFollowing() {
  if (following) {
    following = false;
    Serial.println("Follow mode OFF");
  }
}

// Non-blocking parser for "<l,r>" frames. Returns true if c belonged to a frame.
bool parseFrame(char c) {
  if (c == '<') { frameLen = 0; return true; }
  if (frameLen < 0) return false;

  if (c == '>') {
    frameBuf[frameLen] = '\0';
    frameLen = -1;
    char *comma = strchr(frameBuf, ',');
    if (comma) {
      *comma = '\0';
      int l = constrain(atoi(frameBuf), 0, 255);
      int r = constrain(atoi(comma + 1), 0, 255);
      if (!following) Serial.println("Follow mode ON");
      following = true;
      lastFrameMs = millis();
      setMotors(l, r);
    }
    return true;
  }

  if (frameLen < (int)sizeof(frameBuf) - 1) frameBuf[frameLen++] = c;
  else frameLen = -1;   // garbage, drop the frame
  return true;
}

void setup() {
  Serial.begin(9600);
  pinMode(LEFT_MOTOR, OUTPUT);
  pinMode(RIGHT_MOTOR, OUTPUT);
  setMotors(0, 0);
  Serial.println("Ready. w=both  s=stop  d=left motor  a=right motor  o=arms up  p=arms down");
  Serial.println("Follow mode: run robot/follow_bridge.py (any of w/s/a/d exits it)");
}

void loop() {
  chain.update();   // must run constantly

  for (int i = 0; i < 4; i++) {
    if (servos[i].justConnected()) {
      servos[i].setColor(0, 1, 0);
      Serial.print("Servo ");
      Serial.print(i);
      Serial.println(" found");
    }
  }

  while (Serial.available()) {
    char raw = Serial.read();
    if (parseFrame(raw)) continue;
    char c = tolower(raw);

    switch (c) {
      case 'w': stopFollowing(); setMotors(SPEED, SPEED); Serial.println("Both motors");        break;
      case 's': stopFollowing(); setMotors(0, 0);         Serial.println("Motors stopped");     break;
      case 'd': stopFollowing(); setMotors(SPEED, 0);     Serial.println("Left motor only");    break;
      case 'a': stopFollowing(); setMotors(0, SPEED);     Serial.println("Right motor only");   break;
      case 'o': setAllArms(ARM_UP);      Serial.println("Arms up");            break;
      case 'p': setAllArms(ARM_DOWN);    Serial.println("Arms down");          break;
      default: break;   // ignore Enter and other keys
    }
  }

  if (following && millis() - lastFrameMs > FOLLOW_TIMEOUT_MS) {
    setMotors(0, 0);
    following = false;
    Serial.println("Follow signal lost, motors stopped");
  }
}
