#ifndef I_MOVEMENT_EXECUTOR_H
#define I_MOVEMENT_EXECUTOR_H

#include "Step.h"

/**
 * @brief Abstract interface decoupling movement execution (motors, gait, servos)
 *        from the caching and backtracking logic.
 * 
 * Implement this interface when you know your physical motor drivers, H-bridges,
 * servos, or walking gait. The backtracking engine calls this interface without
 * needing any knowledge of pins or physical actuation.
 */
class IMovementExecutor {
public:
    virtual ~IMovementExecutor() = default;

    /**
     * @brief Executes a single movement step in a blocking manner.
     * 
     * Implementations should:
     * 1. Engage hardware actuators according to step.type and step.speed.
     * 2. Wait for step.durationMs (e.g. using delay()).
     * 3. Stop or brake actuators.
     * 
     * @param step The movement command to execute.
     */
    virtual void executeStep(const Step& step) = 0;

    /**
     * @brief Immediately stops all motors and halts robot motion.
     */
    virtual void stop() = 0;
};

#endif // I_MOVEMENT_EXECUTOR_H
