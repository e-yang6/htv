#ifndef BACKTRACK_MANAGER_H
#define BACKTRACK_MANAGER_H

#ifdef ARDUINO
    #include <Arduino.h>
#else
    #include <stdint.h>
    #include <stddef.h>
#endif

#include "Step.h"
#include "StepInverter.h"
#include "StepCache.h"
#include "IMovementExecutor.h"

/**
 * @brief High-level coordinator for recording steps and executing backtracking.
 * 
 * Manages the LIFO StepCache, step inversion, and dispatches inverse commands
 * to the registered IMovementExecutor.
 * 
 * @tparam CAPACITY Maximum number of steps stored in memory (default: 64 steps).
 */
template <size_t CAPACITY = 64>
class BacktrackManager {
private:
    StepCache<CAPACITY> cache;
    IMovementExecutor* executor = nullptr;
    bool backtrackingActive = false;

    // Platform-neutral delay helper
    void waitMs(uint16_t ms) {
        if (ms == 0) return;
#ifdef ARDUINO
        delay(ms);
#else
        // Host simulation delay or no-op
#endif
    }

public:
    BacktrackManager() : executor(nullptr), backtrackingActive(false) {}

    explicit BacktrackManager(IMovementExecutor* exec) 
        : executor(exec), backtrackingActive(false) {}

    /**
     * @brief Assigns or changes the hardware movement executor.
     */
    void setExecutor(IMovementExecutor* exec) {
        executor = exec;
    }

    /**
     * @brief Records a movement step without executing it.
     * Use this when your navigation system executes the movement directly
     * and simply informs the backtracking cache of what was done.
     * 
     * @param type Movement direction/type.
     * @param durationMs Duration of the movement in milliseconds.
     * @param speed Speed/throttle (0 - 255).
     * @return true if stored without evicting older steps, false if oldest was dropped.
     */
    bool recordStep(MovementType type, uint16_t durationMs, uint8_t speed = 255) {
        if (type == MovementType::NONE || durationMs == 0) {
            return false;
        }
        return recordStep(Step(type, durationMs, speed));
    }

    /**
     * @brief Records a Step object into the cache.
     */
    bool recordStep(const Step& step) {
        if (!step.isValid()) {
            return false;
        }
        return cache.push(step);
    }

    /**
     * @brief Convenience helper: Executes the step on the attached executor
     *        AND records it to the backtracking cache.
     * 
     * @param step Step to execute and record.
     */
    void executeAndRecord(const Step& step) {
        if (executor && step.isValid()) {
            executor->executeStep(step);
        }
        recordStep(step);
    }

    /**
     * @brief Backtracks all cached steps in reverse order (LIFO).
     * 
     * For every recorded step:
     * 1. Pops the most recent step from the cache.
     * 2. Inverts the step (e.g. FORWARD -> BACKWARD, TURN_LEFT -> TURN_RIGHT).
     * 3. Dispatches the inverse step to the executor.
     * 4. Waits for interStepPauseMs to settle robot inertia before the next step.
     * 
     * @param interStepPauseMs Settling pause in milliseconds between consecutive steps (default: 100ms).
     * @return Total number of steps successfully backtracked.
     */
    size_t backtrackAll(uint16_t interStepPauseMs = 100) {
        return backtrackSteps(cache.size(), interStepPauseMs);
    }

    /**
     * @brief Backtracks up to maxSteps in reverse order.
     * Useful for undoing just the last few actions (e.g., backing away from an obstacle).
     * 
     * @param maxSteps Maximum number of steps to reverse.
     * @param interStepPauseMs Settling pause in milliseconds between steps.
     * @return Number of steps actually backtracked.
     */
    size_t backtrackSteps(size_t maxSteps, uint16_t interStepPauseMs = 100) {
        if (executor == nullptr || cache.isEmpty() || maxSteps == 0) {
            return 0;
        }

        backtrackingActive = true;
        size_t stepsExecuted = 0;
        Step forwardStep;

        while (stepsExecuted < maxSteps && cache.pop(forwardStep)) {
            // Invert the step
            Step inverseStep = StepInverter::invert(forwardStep);

            // Execute the inverted step via the decoupled executor
            executor->executeStep(inverseStep);
            stepsExecuted++;

            // Brief pause between actions so momentum settles on flat ground
            if (interStepPauseMs > 0 && !cache.isEmpty() && stepsExecuted < maxSteps) {
                waitMs(interStepPauseMs);
            }
        }

        // Ensure motors are completely stopped when backtracking finishes
        executor->stop();
        backtrackingActive = false;
        return stepsExecuted;
    }

    /**
     * @brief Clears all cached steps in memory without moving the robot.
     */
    void clearHistory() {
        cache.clear();
    }

    /**
     * @brief Returns the number of steps currently stored in the cache.
     */
    size_t getStepCount() const {
        return cache.size();
    }

    /**
     * @brief Returns the maximum number of steps this manager can store.
     */
    size_t getCapacity() const {
        return cache.capacity();
    }

    /**
     * @brief Returns true if the cache has no recorded steps.
     */
    bool isEmpty() const {
        return cache.isEmpty();
    }

    /**
     * @brief Returns true if the cache is currently at full capacity.
     */
    bool isFull() const {
        return cache.isFull();
    }

    /**
     * @brief Returns true if a backtracking routine is actively executing.
     */
    bool isBacktracking() const {
        return backtrackingActive;
    }

    /**
     * @brief Direct read-only access to peek at the most recent step.
     */
    bool peekLastStep(Step& outStep) const {
        return cache.peek(outStep);
    }
};

#endif // BACKTRACK_MANAGER_H
