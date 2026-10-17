# Robot Backtracking Subsystem

A lightweight, zero-heap C++ movement caching and backtracking engine for Arduino robotics.

---

## Key Features

1. **Hardware-Decoupled (`IMovementExecutor`):** The caching and reversal system has zero knowledge of motor driver pins, PWM, or servos. It communicates strictly through an abstract interface.
2. **Symmetric Step Inversion (`StepInverter`):** Every motion primitive has a pure opposite (`FORWARD` $\leftrightarrow$ `BACKWARD`, `TURN_LEFT` $\leftrightarrow$ `TURN_RIGHT`, `STRAFE_LEFT` $\leftrightarrow$ `STRAFE_RIGHT`, `PIVOT_LEFT` $\leftrightarrow$ `PIVOT_RIGHT`).
3. **Zero Dynamic Allocation (`StepCache`):** Uses a pre-allocated circular LIFO stack. A 64-step buffer consumes only **~256 bytes of RAM**, preventing heap fragmentation on microcontrollers.
4. **Time-Based Step Metric & Blocking Reversal:** Steps store durations in milliseconds, and backtracking executes via simple blocking loops with configurable inter-step settling pauses.

---

## File Structure

```text
robot_backtrack/
├── Step.h                 // MovementType enum and compact Step struct (4 bytes)
├── StepInverter.h         // Pure reciprocal inversion declarations
├── StepInverter.cpp       // Reciprocal inversion implementation
├── StepCache.h            // Template circular LIFO stack (zero-heap)
├── IMovementExecutor.h    // Abstract motor execution interface
├── SerialDebugExecutor.h  // Mock executor for testing in Serial Monitor
├── BacktrackManager.h     // High-level orchestrator
├── library.properties     // Arduino library metadata
└── README.md              // Documentation and usage guide
```

A complete, ready-to-flash demo sketch is located in [`backtrack_demo/backtrack_demo.ino`](file:///c:/Users/dashw/OneDrive/Documents/GitHub/htv/backtrack_demo/backtrack_demo.ino).

---

## Quick Start Example

### 1. Using the Subsystem in Your Arduino Sketch

```cpp
#include "BacktrackManager.h"
#include "SerialDebugExecutor.h"

// 1. Create an executor (for now, SerialDebugExecutor simulates movement)
SerialDebugExecutor executor(true);

// 2. Initialize BacktrackManager with 64-step capacity
BacktrackManager<64> backtrack(&executor);

void setup() {
    Serial.begin(115200);

    // Record or execute robot movements
    backtrack.executeAndRecord(Step(MovementType::FORWARD, 1000));
    backtrack.executeAndRecord(Step(MovementType::TURN_LEFT, 500));
    backtrack.executeAndRecord(Step(MovementType::FORWARD, 1500));

    // When ready to return to origin:
    backtrack.backtrackAll(/* interStepPauseMs = */ 100);
}

void loop() {}
```

---

## How to Plug In Real Motor Control Later

When you know your robot's motor driver hardware (e.g., L298N, TB6612FNG, servos, stepper motors), simply subclass [`IMovementExecutor`](file:///c:/Users/dashw/OneDrive/Documents/GitHub/htv/robot_backtrack/IMovementExecutor.h):

```cpp
#include "IMovementExecutor.h"

class MyRobotMotors : public IMovementExecutor {
public:
    void executeStep(const Step& step) override {
        switch (step.type) {
            case MovementType::FORWARD:
                // Engage left and right motors forward
                setMotors(step.speed, step.speed);
                break;

            case MovementType::BACKWARD:
                // Engage left and right motors backward
                setMotors(-step.speed, -step.speed);
                break;

            case MovementType::TURN_LEFT:
                // Spin left
                setMotors(-step.speed, step.speed);
                break;

            case MovementType::TURN_RIGHT:
                // Spin right
                setMotors(step.speed, -step.speed);
                break;

            default:
                stop();
                break;
        }

        // Blocking time duration
        delay(step.durationMs);
        stop();
    }

    void stop() override {
        // Cut power to motors / apply brake
        setMotors(0, 0);
    }

private:
    void setMotors(int leftSpeed, int rightSpeed) {
        // Your pin manipulation / analogWrite / PWM code here
    }
};
```

Then attach your motor class to the manager:
```cpp
MyRobotMotors realMotors;
BacktrackManager<64> backtrack(&realMotors);
```

**Zero changes to the backtracking or caching logic are required!**
