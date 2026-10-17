#ifndef STEP_INVERTER_H
#define STEP_INVERTER_H

#include "Step.h"

/**
 * @brief Strategy class responsible for calculating the reciprocal inverse of movement steps.
 * 
 * Completely decoupled from storage, timers, and hardware actuation.
 */
class StepInverter {
public:
    /**
     * @brief Inverts a single MovementType primitive.
     * 
     * @param type The original movement type.
     * @return The opposite movement type (e.g. FORWARD -> BACKWARD, TURN_LEFT -> TURN_RIGHT).
     */
    static MovementType invertType(MovementType type);

    /**
     * @brief Generates an inverted Step with identical duration and speed.
     * 
     * @param step The original forward step.
     * @return The inverse step to retrace the movement.
     */
    static Step invert(const Step& step);
};

#endif // STEP_INVERTER_H
