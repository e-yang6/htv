#include "StepInverter.h"

MovementType StepInverter::invertType(MovementType type) {
    switch (type) {
        case MovementType::FORWARD:
            return MovementType::BACKWARD;

        case MovementType::BACKWARD:
            return MovementType::FORWARD;

        case MovementType::TURN_LEFT:
            return MovementType::TURN_RIGHT;

        case MovementType::TURN_RIGHT:
            return MovementType::TURN_LEFT;

        case MovementType::STRAFE_LEFT:
            return MovementType::STRAFE_RIGHT;

        case MovementType::STRAFE_RIGHT:
            return MovementType::STRAFE_LEFT;

        case MovementType::PIVOT_LEFT:
            return MovementType::PIVOT_RIGHT;

        case MovementType::PIVOT_RIGHT:
            return MovementType::PIVOT_LEFT;

        case MovementType::PAUSE:
            // Pausing in reverse is still pausing
            return MovementType::PAUSE;

        case MovementType::NONE:
        default:
            return MovementType::NONE;
    }
}

Step StepInverter::invert(const Step& step) {
    return Step(invertType(step.type), step.durationMs, step.speed);
}
