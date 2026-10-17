// ============================================================================
// Robot Movement Caching & Backtracking Demo
// ============================================================================
// Compatible with Arduino Nano 33 BLE, Uno, Mega, ESP32, etc.
// 
// This sketch demonstrates the decoupled backtracking subsystem:
// 1. Caches forward robot movements (time-based duration in milliseconds).
// 2. Inverts each step symmetrically (Forward <-> Backward, Left <-> Right).
// 3. Reverses steps in LIFO order (last step first) in a blocking loop.
// 4. Movement execution is 100% decoupled via IMovementExecutor.
//
// Open the Serial Monitor at 115200 baud to view or interact.
// ============================================================================

#include "BacktrackManager.h"
#include "SerialDebugExecutor.h"

// ----------------------------------------------------------------------------
// 1. Executor Setup (Decoupled from Backtracking Logic)
// ----------------------------------------------------------------------------
// For now, we use SerialDebugExecutor which simulates movement with delay()
// and prints the commands to Serial.
// When you build your motor driver later, simply replace this with:
//   class MyMotorExecutor : public IMovementExecutor { ... };
SerialDebugExecutor debugExecutor(/* verbose = */ true);

// ----------------------------------------------------------------------------
// 2. Backtracking Manager Instance
// ----------------------------------------------------------------------------
// Capacity: 64 steps (uses only ~256 bytes of RAM, zero dynamic allocations).
BacktrackManager<64> backtrack(&debugExecutor);

void printMenu() {
    Serial.println(F("\n--- Interactive Backtrack Menu ---"));
    Serial.println(F(" Send a character via Serial Monitor:"));
    Serial.println(F("  'f' or 'w' -> Step Forward (1000ms)"));
    Serial.println(F("  'k' or 's' -> Step Backward (1000ms)"));
    Serial.println(F("  'l' or 'a' -> Turn Left (500ms)"));
    Serial.println(F("  'r' or 'd' -> Turn Right (500ms)"));
    Serial.println(F("  'b'        -> BACKTRACK ALL STEPS"));
    Serial.println(F("  'u'        -> Undo (Backtrack) LAST single step"));
    Serial.println(F("  'c'        -> Clear step history"));
    Serial.println(F("  '?'        -> Show cache status"));
    Serial.println(F("----------------------------------\n"));
}

void printStatus() {
    Serial.print(F("[STATUS] Cached Steps: "));
    Serial.print(backtrack.getStepCount());
    Serial.print(F(" / "));
    Serial.println(backtrack.getCapacity());
}

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 3000); // Wait up to 3s for Serial Monitor

    Serial.println(F("============================================="));
    Serial.println(F("   Robot Backtracking Subsystem Initialized  "));
    Serial.println(F("============================================="));

    // ------------------------------------------------------------------------
    // AUTOMATED DEMONSTRATION RUN
    // ------------------------------------------------------------------------
    Serial.println(F("\n[DEMO] Starting automated exploration demonstration..."));
    
    // Simulate navigation path:
    // 1. Forward for 1200ms
    Serial.println(F("\n[STEP 1] Moving Forward (1200ms)"));
    backtrack.executeAndRecord(Step(MovementType::FORWARD, 1200));

    // 2. Turn Left for 600ms
    Serial.println(F("\n[STEP 2] Turning Left (600ms)"));
    backtrack.executeAndRecord(Step(MovementType::TURN_LEFT, 600));

    // 3. Forward for 1800ms
    Serial.println(F("\n[STEP 3] Moving Forward (1800ms)"));
    backtrack.executeAndRecord(Step(MovementType::FORWARD, 1800));

    // 4. Turn Right for 450ms
    Serial.println(F("\n[STEP 4] Turning Right (450ms)"));
    backtrack.executeAndRecord(Step(MovementType::TURN_RIGHT, 450));

    // 5. Forward for 800ms
    Serial.println(F("\n[STEP 5] Moving Forward (800ms)"));
    backtrack.executeAndRecord(Step(MovementType::FORWARD, 800));

    printStatus();

    Serial.println(F("\n[DEMO] Robot reached destination. Pausing for 2 seconds..."));
    delay(2000);

    // Now trigger backtracking!
    Serial.println(F("\n============================================="));
    Serial.println(F(">>> INITIATING BACKTRACKING TO ORIGIN <<<"));
    Serial.println(F("============================================="));

    size_t stepsReversed = backtrack.backtrackAll(/* interStepPauseMs = */ 150);

    Serial.println(F("============================================="));
    Serial.print(F(">>> BACKTRACKING COMPLETE! Reversed: "));
    Serial.print(stepsReversed);
    Serial.println(F(" steps <<<"));
    Serial.println(F("============================================="));

    printStatus();
    printMenu();
}

void loop() {
    // Interactive Serial Controller
    if (Serial.available() > 0) {
        char cmd = Serial.read();

        // Skip newline or carriage return
        if (cmd == '\r' || cmd == '\n' || cmd == ' ') {
            return;
        }

        switch (cmd) {
            case 'f':
            case 'w':
                Serial.println(F("\n[MANUAL] Forward (1000ms)"));
                backtrack.executeAndRecord(Step(MovementType::FORWARD, 1000));
                printStatus();
                break;

            case 'k':
            case 's':
                Serial.println(F("\n[MANUAL] Backward (1000ms)"));
                backtrack.executeAndRecord(Step(MovementType::BACKWARD, 1000));
                printStatus();
                break;

            case 'l':
            case 'a':
                Serial.println(F("\n[MANUAL] Turn Left (500ms)"));
                backtrack.executeAndRecord(Step(MovementType::TURN_LEFT, 500));
                printStatus();
                break;

            case 'r':
            case 'd':
                Serial.println(F("\n[MANUAL] Turn Right (500ms)"));
                backtrack.executeAndRecord(Step(MovementType::TURN_RIGHT, 500));
                printStatus();
                break;

            case 'b':
                Serial.println(F("\n[COMMAND] Backtracking all steps..."));
                if (backtrack.isEmpty()) {
                    Serial.println(F("[BACKTRACK] Cache is already empty! Nothing to reverse."));
                } else {
                    size_t count = backtrack.backtrackAll(150);
                    Serial.print(F("[BACKTRACK] Completed. Reversed "));
                    Serial.print(count);
                    Serial.println(F(" steps."));
                }
                printStatus();
                break;

            case 'u':
                Serial.println(F("\n[COMMAND] Undoing last 1 step..."));
                if (backtrack.isEmpty()) {
                    Serial.println(F("[UNDO] Cache is empty!"));
                } else {
                    backtrack.backtrackSteps(1, 150);
                    Serial.println(F("[UNDO] Step undone."));
                }
                printStatus();
                break;

            case 'c':
                backtrack.clearHistory();
                Serial.println(F("\n[COMMAND] Step cache cleared."));
                printStatus();
                break;

            case '?':
                printStatus();
                printMenu();
                break;

            default:
                Serial.print(F("[?] Unknown command: '"));
                Serial.print(cmd);
                Serial.println(F("'. Send '?' for menu."));
                break;
        }
    }
}
