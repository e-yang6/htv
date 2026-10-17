#ifndef SERIAL_DEBUG_EXECUTOR_H
#define SERIAL_DEBUG_EXECUTOR_H

#ifdef ARDUINO
    #include <Arduino.h>
#else
    #include <stdio.h>
#endif

#include "IMovementExecutor.h"

/**
 * @brief Reference/Mock implementation of IMovementExecutor for testing and debugging.
 * 
 * Prints every movement command to the Serial Monitor (or stdout) and performs
 * blocking delay. Use this to verify your backtracking logic without needing
 * real motor hardware connected yet!
 * 
 * Replace or subclass this when integrating physical motor drivers (L298N, TB6612, servos, etc.).
 */
class SerialDebugExecutor : public IMovementExecutor {
private:
    bool verbose;

public:
    explicit SerialDebugExecutor(bool verboseOutput = true) 
        : verbose(verboseOutput) {}

    void executeStep(const Step& step) override {
        if (!step.isValid()) return;

#ifdef ARDUINO
        if (verbose) {
            Serial.print(F("[EXECUTOR] Executing: "));
            Serial.print(step.getTypeName());
            Serial.print(F(" | Duration: "));
            Serial.print(step.durationMs);
            Serial.print(F(" ms | Speed: "));
            Serial.println(step.speed);
        }

        // Blocking movement simulation
        delay(step.durationMs);
#else
        if (verbose) {
            printf("[EXECUTOR] Executing: %-12s | Duration: %5u ms | Speed: %3u\n",
                   step.getTypeName(), step.durationMs, step.speed);
        }
#endif
    }

    void stop() override {
#ifdef ARDUINO
        if (verbose) {
            Serial.println(F("[EXECUTOR] Hardware STOP: Motors halted."));
        }
#else
        if (verbose) {
            printf("[EXECUTOR] Hardware STOP: Motors halted.\n");
        }
#endif
    }
};

#endif // SERIAL_DEBUG_EXECUTOR_H
