// ============================================================================
// Arduino On-Device Unit Test Runner for Robot Backtracking
// ============================================================================
// Upload this sketch to your Arduino board (Nano 33 BLE, Uno, ESP32, etc.)
// Open Serial Monitor at 115200 baud to view live on-device test results.
// ============================================================================

#include "../../robot_backtrack/Step.h"
#include "../../robot_backtrack/StepInverter.h"
#include "../../robot_backtrack/StepCache.h"
#include "../../robot_backtrack/IMovementExecutor.h"
#include "../../robot_backtrack/BacktrackManager.h"

static int totalTests = 0;
static int passedTests = 0;
static int failedTests = 0;

#define ARDUINO_TEST(name) \
    void name(); \
    void run_##name() { \
        totalTests++; \
        Serial.print(F("[RUN     ] ")); \
        Serial.println(F(#name)); \
        int initialFails = failedTests; \
        name(); \
        if (failedTests == initialFails) { \
            passedTests++; \
            Serial.print(F("[      OK] ")); \
            Serial.println(F(#name)); \
        } else { \
            Serial.print(F("[  FAILED] ")); \
            Serial.println(F(#name)); \
        } \
    } \
    void name()

#define ASSERT_TRUE(cond) \
    do { \
        if (!(cond)) { \
            failedTests++; \
            Serial.print(F("  FAIL: (" #cond ") at line ")); \
            Serial.println(__LINE__); \
            return; \
        } \
    } while (0)

#define ASSERT_FALSE(cond) ASSERT_TRUE(!(cond))

#define ASSERT_EQ(v1, v2) \
    do { \
        if (!((v1) == (v2))) { \
            failedTests++; \
            Serial.print(F("  FAIL: " #v1 " == " #v2 " at line ")); \
            Serial.println(__LINE__); \
            return; \
        } \
    } while (0)

// Spy Executor for Arduino
class ArduinoMockExecutor : public IMovementExecutor {
public:
    Step lastStep;
    int stepCount = 0;
    int stopCount = 0;

    void executeStep(const Step& step) override {
        lastStep = step;
        stepCount++;
    }

    void stop() override {
        stopCount++;
    }

    void reset() {
        stepCount = 0;
        stopCount = 0;
    }
};

ARDUINO_TEST(Test_Step_Basics) {
    Step s1;
    ASSERT_FALSE(s1.isValid());

    Step s2(MovementType::FORWARD, 1000, 200);
    ASSERT_TRUE(s2.isValid());
    ASSERT_EQ((int)s2.type, (int)MovementType::FORWARD);
    ASSERT_EQ(s2.durationMs, 1000);
}

ARDUINO_TEST(Test_StepInverter_Symmetry) {
    ASSERT_EQ((int)StepInverter::invertType(MovementType::FORWARD), (int)MovementType::BACKWARD);
    ASSERT_EQ((int)StepInverter::invertType(MovementType::BACKWARD), (int)MovementType::FORWARD);
    ASSERT_EQ((int)StepInverter::invertType(MovementType::TURN_LEFT), (int)MovementType::TURN_RIGHT);
    ASSERT_EQ((int)StepInverter::invertType(MovementType::TURN_RIGHT), (int)MovementType::TURN_LEFT);

    Step orig(MovementType::TURN_LEFT, 600, 150);
    Step inv = StepInverter::invert(orig);
    ASSERT_EQ((int)inv.type, (int)MovementType::TURN_RIGHT);
    ASSERT_EQ(inv.durationMs, 600);
    ASSERT_EQ(inv.speed, 150);
}

ARDUINO_TEST(Test_StepCache_LIFO) {
    StepCache<4> cache;
    ASSERT_TRUE(cache.isEmpty());

    cache.push(Step(MovementType::FORWARD, 100));
    cache.push(Step(MovementType::TURN_LEFT, 200));

    ASSERT_EQ(cache.size(), 2);

    Step s;
    ASSERT_TRUE(cache.pop(s));
    ASSERT_EQ((int)s.type, (int)MovementType::TURN_LEFT);

    ASSERT_TRUE(cache.pop(s));
    ASSERT_EQ((int)s.type, (int)MovementType::FORWARD);

    ASSERT_TRUE(cache.isEmpty());
}

ARDUINO_TEST(Test_StepCache_RingEviction) {
    StepCache<2> cache;
    cache.push(Step(MovementType::FORWARD, 100));
    cache.push(Step(MovementType::TURN_LEFT, 200));
    // Overwrite oldest
    cache.push(Step(MovementType::BACKWARD, 300));

    ASSERT_EQ(cache.size(), 2);

    Step s;
    ASSERT_TRUE(cache.pop(s));
    ASSERT_EQ(s.durationMs, 300);

    ASSERT_TRUE(cache.pop(s));
    ASSERT_EQ(s.durationMs, 200);

    ASSERT_TRUE(cache.isEmpty());
}

ARDUINO_TEST(Test_BacktrackManager_Workflow) {
    ArduinoMockExecutor mock;
    BacktrackManager<8> mgr(&mock);

    mgr.recordStep(MovementType::FORWARD, 1000);
    mgr.recordStep(MovementType::TURN_LEFT, 500);

    ASSERT_EQ(mgr.getStepCount(), 2);
    ASSERT_EQ(mock.stepCount, 0);

    size_t count = mgr.backtrackAll(0);
    ASSERT_EQ(count, 2);
    ASSERT_EQ(mock.stepCount, 2);
    ASSERT_EQ(mock.stopCount, 1);
    ASSERT_TRUE(mgr.isEmpty());
}

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 3000);

    Serial.println(F("\n=========================================="));
    Serial.println(F("  ARDUINO ON-DEVICE BACKTRACK UNIT TESTS  "));
    Serial.println(F("=========================================="));

    run_Test_Step_Basics();
    run_Test_StepInverter_Symmetry();
    run_Test_StepCache_LIFO();
    run_Test_StepCache_RingEviction();
    run_Test_BacktrackManager_Workflow();

    Serial.println(F("\n------------------------------------------"));
    Serial.print(F("Total Tests: "));
    Serial.println(totalTests);
    Serial.print(F("Passed:      "));
    Serial.println(passedTests);
    Serial.print(F("Failed:      "));
    Serial.println(failedTests);

    if (failedTests == 0) {
        Serial.println(F(">>> ALL TESTS PASSED! <<<"));
    } else {
        Serial.println(F(">>> SOME TESTS FAILED! <<<"));
    }
    Serial.println(F("==========================================\n"));
}

void loop() {}
