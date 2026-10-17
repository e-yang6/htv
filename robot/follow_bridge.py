"""Follow-me bridge: wearable BLE33 (FallDetector) -> this machine -> Meccanoid robot.

The robot (Uno, no BLE) is plugged in over USB. This script reads the wearer's
heading, motion and signal strength from the BLE33 and streams "<left,right>"
motor frames to the robot (see robot/meccanoid_follow).

Signal strength is measured between the BLE33 and THIS machine, so it only
means "distance to the robot" if this machine rides with the robot.

Start with the robot facing the same way as the wearer, then run:
    python follow_bridge.py --port /dev/cu.usbmodem1101
"""
import argparse
import glob
import os
import asyncio
import math
import struct
import threading
import time
from collections import deque

import serial

ARDUINO_NAME = "FallDetector"
FOLLOW_CHAR_UUID = "19b10003-e8f2-537e-4f6c-d104768a1214"
FALL_CHAR_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214"   # 0 normal, 1 fall detected, 2 emergency

# --- Tunables ---
SPEED = 255               # full speed works best with the 5N65 MOSFETs
TURN_RATE_DPS = 90.0      # how fast the robot spins with one motor on; overridden by turn_rate.json (--calibrate-turn)
YAW_SIGN = 1              # flip if the robot turns the opposite way to the wearer
MOTORS_SWAPPED = True     # the robot's left/right motors are wired opposite to (left, right) in the code
SEND_HZ = 20              # 20 Hz = finer turns (~2.6 deg per tick); the Uno accepts it fine
DATA_TIMEOUT_S = 1.0

# --- Following ---
# Steering: the robot matches the wearer's gyro heading directly, so it reacts to even small turns.
# Distance: the BLE33 counts steps; distance walked (steps x STEP_LENGTH_M) minus distance the
# robot has driven = how far ahead the wearer is. The robot keeps that at FOLLOW_MIN_M..FOLLOW_MAX_M.
MAX_STEPS_PER_PACKET = 5  # a bigger jump (or the count going down) = the BLE33 restarted
STEP_LENGTH_M = 0.67      # measured: 8 m walked = 12 counted steps (includes start/stop shuffle)
ROBOT_SPEED_MPS = 0.3     # robot speed with both motors on; overridden by turn_rate.json (--drive-test)
FOLLOW_START_M = 1.2      # the wearer starts this far in front of the robot, both facing the same way
FOLLOW_MIN_M = 0.9        # ~3 ft: stop when this close
FOLLOW_MAX_M = 1.5        # ~5 ft: start driving when further than this
MAX_GAP_M = 20.0          # wearer supposedly further ahead than this = something's wrong, stop
TURN_START_DEG = 5        # start correcting when the robot is this far off the wearer's heading
TURN_STOP_DEG = 2         # keep correcting until this close (one 20 Hz tick turns ~2.6 deg)
PIVOT_DEG = 30            # further off than this = turn on the spot, even while driving
ARC_FULL_DEG = 20         # while driving, this far off = arc as tight as it goes
BEHIND_DEG = 150          # wearer facing back toward the robot = they're coming back; don't spin round
# Dual checks: don't act on a single odd reading or flip-flop between decisions
HEADING_JUMP_DEG = 45     # wearer heading jumping more than this between packets = glitch unless the next agrees
CONFIRM_TICKS = 2         # a new move (not a stop) must be wanted this many ticks in a row
REVERSE_HOLD_S = 0.3      # after turning one way, wait this long before turning the other way
HEADING_SMOOTH = 0.6      # 0-1, higher = reacts to the wearer's gyro faster (less smoothing)
MOTION_SMOOTH = 0.4       # 0-1 smoothing on the motion level (display only)

# Signal strength is only used as a safety gate, it's too noisy (+-5 dB) to steer by
NEAR_RSSI = -58           # --laptop-on-robot: stronger than this = right next to the wearer, never drive
LOST_RSSI = -90           # weaker than this = lost the wearer, stop
RSSI_WINDOW_S = 1.5       # RSSI is a median over this window


def wrap(deg):
    return (deg + 180) % 360 - 180


def median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2]


class Follower:
    def __init__(self, use_rssi=False):
        self.use_rssi = use_rssi
        self.heading_zero = None
        self.person_heading = None   # wearer's heading in the robot's frame, lightly smoothed
        self.rx = self.ry = 0.0      # robot pose (m, deg), dead-reckoned from the commands we send
        self.robot_heading = 0.0
        self.walked = 0.0            # metres the wearer has walked since sync
        self.driven = 0.0            # metres the robot has driven since sync
        self.steps = None            # last step count from the BLE33
        self.has_steps = False       # False = old firmware without step counting
        self.rssi_samples = deque()  # (time, dBm)
        self.rssi = None
        self.motion = 0
        self.motion_smooth = 0.0
        self.driving = False
        self.turning = False
        self.turn_acc = 0.0
        self.gap = FOLLOW_START_M
        self.last_data = 0.0
        self.fall = 0                # latest fall status from the BLE33
        self.raw_heading = None      # last accepted raw heading from the BLE33
        self.jump_pending = None     # a big heading jump waiting for a second packet to confirm it
        self.wanted = (0, 0)         # last decision, and how many ticks in a row it's been wanted
        self.wanted_ticks = 0
        self.last_turn_dir = 0
        self.last_turn_t = 0.0
        self.packets = 0             # BLE packets since the last status line
        self.worst_gap = 0.0         # longest gap between BLE packets since the last status line
        self.cmd = (0, 0)
        self.state = "waiting for BLE33"

    def resync(self, raw_heading=None):
        """Wearer is FOLLOW_START_M in front of the robot, facing the same way.
        Called on every (re)connect, since the BLE33's heading and step count may have restarted."""
        self.walked = self.driven = 0.0
        self.driving = self.turning = False
        self.steps = None
        self.heading_zero = None if raw_heading is None else raw_heading - self.robot_heading
        self.person_heading = None if raw_heading is None else self.robot_heading

    def reset_distance(self):
        """After a go-to-person trip the robot moved on its own: assume it's FOLLOW_START_M behind again."""
        self.walked = self.driven = 0.0
        self.driving = False

    def on_data(self, _sender, data):
        data = bytes(data)
        heading, _rate, motion, rssi = struct.unpack("<hhBb", data[:6])
        heading = YAW_SIGN * heading / 10
        # Dual check: a huge jump in one packet is a glitch unless the next packet agrees
        if self.raw_heading is not None and abs(wrap(heading - self.raw_heading)) > HEADING_JUMP_DEG:
            if self.jump_pending is None or abs(wrap(heading - self.jump_pending)) > HEADING_JUMP_DEG:
                self.jump_pending = heading
                heading = self.raw_heading          # hold the old value for now
            else:
                self.jump_pending = None            # confirmed: it really moved
        else:
            self.jump_pending = None
        self.raw_heading = heading
        if self.heading_zero is None:
            self.heading_zero = heading - self.robot_heading
        h = wrap(heading - self.heading_zero)
        if self.person_heading is None:
            self.person_heading = h
        else:
            self.person_heading = wrap(self.person_heading + HEADING_SMOOTH * wrap(h - self.person_heading))
        self.motion = motion
        self.motion_smooth += MOTION_SMOOTH * (motion - self.motion_smooth)

        if len(data) >= 8:
            self.has_steps = True
            steps = struct.unpack("<H", data[6:8])[0]
            if self.steps is not None:
                new = (steps - self.steps) & 0xFFFF
                if new > MAX_STEPS_PER_PACKET:
                    print(f"Step count jumped {self.steps} -> {steps}: BLE33 restarted, re-syncing")
                    self.resync(heading)
                else:
                    self.walked += new * STEP_LENGTH_M
            self.steps = steps

        now = time.monotonic()
        if rssi < 0:
            self.rssi_samples.append((now, rssi))
        while self.rssi_samples and now - self.rssi_samples[0][0] > RSSI_WINDOW_S:
            self.rssi_samples.popleft()
        if self.rssi_samples:
            self.rssi = median([r for _, r in self.rssi_samples])
        if self.last_data:
            self.worst_gap = max(self.worst_gap, now - self.last_data)
        self.packets += 1
        self.last_data = now

    def track(self, cmd, dt, dheading=None):
        """Dead-reckon the robot from the command that was actually sent.
        dheading: measured heading change (camera), otherwise worked out from the turn rate."""
        l, r = cmd
        if dheading is None:
            if l and not r:
                dheading = -TURN_RATE_DPS * dt   # left wheel only -> turns right
            elif r and not l:
                dheading = TURN_RATE_DPS * dt
            else:
                dheading = 0.0
        self.robot_heading = wrap(self.robot_heading + dheading)
        # Both wheels = full speed; one wheel = pivot, the middle moves at half speed
        v = ROBOT_SPEED_MPS if (l and r) else ROBOT_SPEED_MPS / 2 if (l or r) else 0.0
        a = math.radians(self.robot_heading)
        self.rx += v * math.cos(a) * dt
        self.ry += v * math.sin(a) * dt
        self.driven += v * dt

    def stop(self, state):
        self.state = state
        self.driving = False
        self.cmd = (0, 0)
        return self.cmd

    def step(self):
        """Decide, then dual-check the decision before acting on it."""
        prev = self.cmd
        state_before = self.state
        want = self._decide()
        now = time.monotonic()
        if want == (0, 0):
            self.wanted, self.wanted_ticks = want, 0
            return want                              # stopping is always allowed straight away
        # A move must be wanted CONFIRM_TICKS in a row (filters one-tick flip-flops)
        self.wanted_ticks = self.wanted_ticks + 1 if want == self.wanted else 1
        self.wanted = want
        turn_dir = 1 if want == (0, SPEED) else -1 if want == (SPEED, 0) else 0
        if want != prev and self.wanted_ticks < CONFIRM_TICKS:
            self.cmd, self.state = prev, state_before
            return prev
        # Don't snap straight from turning one way to the other
        if turn_dir and self.last_turn_dir and turn_dir != self.last_turn_dir \
                and now - self.last_turn_t < REVERSE_HOLD_S:
            self.cmd = (0, 0)
            self.state = "settle"
            return self.cmd
        if turn_dir:
            self.last_turn_dir, self.last_turn_t = turn_dir, now
        return want

    def _decide(self):
        now = time.monotonic()
        if self.person_heading is None or now - self.last_data > DATA_TIMEOUT_S:
            return self.stop("no data")
        if not self.has_steps:
            return self.stop("reflash BLE33")
        if self.rssi is not None and self.rssi < LOST_RSSI:
            return self.stop("lost")

        self.gap = gap = FOLLOW_START_M + self.walked - self.driven
        if gap > MAX_GAP_M:
            return self.stop("too far")   # bad data or lost the wearer: never chase blindly
        if gap > FOLLOW_MAX_M:
            self.driving = True
        elif gap < FOLLOW_MIN_M or (self.use_rssi and self.rssi is not None and self.rssi > NEAR_RSSI):
            self.driving = False

        err = wrap(self.person_heading - self.robot_heading)
        if abs(err) > BEHIND_DEG and not self.driving:
            self.turning = False
            return self.stop("coming back")   # wearer turned to face the robot: wait for them

        # Match the wearer's heading, always (even while waiting), with a little hysteresis
        if self.turning and abs(err) < TURN_STOP_DEG:
            self.turning = False
        elif abs(err) > TURN_START_DEG:
            self.turning = True
        turn = (0, SPEED) if err > 0 else (SPEED, 0)
        side = "left" if err > 0 else "right"

        if not self.driving:
            if self.turning:
                self.state = f"face {side}"
                self.cmd = turn
                return self.cmd
            return self.stop("waiting")

        if self.turning and abs(err) > PIVOT_DEG:
            self.state = f"turn {side}"
            self.cmd = turn
        elif self.turning:
            # One-motor robot can't steer gently: mix turn ticks into straight driving,
            # more of them the further off we are
            self.turn_acc += min(0.75, abs(err) / ARC_FULL_DEG)
            if self.turn_acc >= 1:
                self.turn_acc -= 1
                self.cmd = turn
            else:
                self.cmd = (SPEED, SPEED)
            self.state = f"arc {side}"
        else:
            self.state = "forward"
            self.cmd = (SPEED, SPEED)
        return self.cmd


async def ble_task(follower):
    from bleak import BleakClient, BleakScanner

    while True:
        try:
            print("Scanning for FallDetector...")
            device = await BleakScanner.find_device_by_name(ARDUINO_NAME, timeout=10)
            if not device:
                print("FallDetector not found, retrying...")
                await asyncio.sleep(2)
                continue
            async with BleakClient(device) as client:
                print(f"Connected to FallDetector ({device.address}), assuming the wearer is "
                      f"{FOLLOW_START_M} m in front of the robot, facing the same way")
                follower.resync()
                await client.start_notify(FOLLOW_CHAR_UUID, follower.on_data)

                def on_fall(_sender, data):
                    follower.fall = data[0]
                    print({0: "BLE33: normal", 1: "BLE33: FALL DETECTED", 2: "BLE33: EMERGENCY"}.get(data[0], data[0]))

                await client.start_notify(FALL_CHAR_UUID, on_fall)
                while client.is_connected:
                    await asyncio.sleep(0.5)
                print("BLE disconnected")
        except Exception as e:
            print(f"BLE error: {e}, retrying in 3s...")
            await asyncio.sleep(3)


class Robot:
    """Serial link to the Uno that reopens itself if the USB drops (cable tug, motor brownout)."""

    def __init__(self, port):
        self.port = port
        self.ser = None
        self.next_try = 0.0
        self.rx_buf = b""

    def _open(self):
        if self.ser or time.monotonic() < self.next_try:
            return self.ser
        port = self.port
        if not os.path.exists(port):
            # Plugged into a different USB socket = different name; take any USB-serial adapter
            found = sorted(glob.glob("/dev/cu.usbserial-*") + glob.glob("/dev/cu.wchusbserial*"))
            if found:
                port = found[0]
        try:
            self.ser = serial.Serial(port, 9600, timeout=0.1)
            time.sleep(2)   # opening the port resets the Uno
            print(f"Robot connected on {port}")
        except serial.SerialException as e:
            print(f"Robot not available ({e}), retrying...")
            self.next_try = time.monotonic() + 2
        return self.ser

    def _drop(self, e):
        print(f"Robot USB lost ({e}), reconnecting...")
        try:
            self.ser.close()
        except Exception:
            pass
        self.ser = None
        self.next_try = time.monotonic() + 1

    def send(self, data):
        if not self._open():
            return
        try:
            self.ser.write(data)
            # Read whatever has arrived without waiting for a full line (readline could block 100 ms)
            if self.ser.in_waiting:
                self.rx_buf += self.ser.read(self.ser.in_waiting)
                *lines, self.rx_buf = self.rx_buf.split(b"\n")
                for line in lines:
                    line = line.decode(errors="ignore").strip()
                    if line:
                        print(f"robot: {line}")
        except (serial.SerialException, OSError) as e:
            self._drop(e)

    def drive(self, left, right):
        if MOTORS_SWAPPED:
            left, right = right, left
        self.send(f"<{left},{right}>".encode())

    def close(self):
        if self.ser:
            try:
                self.ser.write(b"<0,0>s")
                self.ser.close()
            except Exception:
                pass


def mode_name(seeker):
    return seeker.state if seeker and seeker.active else "follow"


def toggle_seek(follower, seeker):
    """Dashboard button: follow -> go to nearest person -> return to start -> follow."""
    if not seeker:
        return
    if not seeker.active:
        follower.stop("paused")
        seeker.start(follower.robot_heading)
        print("Button: going to nearest person")
    elif seeker.state == "returning":
        seeker.cancel()
        follower.reset_distance()
        print("Button: return cancelled, back to follow mode")
    else:
        seeker.go_home()
        print("Button: returning to start")


async def control_task(follower, robot, seeker, phone=None):
    period = 1 / SEND_HZ
    last = time.monotonic()
    last_print = 0.0
    cmd = (0, 0)
    last_moving = 0.0
    vision = seeker.vision if seeker else None
    yaw_prev = bad_prev = None
    last_fall = 0
    worst_dt = 0.0
    phone_prev = None
    stall_t, stall_warned = 0.0, False
    while True:
        await asyncio.sleep(period)
        now = time.monotonic()
        dt = now - last
        last = now
        worst_dt = max(worst_dt, dt)
        # Update odometry with what the robot did since the last tick (nothing, if it isn't connected)
        if not robot.ser:
            cmd = (0, 0)
        if cmd != (0, 0):
            last_moving = now
        # What the robot should have turned this tick, from the command and the calibrated turn rate
        commanded = TURN_RATE_DPS if cmd == (0, SPEED) else -TURN_RATE_DPS if cmd == (SPEED, 0) else 0.0
        phone_now = None
        if phone:
            phone.learn_sign(commanded, dt)
            phone_now = phone.reading()
        if phone_now is not None and phone_prev is not None:
            # Dual check: use the turn the iPhone actually measured, not the one we assumed
            measured = wrap(phone_now - phone_prev)
            follower.track(cmd, dt, dheading=measured)
            # Commanded a turn for a while but the robot isn't rotating = stuck / wheel slipping
            stall_t = stall_t + dt if commanded and abs(measured) < abs(commanded * dt) * 0.2 else 0.0
            if stall_t > 1.0 and not stall_warned:
                print("Robot told to turn but the iPhone says it isn't (stuck or slipping?)")
                stall_warned = True
            elif stall_t == 0.0:
                stall_warned = False
        elif vision and vision.deg_per_px:
            # Heading from how far the camera view slid: catches slip, drift and coasting
            yaw, bad = vision.yaw_reading()
            if yaw_prev is None or bad != bad_prev:
                follower.track(cmd, dt)   # couldn't read the view this tick, use timing
            elif now - last_moving < 0.6:   # ignore people walking past a parked robot
                follower.track(cmd, dt, dheading=(yaw - yaw_prev) * vision.deg_per_px)
            yaw_prev, bad_prev = yaw, bad
        else:
            follower.track(cmd, dt)
        phone_prev = phone_now
        if seeker:
            seeker.update_pose(cmd, follower.robot_heading, dt)

        # Wearer fell: fetch the nearest other person, then lead them back here
        if seeker and follower.fall != last_fall:
            if follower.fall and not last_fall:
                follower.stop("paused")
                seeker.start(follower.robot_heading, emergency=True)
                print("Fall: going to get the nearest person")
            # 1 -> 0 is a double-tap cancel; 2 -> 0 is just the BLE33 resetting after the alert
            elif not follower.fall and last_fall == 1 and seeker.emergency and seeker.state != "returning":
                seeker.cancel()
                follower.reset_distance()
                print("Fall cancelled on the BLE33, back to follow mode")
            last_fall = follower.fall

        if seeker and seeker.active:
            cmd = seeker.step(follower.robot_heading, now)
            if cmd is None:
                print("Back at the start, follow mode")
                follower.reset_distance()
                cmd = (0, 0)
        else:
            cmd = follower.step()
        robot.drive(*cmd)   # sent every tick; the robot stops if frames stop
        if seeker and seeker.arm_cmd:
            robot.send(seeker.arm_cmd)   # 'o' arms up / 'p' arms down
            seeker.arm_cmd = None

        if seeker:
            seeker.vision.overlay = f"{mode_name(seeker)}  |  {follower.state}"
        if now - last_print > 1:
            last_print = now
            ph = str(round(follower.person_heading)) if follower.person_heading is not None else "--"
            rssi = f"{follower.rssi:.0f}dBm" if follower.rssi is not None else "--"
            state = mode_name(seeker) if seeker and seeker.active else follower.state
            print(f"[{state:>11}] behind {follower.gap:4.1f}m  steps {follower.steps if follower.steps is not None else '--'}  "
                  f"wearer {ph:>5}  robot {round(follower.robot_heading):>5}  rssi {rssi}  motion {follower.motion_smooth:.0f}mg  "
                  f"loop {worst_dt * 1000:.0f}ms  ble {follower.packets}/s gap {follower.worst_gap * 1000:.0f}ms  "
                  f"heading {'iphone' if phone_now is not None else 'iphone: learning' if phone and phone.fresh else 'timing'}")
            worst_dt = 0.0
            follower.packets, follower.worst_gap = 0, 0.0


def start_http(follower, seeker, port, phone=None):
    """Tiny API for frontend/index.html: GET /status, POST /seek (toggle), GET /video (robot camera)."""
    import json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def _head(self, code, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

        def _json(self, obj):
            self._head(200, "application/json")
            self.wfile.write(json.dumps(obj).encode())

        def _status(self):
            t = seeker.vision.latest(1.0) if seeker else None
            return {
                "mode": mode_name(seeker),
                "follow_state": follower.state,
                "camera": bool(seeker and seeker.vision.ok),
                "emergency": bool(seeker and seeker.emergency),
                "people": seeker.vision.people if seeker else 0,
                "target": {k: round(t[k], 2) for k in ("cx", "area", "bottom")} if t else None,
            }

        def do_GET(self):
            if self.path.startswith("/status"):
                self._json(self._status())
            elif self.path.startswith("/video") and seeker:
                self._head(200, "multipart/x-mixed-replace; boundary=frame")
                try:
                    while True:
                        jpg = seeker.vision.jpeg
                        if jpg:
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
                        time.sleep(0.1)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            else:
                self._head(404, "text/plain")

        def do_POST(self):
            if self.path.startswith("/phone") and phone:
                n = int(self.headers.get("Content-Length", 0))
                try:
                    phone.feed(json.loads(self.rfile.read(n)))
                except ValueError:
                    pass
                self._json({"ok": True})
            elif self.path.startswith("/seek"):
                toggle_seek(follower, seeker)
                self._json(self._status())
            else:
                self._head(404, "text/plain")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Robot API on http://localhost:{port}")


async def spin_test(robot, seconds):
    robot.send(b"<0,0>")   # opens the port (resets the Uno)
    print(f"Spinning on the left motor for {seconds}s...")
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        robot.drive(SPEED, 0)
        await asyncio.sleep(1 / SEND_HZ)
    robot.send(b"<0,0>")
    print(f"Done. TURN_RATE_DPS = degrees turned / {seconds}")


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", required=True, help="robot serial port, e.g. /dev/cu.usbmodem1101 or COM3")
    parser.add_argument("--laptop-on-robot", action="store_true",
                        help="this machine rides on the robot, so signal strength = distance to the wearer")
    parser.add_argument("--spin", type=float, metavar="SECONDS",
                        help="calibrate: spin on the left motor for SECONDS, then stop. "
                             "Measure the angle turned and set TURN_RATE_DPS = degrees / SECONDS")
    parser.add_argument("--calibrate-turn", action="store_true",
                        help="measure the turn rate with the camera (spins one full turn) and save it")
    parser.add_argument("--drive-test", type=float, metavar="SECONDS",
                        help="drive straight for SECONDS; measure the distance and save it with --set-speed")
    parser.add_argument("--set-speed", type=float, metavar="M_PER_S",
                        help="save the robot's measured forward speed (metres / drive-test seconds)")
    parser.add_argument("--camera", type=int, default=0,
                        help="OpenCV index of the robot's chest camera (default 0 = iPhone Continuity Camera here)")
    parser.add_argument("--no-camera", action="store_true", help="follow mode only, no go-to-person button")
    parser.add_argument("--http-port", type=int, default=5002, help="port for the dashboard API")
    args = parser.parse_args()

    global TURN_RATE_DPS, ROBOT_SPEED_MPS
    from seeker import load_speed, save_calibration
    if args.set_speed:
        save_calibration(speed_mps=args.set_speed)
        print(f"Saved robot speed {args.set_speed} m/s")
        return
    robot = Robot(args.port)
    if args.drive_test:
        try:
            robot.drive(0, 0)
            print(f"Driving straight for {args.drive_test}s...")
            end = time.monotonic() + args.drive_test
            while time.monotonic() < end:
                robot.drive(SPEED, SPEED)
                await asyncio.sleep(1 / SEND_HZ)
            robot.drive(0, 0)
            print(f"Measure the distance in metres, then: --set-speed <metres / {args.drive_test}>")
        finally:
            robot.close()
        return
    if args.calibrate_turn:
        from seeker import Vision, calibrate_turn
        vision = Vision(args.camera)
        while not vision.small:
            await asyncio.sleep(0.1)
        robot.drive(0, 0)
        while not robot.ser:
            print("Waiting for the robot's USB...")
            await asyncio.sleep(2)
            robot.drive(0, 0)
        try:
            await asyncio.to_thread(calibrate_turn, vision, robot.drive, SPEED)
        finally:
            robot.close()
        return
    if args.spin:
        try:
            await spin_test(robot, args.spin)
        finally:
            robot.close()
        return

    from seeker import load_calibration
    TURN_RATE_DPS, deg_per_px = load_calibration(TURN_RATE_DPS)
    ROBOT_SPEED_MPS = load_speed(ROBOT_SPEED_MPS)
    print(f"Turn rate: {TURN_RATE_DPS:.1f} deg/s, speed {ROBOT_SPEED_MPS:.2f} m/s")
    follower = Follower(use_rssi=args.laptop_on_robot)
    print("Signal strength: " + ("used for distance" if args.laptop_on_robot
                                 else "ignored (pass --laptop-on-robot if this machine rides on the robot)"))
    seeker = None
    if not args.no_camera:
        from seeker import Seeker, Vision
        seeker = Seeker(Vision(args.camera, deg_per_px), SPEED, TURN_RATE_DPS)
        print("Heading: " + ("camera (view slide) + timing fallback" if deg_per_px
                             else "timing only (run --calibrate-turn to enable camera heading)"))
    from phone_imu import PhoneIMU, UDP_PORT
    phone = PhoneIMU()
    print(f"iPhone heading: ZIG SIM -> UDP {UDP_PORT}, or Sensor Logger -> http://<this mac>:{args.http_port}/phone")
    start_http(follower, seeker, args.http_port, phone)
    try:
        await asyncio.gather(ble_task(follower), control_task(follower, robot, seeker, phone))
    finally:
        robot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")
