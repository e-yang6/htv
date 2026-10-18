"""Every setting for follow mode, in one place.

Change a number here, restart follow mode, done. Nothing else needs editing for tuning.
On the UNO Q: copy this file to ~/robot/ and run ~/robot/start_robot.sh.

Angles are degrees (+ = left), distances metres, times seconds.
"""

# --- Wearable (BLE33 running fall_detection/fall_detection.ino) ---
BLE_NAME = "FallDetector"
FOLLOW_CHAR_UUID = "19b10003-e8f2-537e-4f6c-d104768a1214"   # heading, motion, rssi, steps
FALL_CHAR_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214"     # 0 normal, 1 fall detected, 2 emergency
GFORCE_CHAR_UUID = "19b10002-e8f2-537e-4f6c-d104768a1214"   # G-force x100, for the dashboard graph
# When the robot goes to fetch help: 2 = emergency (no double-tap within 5 s; what the dashboard shows
# as "robot dispatched"), 1 = as soon as a fall is detected
RESCUE_ON = 2
YAW_SIGN = 1              # flip to -1 if the robot turns the opposite way to you
DATA_TIMEOUT_S = 1.0      # no BLE33 data for this long = stop

# --- Robot hardware ---
SPEED = 255               # motor command when on (the MOSFETs only do full on / off)
MOTORS_SWAPPED = True     # the robot's left/right motors are wired opposite to (left, right) in the code
TURN_RATE_DPS = 52.1      # how fast it spins on one motor; overridden by turn_rate.json (--calibrate-turn)
# Each direction runs a different motor, so they can differ. Measure with --spin-left / --spin-right;
# None = use TURN_RATE_DPS for that direction.
TURN_RATE_LEFT_DPS = None     # counter-clockwise (right motor only)
TURN_RATE_RIGHT_DPS = None    # clockwise (left motor only)
ROBOT_SPEED_MPS = 0.25    # forward speed; overridden by turn_rate.json (--drive-test / --set-speed)
SEND_HZ = 20              # motor commands per second

# --- Heading: how the robot matches the way you're facing ---
# Your heading is smoothed, then the robot "pulses and settles": one turn sized to the error,
# a pause while it coasts to a stop, then it looks again. No twitching, at the cost of a little delay.
HEADING_TAU_S = 0.6       # smoothing on your heading. Higher = smoother but later; lower = snappier
DEADBAND_DEG = 10          # ignore errors smaller than this (raised automatically if the smallest
                          # possible turn would overshoot it, see MIN_TURN_S)
TURN_GAIN = 1.8           # gyro turns: size of each turn as a share of the error (doubled: real
                          # turns came out about half of what was asked)
CAMERA_TURN_GAIN = 1.0    # turns when the camera sees its target: it measures the real error, so no
                          # boost needed (this is what keeps the doubled gyro turns from overshooting)
MIN_TURN_S = 0.2          # shortest motor pulse that actually moves the robot (friction)
MAX_TURN_S = 2.0          # longest single turn pulse; bigger errors take several
SETTLE_S = 0.25           # pause after a turn so the robot stops coasting before it looks again
TURN_COOLDOWN_S = 0.7     # at least this long between turns (except big ones), so no rapid twitching
BIG_TURN_DEG = 45         # errors bigger than this skip the cooldown
DRIVE_DEADBAND_DEG = 15   # while driving forward, ignore errors smaller than this: keep going straight
PIVOT_DEG = 35            # while driving: further off than this = stop and turn on the spot
BEHIND_DEG = 150          # you're facing back toward the robot = you're coming back; don't spin round
HEADING_JUMP_DEG = 45     # one packet jumping more than this = glitch, unless the next agrees
# Gyro drift: if the BLE33's gyro was moving when it booted, its heading creeps one way on its own
# (seen: 23 deg/s to the left). While you stand still, any steady heading change is drift: measure
# it and subtract it.
DRIFT_FIX = True
STILL_MOTION_MG = 80      # BLE33 motion below this (and no new steps) = you're standing still
                          # (chest-mounted, breathing and sway alone read ~25-60 mg)
DRIFT_WARMUP_S = 4.0      # after connecting, hold still this long and measure the drift
                          # (>= one breathing cycle, so chest sway averages out)
                          # (stand still while it says "learning drift")
DRIFT_WARMUP_TAU_S = 1.0  # how fast a re-measured drift (see below) replaces the old estimate
DRIFT_LEARN_TAU_S = 6.0   # learning speed afterwards (slow: only fine-tunes)
DRIFT_ACCEPT_DPS = 12     # afterwards, only changes this close to the known drift count as drift,
                          # so you turning on the spot is never mistaken for it...
DRIFT_RELEARN_STILL_S = 4.0   # ...except after this long still with a rotation rate that hasn't
                              # changed (drift is constant; a real turn speeds up and slows down):
DRIFT_STEADY_SPREAD_DPS = 4.0 # max spread of the rate over that window to count as drift
                              # (re-learns when the BLE33's drift changes, e.g. it re-calibrates)
MAX_DRIFT_DPS = 40        # never assume more drift than this

# iPhone on the robot as a second check on the robot's own turns (phone_imu.py, Sensor Logger).
# Off: it learned its direction wrong once and pushed the robot off to one side. Turn on only if the
# status line shows the robot heading tracking smoothly with it.
USE_PHONE_HEADING = False

# --- Sticker tracking (camera, Mac only: run_mac.sh) ---
# When the iPhone camera sees the sticker on your pants (target.png), steer straight at it and
# judge distance from its size; when it can't, fall back to the BLE33 gyro + steps as usual.
PATCH_TRACKING = True
PATCH_IMAGE = "target.png"     # the sticker, cut out of a straight-on photo
PATCH_FRESH_S = 0.5            # a sighting older than this doesn't count
PATCH_MIN_SCORE = 0.35         # pattern match needed (0-1); raise if it locks onto other things
PATCH_MIN_PX = 14              # ignore candidates shorter than this (too far / noise)
PATCH_ASPECT_TOL = 0.3         # width/height may differ from the sticker's by this much
PATCH_GREEN_LO, PATCH_GREEN_HI = (30, 60, 50), (90, 255, 255)   # HSV: the green
PATCH_LIGHT_LO, PATCH_LIGHT_HI = (0, 0, 120), (180, 70, 255)    # HSV: the light outline
CAMERA_FOV_DEG = 60.0          # iPhone camera's horizontal view (rough is fine)
PATCH_DEADBAND_DEG = 6         # sticker this close to centre = straight ahead

# --- Click-to-follow (dashboard, Mac only) ---
# Click a person in the dashboard video and the camera locks onto them, so it follows that person
# and doesn't get lost or switch to someone else. Used when the sticker isn't in view.
PERSON_TRACKING = True
PERSON_FRESH_S = 0.8      # a sighting older than this doesn't count
PERSON_LOST_S = 3.0       # not seen for this long = give up the lock (click again)

# --- Distance: how far behind you it stays ---
# Steps from the BLE33 x STEP_LENGTH_M = how far you've walked; minus how far the robot has driven
# = how far ahead you are.
STEP_LENGTH_M = 1.34      # robot distance per step you take (measured stride 0.67 m, doubled: the robot
                          # covers less ground per command than its speed test suggests)
FOLLOW_START_M = 1.2      # you start this far in front of the robot, both facing the same way
FOLLOW_MIN_M = 0.9        # ~3 ft: stop when this close
FOLLOW_MAX_M = 1.5        # ~5 ft: start driving when further than this
DRIVE_ONLY_WHILE_WALKING = True   # stop shortly after you stop walking, instead of catching up any gap
WALKING_GRACE_S = 3.0     # you count as walking for this long after your last step (long, so slow
                          # walking doesn't make it stop and start)
MIN_DRIVE_S = 1.2         # once it starts driving forward, keep going at least this long: big smooth
                          # moves instead of little stuttering ones
MAX_LAG_M = 3.0           # never try to make up more than this (it's ~5x slower than walking)
MAX_GAP_M = 20.0          # supposedly further ahead than this = bad data, stop rather than chase
MAX_STEPS_PER_PACKET = 5  # a bigger jump (or the count going down) = the BLE33 restarted

# --- Signal strength (safety only; far too noisy to steer by) ---
LOST_RSSI = -90           # weaker than this = lost you, stop
NEAR_RSSI = -58           # with --laptop-on-robot: stronger than this = right next to you, don't drive
RSSI_WINDOW_S = 1.5       # median over this window
