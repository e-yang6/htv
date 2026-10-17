#ifndef STEP_H
#define STEP_H

#include <stdint.h>
#include <stddef.h>

/**
 * @brief Discrete movement types that the robot can perform.
 * 
 * Every movement type in this enum has a corresponding inverse movement.
 */
enum class MovementType : uint8_t {
    NONE = 0,
    FORWARD,
    BACKWARD,
    TURN_LEFT,
    TURN_RIGHT,
    STRAFE_LEFT,
    STRAFE_RIGHT,
    PIVOT_LEFT,
    PIVOT_RIGHT,
    PAUSE
};

/**
 * @brief Represents a single movement step taken by the robot.
 * 
 * Memory footprint: 4 bytes (1 byte type + 2 bytes duration + 1 byte speed).
 * Highly compact for embedded microcontrollers with constrained SRAM.
 */
struct Step {
    MovementType type;      // Type of movement primitive
    uint16_t durationMs;    // Time duration of the movement in milliseconds
    uint8_t speed;          // Speed or throttle value (0 - 255), defaults to 255 (full)

    // Default constructor
    Step() 
        : type(MovementType::NONE), durationMs(0), speed(255) {}

    // Parameterized constructor
    Step(MovementType t, uint16_t duration, uint8_t spd = 255)
        : type(t), durationMs(duration), speed(spd) {}

    // Check if step represents a valid executable motion
    bool isValid() const {
        return type != MovementType::NONE && durationMs > 0;
    }

    // Human-readable string representation for debugging and serial logs
    const char* getTypeName() const {
        switch (type) {
            case MovementType::FORWARD:      return "FORWARD";
            case MovementType::BACKWARD:     return "BACKWARD";
            case MovementType::TURN_LEFT:    return "TURN_LEFT";
            case MovementType::TURN_RIGHT:   return "TURN_RIGHT";
            case MovementType::STRAFE_LEFT:  return "STRAFE_LEFT";
            case MovementType::STRAFE_RIGHT: return "STRAFE_RIGHT";
            case MovementType::PIVOT_LEFT:   return "PIVOT_LEFT";
            case MovementType::PIVOT_RIGHT:  return "PIVOT_RIGHT";
            case MovementType::PAUSE:        return "PAUSE";
            case MovementType::NONE:
            default:                         return "NONE";
        }
    }
};

#endif // STEP_H
