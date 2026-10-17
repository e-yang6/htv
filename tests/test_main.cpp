#include <iostream>
#include <vector>
#include <string>
#include <cassert>
#include <iomanip>

// Include the backtrack subsystem headers
#include "../robot_backtrack/Step.h"
#include "../robot_backtrack/StepInverter.h"
#include "../robot_backtrack/StepCache.h"
#include "../robot_backtrack/IMovementExecutor.h"
#include "../robot_backtrack/BacktrackManager.h"

// ----------------------------------------------------------------------------
// Simple Lightweight Test Framework
// ----------------------------------------------------------------------------
static int totalTests = 0;
static int passedTests = 0;
static int failedTests = 0;

#define TEST_CASE(name) \
    void name(); \
    struct Register_##name { \
        Register_##name() { \
            std::cout << "[RUN     ] " << #name << std::endl; \
            totalTests++; \
            try { \
                name(); \
                passedTests++; \
                std::cout << "[      OK] " << #name << std::endl; \
            } catch (const std::exception& e) { \
                failedTests++; \
                std::cout << "[  FAILED] " << #name << " (Exception: " << e.what() << ")" << std::endl; \
            } catch (...) { \
                failedTests++; \
                std::cout << "[  FAILED] " << #name << " (Unknown Exception)" << std::endl; \
            } \
        } \
    } instance_##name; \
    void name()

#define ASSERT_TRUE(condition) \
    do { \
        if (!(condition)) { \
            std::cerr << "  Assertion Failed: (" #condition ") at " << __FILE__ << ":" << __LINE__ << std::endl; \
            throw std::runtime_error("Assertion failed: " #condition); \
        } \
    } while (0)

#define ASSERT_FALSE(condition) ASSERT_TRUE(!(condition))

#define ASSERT_EQ(val1, val2) \
    do { \
        if (!((val1) == (val2))) { \
            std::cerr << "  Assertion Failed: " #val1 " == " #val2 " (" << (val1) << " != " << (val2) << ") at " << __FILE__ << ":" << __LINE__ << std::endl; \
            throw std::runtime_error("Assertion failed: " #val1 " == " #val2); \
        } \
    } while (0)

// ----------------------------------------------------------------------------
// Mock Movement Executor (Spy) for Testing
// ----------------------------------------------------------------------------
class MockMovementExecutor : public IMovementExecutor {
public:
    std::vector<Step> executedSteps;
    int stopCount = 0;

    void executeStep(const Step& step) override {
        executedSteps.push_back(step);
    }

    void stop() override {
        stopCount++;
    }

    void clear() {
        executedSteps.clear();
        stopCount = 0;
    }
};

// ============================================================================
// SUITE 1: Step Model Tests
// ============================================================================

TEST_CASE(Test_Step_DefaultConstructor) {
    Step s;
    ASSERT_EQ((int)s.type, (int)MovementType::NONE);
    ASSERT_EQ(s.durationMs, 0);
    ASSERT_EQ(s.speed, 255);
    ASSERT_FALSE(s.isValid());
}

TEST_CASE(Test_Step_ParameterizedConstructor) {
    Step s(MovementType::FORWARD, 1500, 180);
    ASSERT_EQ((int)s.type, (int)MovementType::FORWARD);
    ASSERT_EQ(s.durationMs, 1500);
    ASSERT_EQ(s.speed, 180);
    ASSERT_TRUE(s.isValid());
}

TEST_CASE(Test_Step_ValidityCheck) {
    // Type is NONE
    Step s1(MovementType::NONE, 1000);
    ASSERT_FALSE(s1.isValid());

    // Duration is 0
    Step s2(MovementType::FORWARD, 0);
    ASSERT_FALSE(s2.isValid());

    // Valid step
    Step s3(MovementType::TURN_LEFT, 500);
    ASSERT_TRUE(s3.isValid());
}

TEST_CASE(Test_Step_TypeNameStrings) {
    ASSERT_EQ(std::string(Step(MovementType::FORWARD, 100).getTypeName()), "FORWARD");
    ASSERT_EQ(std::string(Step(MovementType::BACKWARD, 100).getTypeName()), "BACKWARD");
    ASSERT_EQ(std::string(Step(MovementType::TURN_LEFT, 100).getTypeName()), "TURN_LEFT");
    ASSERT_EQ(std::string(Step(MovementType::TURN_RIGHT, 100).getTypeName()), "TURN_RIGHT");
    ASSERT_EQ(std::string(Step(MovementType::STRAFE_LEFT, 100).getTypeName()), "STRAFE_LEFT");
    ASSERT_EQ(std::string(Step(MovementType::STRAFE_RIGHT, 100).getTypeName()), "STRAFE_RIGHT");
    ASSERT_EQ(std::string(Step(MovementType::PIVOT_LEFT, 100).getTypeName()), "PIVOT_LEFT");
    ASSERT_EQ(std::string(Step(MovementType::PIVOT_RIGHT, 100).getTypeName()), "PIVOT_RIGHT");
    ASSERT_EQ(std::string(Step(MovementType::PAUSE, 100).getTypeName()), "PAUSE");
}

// ============================================================================
// SUITE 2: Step Inverter Tests
// ============================================================================

TEST_CASE(Test_StepInverter_DirectPairs) {
    ASSERT_EQ((int)StepInverter::invertType(MovementType::FORWARD), (int)MovementType::BACKWARD);
    ASSERT_EQ((int)StepInverter::invertType(MovementType::BACKWARD), (int)MovementType::FORWARD);

    ASSERT_EQ((int)StepInverter::invertType(MovementType::TURN_LEFT), (int)MovementType::TURN_RIGHT);
    ASSERT_EQ((int)StepInverter::invertType(MovementType::TURN_RIGHT), (int)MovementType::TURN_LEFT);

    ASSERT_EQ((int)StepInverter::invertType(MovementType::STRAFE_LEFT), (int)MovementType::STRAFE_RIGHT);
    ASSERT_EQ((int)StepInverter::invertType(MovementType::STRAFE_RIGHT), (int)MovementType::STRAFE_LEFT);

    ASSERT_EQ((int)StepInverter::invertType(MovementType::PIVOT_LEFT), (int)MovementType::PIVOT_RIGHT);
    ASSERT_EQ((int)StepInverter::invertType(MovementType::PIVOT_RIGHT), (int)MovementType::PIVOT_LEFT);

    ASSERT_EQ((int)StepInverter::invertType(MovementType::PAUSE), (int)MovementType::PAUSE);
    ASSERT_EQ((int)StepInverter::invertType(MovementType::NONE), (int)MovementType::NONE);
}

TEST_CASE(Test_StepInverter_PreservesDurationAndSpeed) {
    Step original(MovementType::TURN_LEFT, 750, 190);
    Step inverted = StepInverter::invert(original);

    ASSERT_EQ((int)inverted.type, (int)MovementType::TURN_RIGHT);
    ASSERT_EQ(inverted.durationMs, 750);
    ASSERT_EQ(inverted.speed, 190);
}

TEST_CASE(Test_StepInverter_DoubleInversionIdempotency) {
    std::vector<MovementType> allTypes = {
        MovementType::FORWARD, MovementType::BACKWARD,
        MovementType::TURN_LEFT, MovementType::TURN_RIGHT,
        MovementType::STRAFE_LEFT, MovementType::STRAFE_RIGHT,
        MovementType::PIVOT_LEFT, MovementType::PIVOT_RIGHT,
        MovementType::PAUSE
    };

    for (MovementType t : allTypes) {
        Step original(t, 1200, 200);
        Step doubleInverted = StepInverter::invert(StepInverter::invert(original));
        ASSERT_EQ((int)doubleInverted.type, (int)original.type);
        ASSERT_EQ(doubleInverted.durationMs, original.durationMs);
        ASSERT_EQ(doubleInverted.speed, original.speed);
    }
}

// ============================================================================
// SUITE 3: StepCache Tests
// ============================================================================

TEST_CASE(Test_StepCache_InitialState) {
    StepCache<16> cache;
    ASSERT_TRUE(cache.isEmpty());
    ASSERT_FALSE(cache.isFull());
    ASSERT_EQ(cache.size(), 0);
    ASSERT_EQ(cache.capacity(), 16);

    Step dummy;
    ASSERT_FALSE(cache.pop(dummy));
    ASSERT_FALSE(cache.peek(dummy));
}

TEST_CASE(Test_StepCache_PushPopSingle) {
    StepCache<8> cache;
    Step input(MovementType::FORWARD, 1000, 250);
    ASSERT_TRUE(cache.push(input));
    ASSERT_EQ(cache.size(), 1);
    ASSERT_FALSE(cache.isEmpty());

    Step output;
    ASSERT_TRUE(cache.pop(output));
    ASSERT_EQ((int)output.type, (int)MovementType::FORWARD);
    ASSERT_EQ(output.durationMs, 1000);
    ASSERT_EQ(output.speed, 250);
    ASSERT_TRUE(cache.isEmpty());
}

TEST_CASE(Test_StepCache_LIFOOrder) {
    StepCache<8> cache;
    cache.push(Step(MovementType::FORWARD, 100));
    cache.push(Step(MovementType::TURN_LEFT, 200));
    cache.push(Step(MovementType::BACKWARD, 300));

    ASSERT_EQ(cache.size(), 3);

    Step s;
    // 1st pop should be the last step pushed (BACKWARD 300)
    ASSERT_TRUE(cache.pop(s));
    ASSERT_EQ((int)s.type, (int)MovementType::BACKWARD);
    ASSERT_EQ(s.durationMs, 300);

    // 2nd pop should be TURN_LEFT 200
    ASSERT_TRUE(cache.pop(s));
    ASSERT_EQ((int)s.type, (int)MovementType::TURN_LEFT);
    ASSERT_EQ(s.durationMs, 200);

    // 3rd pop should be FORWARD 100
    ASSERT_TRUE(cache.pop(s));
    ASSERT_EQ((int)s.type, (int)MovementType::FORWARD);
    ASSERT_EQ(s.durationMs, 100);

    // Now empty
    ASSERT_FALSE(cache.pop(s));
    ASSERT_TRUE(cache.isEmpty());
}

TEST_CASE(Test_StepCache_PeekDoesNotRemove) {
    StepCache<4> cache;
    cache.push(Step(MovementType::TURN_RIGHT, 450));

    Step peeked;
    ASSERT_TRUE(cache.peek(peeked));
    ASSERT_EQ((int)peeked.type, (int)MovementType::TURN_RIGHT);
    ASSERT_EQ(peeked.durationMs, 450);
    ASSERT_EQ(cache.size(), 1); // Size unchanged!

    Step popped;
    ASSERT_TRUE(cache.pop(popped));
    ASSERT_EQ((int)popped.type, (int)MovementType::TURN_RIGHT);
    ASSERT_TRUE(cache.isEmpty());
}

TEST_CASE(Test_StepCache_Clear) {
    StepCache<4> cache;
    cache.push(Step(MovementType::FORWARD, 100));
    cache.push(Step(MovementType::FORWARD, 200));
    ASSERT_EQ(cache.size(), 2);

    cache.clear();
    ASSERT_TRUE(cache.isEmpty());
    ASSERT_EQ(cache.size(), 0);

    Step dummy;
    ASSERT_FALSE(cache.pop(dummy));
}

TEST_CASE(Test_StepCache_CircularOverwriteEviction) {
    // Capacity of exactly 3 steps
    StepCache<3> cache;

    // Push 3 steps -> Cache is full
    ASSERT_TRUE(cache.push(Step(MovementType::FORWARD, 100)));
    ASSERT_TRUE(cache.push(Step(MovementType::TURN_LEFT, 200)));
    ASSERT_TRUE(cache.push(Step(MovementType::FORWARD, 300)));
    ASSERT_TRUE(cache.isFull());
    ASSERT_EQ(cache.size(), 3);

    // Push 4th step -> Should return false (signaling eviction of oldest: FORWARD 100)
    ASSERT_FALSE(cache.push(Step(MovementType::TURN_RIGHT, 400)));
    ASSERT_TRUE(cache.isFull());
    ASSERT_EQ(cache.size(), 3);

    // Push 5th step -> Evicts TURN_LEFT 200
    ASSERT_FALSE(cache.push(Step(MovementType::BACKWARD, 500)));
    ASSERT_TRUE(cache.isFull());
    ASSERT_EQ(cache.size(), 3);

    // Verify LIFO order of remaining items: [500, 400, 300]
    Step s;
    ASSERT_TRUE(cache.pop(s));
    ASSERT_EQ(s.durationMs, 500);
    ASSERT_EQ((int)s.type, (int)MovementType::BACKWARD);

    ASSERT_TRUE(cache.pop(s));
    ASSERT_EQ(s.durationMs, 400);
    ASSERT_EQ((int)s.type, (int)MovementType::TURN_RIGHT);

    ASSERT_TRUE(cache.pop(s));
    ASSERT_EQ(s.durationMs, 300);
    ASSERT_EQ((int)s.type, (int)MovementType::FORWARD);

    ASSERT_TRUE(cache.isEmpty());
}

// ============================================================================
// SUITE 4: BacktrackManager Orchestration Tests
// ============================================================================

TEST_CASE(Test_BacktrackManager_RecordOnly) {
    MockMovementExecutor mock;
    BacktrackManager<16> mgr(&mock);

    ASSERT_TRUE(mgr.recordStep(MovementType::FORWARD, 1000));
    ASSERT_TRUE(mgr.recordStep(MovementType::TURN_LEFT, 500));

    // Cache count should be 2
    ASSERT_EQ(mgr.getStepCount(), 2);
    // Executor should NOT have executed anything during record-only
    ASSERT_EQ(mock.executedSteps.size(), 0);
}

TEST_CASE(Test_BacktrackManager_RejectsInvalidStep) {
    MockMovementExecutor mock;
    BacktrackManager<16> mgr(&mock);

    ASSERT_FALSE(mgr.recordStep(MovementType::NONE, 500));
    ASSERT_FALSE(mgr.recordStep(MovementType::FORWARD, 0));
    ASSERT_EQ(mgr.getStepCount(), 0);
}

TEST_CASE(Test_BacktrackManager_ExecuteAndRecord) {
    MockMovementExecutor mock;
    BacktrackManager<16> mgr(&mock);

    Step s(MovementType::FORWARD, 1200, 220);
    mgr.executeAndRecord(s);

    ASSERT_EQ(mgr.getStepCount(), 1);
    ASSERT_EQ(mock.executedSteps.size(), 1);
    ASSERT_EQ((int)mock.executedSteps[0].type, (int)MovementType::FORWARD);
    ASSERT_EQ(mock.executedSteps[0].durationMs, 1200);
}

TEST_CASE(Test_BacktrackManager_FullBacktrackSequence) {
    MockMovementExecutor mock;
    BacktrackManager<16> mgr(&mock);

    // Record exploration route:
    // 1. Forward 1000ms
    // 2. Turn Left 500ms
    // 3. Forward 1500ms
    // 4. Turn Right 400ms
    mgr.recordStep(MovementType::FORWARD, 1000);
    mgr.recordStep(MovementType::TURN_LEFT, 500);
    mgr.recordStep(MovementType::FORWARD, 1500);
    mgr.recordStep(MovementType::TURN_RIGHT, 400);

    ASSERT_EQ(mgr.getStepCount(), 4);

    // Run backtrack
    size_t count = mgr.backtrackAll(0);
    ASSERT_EQ(count, 4);
    ASSERT_TRUE(mgr.isEmpty());

    // Verify executor received inverted steps in reverse order
    ASSERT_EQ(mock.executedSteps.size(), 4);

    // 1st reverse step: Turn Left 400ms (inversion of Turn Right 400ms)
    ASSERT_EQ((int)mock.executedSteps[0].type, (int)MovementType::TURN_LEFT);
    ASSERT_EQ(mock.executedSteps[0].durationMs, 400);

    // 2nd reverse step: Backward 1500ms (inversion of Forward 1500ms)
    ASSERT_EQ((int)mock.executedSteps[1].type, (int)MovementType::BACKWARD);
    ASSERT_EQ(mock.executedSteps[1].durationMs, 1500);

    // 3rd reverse step: Turn Right 500ms (inversion of Turn Left 500ms)
    ASSERT_EQ((int)mock.executedSteps[2].type, (int)MovementType::TURN_RIGHT);
    ASSERT_EQ(mock.executedSteps[2].durationMs, 500);

    // 4th reverse step: Backward 1000ms (inversion of Forward 1000ms)
    ASSERT_EQ((int)mock.executedSteps[3].type, (int)MovementType::BACKWARD);
    ASSERT_EQ(mock.executedSteps[3].durationMs, 1000);

    // Motors must be stopped at conclusion
    ASSERT_EQ(mock.stopCount, 1);
}

TEST_CASE(Test_BacktrackManager_PartialBacktrack) {
    MockMovementExecutor mock;
    BacktrackManager<16> mgr(&mock);

    mgr.recordStep(MovementType::FORWARD, 1000);
    mgr.recordStep(MovementType::TURN_LEFT, 500);
    mgr.recordStep(MovementType::FORWARD, 600);

    // Backtrack only the last 1 step (e.g. undoing a bump sensor collision)
    size_t count = mgr.backtrackSteps(1, 0);
    ASSERT_EQ(count, 1);
    ASSERT_EQ(mgr.getStepCount(), 2); // 2 steps still remain

    // Should have reversed Forward 600ms -> Backward 600ms
    ASSERT_EQ(mock.executedSteps.size(), 1);
    ASSERT_EQ((int)mock.executedSteps[0].type, (int)MovementType::BACKWARD);
    ASSERT_EQ(mock.executedSteps[0].durationMs, 600);
}

TEST_CASE(Test_BacktrackManager_EmptyBacktrackSafe) {
    MockMovementExecutor mock;
    BacktrackManager<16> mgr(&mock);

    // Backtracking on empty cache
    size_t count = mgr.backtrackAll(0);
    ASSERT_EQ(count, 0);
    ASSERT_EQ(mock.executedSteps.size(), 0);
    ASSERT_EQ(mock.stopCount, 0);
}

// ============================================================================
// MAIN RUNNER
// ============================================================================
int main() {
    std::cout << "\n========================================" << std::endl;
    std::cout << "  ROBOT BACKTRACK SUBSYSTEM TEST SUITE  " << std::endl;
    std::cout << "========================================" << std::endl;

    std::cout << "\nTotal Test Cases: " << totalTests << std::endl;
    std::cout << "Passed:           " << passedTests << std::endl;
    std::cout << "Failed:           " << failedTests << std::endl;

    if (failedTests == 0) {
        std::cout << "\n>>> ALL UNIT TESTS PASSED SUCCESSFULLY! <<<\n" << std::endl;
        return 0;
    } else {
        std::cout << "\n>>> SOME TESTS FAILED! <<<\n" << std::endl;
        return 1;
    }
}
