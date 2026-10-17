#ifndef STEP_CACHE_H
#define STEP_CACHE_H

#include "Step.h"

/**
 * @brief Zero-heap, fixed-capacity circular LIFO stack for step caching.
 * 
 * Design characteristics:
 * 1. Zero dynamic memory allocation (avoids heap fragmentation on microcontrollers).
 * 2. Circular overflow protection: when the cache reaches CAPACITY, pushing a new step
 *    gracefully drops the oldest step so the robot can always backtrack the most recent N steps.
 * 3. Constant-time O(1) push, pop, and peek operations.
 * 
 * @tparam CAPACITY Maximum number of steps stored concurrently (default = 64).
 */
template <size_t CAPACITY = 64>
class StepCache {
private:
    Step buffer[CAPACITY];
    size_t head = 0;   // Index where the next pushed step will be stored
    size_t count = 0;  // Current number of steps in the cache

public:
    StepCache() : head(0), count(0) {}

    /**
     * @brief Pushes a step into the cache.
     * If the cache is full, the oldest step is evicted to make room.
     * 
     * @param step The step to record.
     * @return true if pushed without eviction, false if an old step had to be overwritten.
     */
    bool push(const Step& step) {
        bool wasOverwritten = (count == CAPACITY);

        buffer[head] = step;
        head = (head + 1) % CAPACITY;

        if (count < CAPACITY) {
            count++;
        }

        return !wasOverwritten;
    }

    /**
     * @brief Pops the most recently added step (LIFO order for backtracking).
     * 
     * @param outStep Destination reference to store the popped step.
     * @return true if a step was successfully popped, false if cache was empty.
     */
    bool pop(Step& outStep) {
        if (count == 0) {
            return false;
        }

        head = (head + CAPACITY - 1) % CAPACITY;
        outStep = buffer[head];
        count--;
        return true;
    }

    /**
     * @brief Inspects the most recently added step without removing it.
     * 
     * @param outStep Destination reference to store the inspected step.
     * @return true if valid step exists, false if cache is empty.
     */
    bool peek(Step& outStep) const {
        if (count == 0) {
            return false;
        }

        size_t lastIndex = (head + CAPACITY - 1) % CAPACITY;
        outStep = buffer[lastIndex];
        return true;
    }

    /**
     * @brief Clears all cached steps.
     */
    void clear() {
        head = 0;
        count = 0;
    }

    /**
     * @brief Returns current number of cached steps.
     */
    size_t size() const {
        return count;
    }

    /**
     * @brief Returns the maximum capacity of this cache.
     */
    size_t capacity() const {
        return CAPACITY;
    }

    /**
     * @brief Checks if the cache contains no steps.
     */
    bool isEmpty() const {
        return count == 0;
    }

    /**
     * @brief Checks if the cache has reached maximum capacity.
     */
    bool isFull() const {
        return count >= CAPACITY;
    }
};

#endif // STEP_CACHE_H
