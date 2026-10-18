// Meccanoid robot on an Arduino UNO Q (STM32 MCU side).
//
// The UNO Q's pins are 3.3 V, which can't switch the robot's 5N65 MOSFETs (or reliably talk to the
// 5 V Meccanoid servos). So the old Uno stays on the robot as a 5 V driver, still running
// robot/meccanoid_follow (no reflash needed), and this sketch forwards commands to it on one wire:
//   UNO Q D1 (TX) -> Uno D0 (RX),  GND -> GND,  UNO Q 5V -> Uno 5V
// D0/D1 are the UNO Q's hardware UART (Serial = usart1); the Bridge uses a different one (Serial1).
// Motors stay on the Uno's D5/D6 and the servo chain on its D8, as before.
//
// Commands arrive from the UNO Q's Linux side over the Router Bridge:
//   drive(left, right)  0-255 each, ~20x a second, from robot/unoq_robot/python/main.py
//   arms(angle)         >= 90 = arms up, < 90 = arms down
// They go out as the Uno's own serial format at 9600 baud: "<left,right>" and "o"/"p".
// If drive() stops arriving we stop sending, and the Uno stops the motors after 0.7 s.
#include <Arduino_RouterBridge.h>

const long BAUD = 9600;      // what meccanoid_follow on the Uno listens at
const unsigned long DRIVE_TIMEOUT_MS = 700;

// Set from Bridge callbacks, sent from loop(): callbacks must stay short and must not
// talk back over the Bridge (that deadlocks), so they only store what was asked for.
volatile int wantLeft = 0, wantRight = 0;
volatile unsigned long lastDriveMs = 0;
volatile bool driveChanged = false;
volatile int wantArms = -1;  // -1 = nothing to send, 1 = up, 0 = down

bool drive(int left, int right) {
  wantLeft = constrain(left, 0, 255);
  wantRight = constrain(right, 0, 255);
  lastDriveMs = millis();
  driveChanged = true;
  return true;   // lets the Linux side confirm the MCU got it
}

bool arms(int angle) {
  wantArms = angle >= 90 ? 1 : 0;
  return true;
}

// Diagnostics: whatever arrives on D0 (RX) is kept, so the Linux side can show it. Wire the Uno's
// TX (D1) to this board's D0 to read the Uno's own messages ("Ready", "Follow mode ON", ...).
volatile long rxCount = 0;
char rxText[241];
int rxLen = 0;
long rx_count() { return rxCount; }
String rx_text() {
  rxText[rxLen] = '\0';
  String out(rxText);
  rxLen = 0;
  return out;
}

void sendText(const char *s) {
  Serial.print(s);   // hardware UART: exact timing, nothing to disturb it
}

void setup() {
  Serial.begin(BAUD);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, HIGH);               // LED is active-low on the UNO Q: HIGH = off

  Bridge.begin();
  Bridge.provide("drive", drive);
  Bridge.provide("arms", arms);
  Bridge.provide("rx_count", rx_count);
  Bridge.provide("rx_text", rx_text);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    rxCount++;
    if (rxLen < 240) rxText[rxLen++] = c;
  }
  bool fresh = millis() - lastDriveMs < DRIVE_TIMEOUT_MS;
  if (driveChanged && fresh) {
    driveChanged = false;
    char frame[16];
    snprintf(frame, sizeof(frame), "<%d,%d>", wantLeft, wantRight);
    sendText(frame);
  }
  int a = wantArms;
  if (a >= 0) {
    wantArms = -1;
    sendText(a ? "o" : "p");
  }
  // Built-in LED on while a motor is being driven: shows the MCU is getting commands
  digitalWrite(LED_BUILTIN, fresh && (wantLeft || wantRight) ? LOW : HIGH);
}
