"""Go-to-nearest-person mode for follow_bridge.py.

The camera rides low on the robot's chest, so it mostly sees feet/legs. YOLO still
tags those as "person"; the box gets bigger (and reaches the bottom of the frame)
as the robot closes in, which is what "arrived" is based on.

The robot can't reverse, so "return" goes the direct way: one turn to face the
start point, one straight drive, one turn back to the original heading. Position is
dead-reckoned from the motor commands, so it is only as good as the turn rate:
run follow_bridge.py --calibrate-turn once to measure it with the camera.
"""
import json
import math
import os
import threading
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TURN_RATE_FILE = os.path.join(HERE, "turn_rate.json")

# --- Camera ---
CAMERA_FOV_DEG = 60.0     # horizontal field of view of the chest camera (rough is fine)
MIN_CONF = 0.25           # low on purpose: feet-only views score low
FRAME_W, FRAME_H = 640, 480
CAMERA_LAG_S = 0.25       # frames this much newer than a move show where the robot ended up
FLOW_W, FLOW_H = 160, 120 # frame size for measuring how far the view slides (= how much we turned)
FLOW_MIN_RESPONSE = 0.05  # phase-correlation confidence below this = can't tell, fall back to timing

# --- Approach ---
CENTER_TOL = 0.4          # person within the middle 40% either side = keep driving straight (no fiddly re-aims)
ARRIVE_AREA = 0.30        # box covers this share of the frame = close enough
ARRIVE_BOTTOM = 0.97      # ... or reaches the bottom of the frame and is at least half that big
FWD_STEP_S = 0.6          # forward is re-checked this often, without stopping
TURN_MAX_S = 0.8          # longest single aiming turn
MIN_AIM_DEG = 20          # aiming turns are at least this big...
AIM_GAIN = 1.2            # ...and aim slightly past centre, so one turn does the job
SETTLE_S = 0.15           # stop after a turn so the robot stops coasting
LOST_GRACE_S = 1.0        # target missing this long = start scanning
SCAN_PULSE_S = 0.3        # scan = left turns of this length...
SCAN_MAX_DEG = 360        # ...until we've looked all the way round

# --- Fall response ---
LYING_ASPECT = 1.3        # box this many times wider than tall (and not cut off at the top) = lying down
WAVE_S = 5.0              # on arrival, wave the arms this long, then lead them back to the fallen wearer
WAVE_PERIOD_S = 0.6

# --- Return ---
RETURN_TURN_TOL = 6       # deg off the way home before driving
RETURN_DRIFT_TOL = 12     # deg the robot may drift while driving before it stops to correct
RETURN_CHUNK_S = 0.5      # bearing is re-checked this often while driving home (no stop)
RETURN_DIST_TOL = 0.2     # forward-seconds


def wrap(deg):
    return (deg + 180) % 360 - 180


def save_calibration(**values):
    """Merge values into turn_rate.json."""
    try:
        with open(TURN_RATE_FILE) as f:
            cal = json.load(f)
    except (OSError, ValueError):
        cal = {}
    cal.update(values)
    with open(TURN_RATE_FILE, "w") as f:
        json.dump(cal, f)


def load_speed(default_mps):
    try:
        with open(TURN_RATE_FILE) as f:
            return float(json.load(f)["speed_mps"])
    except (OSError, ValueError, KeyError):
        return default_mps


def load_calibration(default_rate):
    """(turn rate deg/s, degrees per pixel of view slide or None) from --calibrate-turn."""
    try:
        with open(TURN_RATE_FILE) as f:
            cal = json.load(f)
        return float(cal["turn_rate_dps"]), cal.get("deg_per_px")
    except (OSError, ValueError, KeyError):
        return default_rate, None


class Vision:
    """Robot camera. A fast thread reads frames and measures how far the view slides sideways
    (= how much the robot turned); a second thread runs YOLO on the newest frame."""

    def __init__(self, camera_index, deg_per_px=None):
        from ultralytics import YOLO
        self.model = YOLO(os.path.join(HERE, "yolov8n.pt"))
        self.camera_index = camera_index
        self.deg_per_px = deg_per_px  # from --calibrate-turn; None = no visual heading
        self.lock = threading.Lock()
        self.target = None        # dict(cx=-1..1, area=0..1, bottom=0..1, conf, t)
        self.people = 0
        self.jpeg = None
        self.frame = None         # (time, newest BGR frame)
        self.small = None         # (time, tiny grey frame) for turn calibration
        self.yaw_px = 0.0         # total sideways slide of the view, + = view moved right = robot turned left
        self.bad_flow = 0         # frame pairs where the slide couldn't be measured
        self.overlay = ""         # status text drawn on the feed
        self.ok = False
        self.detect = True        # False = skip YOLO (calibration wants the CPU)
        self.exclude_lying = False  # True = never pick someone lying down (the fallen wearer)
        threading.Thread(target=self._capture, daemon=True).start()
        threading.Thread(target=self._detect, daemon=True).start()

    def _capture(self):
        cap = cv2.VideoCapture(self.camera_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
        if not cap.isOpened():
            print(f"Camera {self.camera_index} failed to open (try --camera 1)")
            return
        print(f"Camera {self.camera_index} running")
        self.ok = True
        prev = None
        window = None
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            now = time.monotonic()
            grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            flow = cv2.resize(grey, (FLOW_W, FLOW_H)).astype(np.float32)
            if window is None:
                window = cv2.createHanningWindow((FLOW_W, FLOW_H), cv2.CV_32F)
            dx, good = 0.0, False
            if prev is not None:
                (dx, _dy), response = cv2.phaseCorrelate(prev, flow, window)
                good = response >= FLOW_MIN_RESPONSE and abs(dx) < FLOW_W / 3
            prev = flow
            with self.lock:
                self.frame = (now, frame)
                self.small = (now, cv2.resize(grey, (64, 48)).astype(np.float32))
                if good:
                    self.yaw_px += dx
                elif prev is not None:
                    self.bad_flow += 1

    def _detect(self):
        last = 0.0
        while True:
            with self.lock:
                f = self.frame
            if not self.detect or not f or f[0] == last:
                time.sleep(0.01)
                continue
            last, frame = f[0], f[1].copy()
            h, w = frame.shape[:2]
            results = self.model(frame, classes=[0], conf=MIN_CONF, verbose=False)
            best, best_score, people = None, -1, 0
            for r in results:
                for box in r.boxes:
                    people += 1
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    area = (x2 - x1) * (y2 - y1) / (w * h)
                    # Wide box that isn't cut off at the top = lying down. A standing person seen
                    # from this low camera is cut off at the top (only legs/feet in view).
                    lying = (x2 - x1) > LYING_ASPECT * (y2 - y1) and y1 > 0.02 * h
                    colour = (0, 200, 255) if lying else (0, 200, 0)
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), colour, 2)
                    if lying:
                        cv2.putText(frame, "lying", (int(x1), int(y1) - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 2)
                        if self.exclude_lying:
                            continue
                    # Nearest = biggest box, nudged toward whoever is already in front of us
                    cx = ((x1 + x2) / 2 - w / 2) / (w / 2)
                    score = area * (1 - 0.3 * abs(cx))
                    if score > best_score:
                        best_score = score
                        best = dict(cx=cx, area=area, bottom=y2 / h, conf=float(box.conf[0]),
                                    box=(int(x1), int(y1), int(x2), int(y2)))
            if best:
                x1, y1, x2, y2 = best["box"]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                best["t"] = last   # time the frame was taken, not when YOLO finished
            cv2.line(frame, (w // 2, 0), (w // 2, h), (255, 255, 255), 1)
            cv2.rectangle(frame, (0, 0), (w, 30), (0, 0, 0), -1)
            cv2.putText(frame, self.overlay, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            with self.lock:
                if best:
                    self.target = best
                self.people = people
                self.jpeg = jpg.tobytes()

    def yaw_reading(self):
        """(total slide in px, count of unmeasurable frame pairs)."""
        with self.lock:
            return self.yaw_px, self.bad_flow

    def latest(self, max_age):
        with self.lock:
            t = self.target
        if t and time.monotonic() - t["t"] <= max_age:
            return t
        return None


class Seeker:
    """seek -> (scan) -> arrived -> return -> off. step() returns a motor command, or None when home."""

    def __init__(self, vision, speed, turn_rate_dps):
        self.vision = vision
        self.speed = speed
        self.turn_rate = turn_rate_dps
        self.state = "off"
        self.action = None        # (cmd, until)
        self.fresh_after = 0.0    # ignore detections older than this (taken before the last turn)
        self.x = self.y = 0.0     # forward-seconds from the start point
        self.origin_heading = 0.0
        self.scanned = 0.0
        self.last_seen = 0.0
        self.driving_home = False
        self.emergency = False    # started by a fall rather than the button
        self.confirmed = False    # True once the frontend confirms "lead this person back"
        self.arrived_at = 0.0
        self.arm_cmd = None       # b"o"/b"p" for the control loop to send

    # --- control ---
    def start(self, heading, emergency=False):
        self.emergency = emergency
        self.confirmed = False
        self.vision.exclude_lying = emergency
        self.x = self.y = 0.0
        self.origin_heading = heading
        self.scanned = 0.0
        self.last_seen = time.monotonic()
        self.action = None
        self.state = "seeking"

    def go_home(self):
        self.action = None
        self.driving_home = False
        self.state = "returning"

    def cancel(self):
        self.action = None
        self.state = "off"
        self.emergency = False
        self.confirmed = False
        self.vision.exclude_lying = False

    def confirm(self):
        if self.state == "arrived" and not self.confirmed:
            self.confirmed = True
            self.arrived_at = time.monotonic()

    def reject(self):
        if self.state == "arrived" and not self.confirmed:
            self.last_seen = time.monotonic()
            self.scanned = 0.0
            self.state = "seeking"

    @property
    def active(self):
        return self.state != "off"

    # --- odometry, called every tick with the command that was actually sent ---
    def update_pose(self, cmd, heading, dt):
        # Both wheels = 1 forward-second per second; one wheel = pivot, the middle moves half as fast
        l, r = cmd
        v = 1.0 if (l and r) else 0.5 if (l or r) else 0.0
        self.x += v * math.cos(math.radians(heading)) * dt
        self.y += v * math.sin(math.radians(heading)) * dt

    # --- behaviour ---
    def _do(self, cmd, seconds, now):
        self.action = (cmd, now + seconds)
        return cmd

    def _turn(self, deg, now, max_s=None):
        """One turn pulse of deg (+ = left), followed by a short settle."""
        s = abs(deg) / self.turn_rate
        if max_s:
            s = min(s, max_s)
        cmd = (0, self.speed) if deg > 0 else (self.speed, 0)
        self.fresh_after = now + s + SETTLE_S + CAMERA_LAG_S
        return self._do(cmd, max(0.05, s), now)

    def step(self, heading, now):
        if self.action:
            cmd, until = self.action
            if now < until:
                return cmd
            self.action = None
            if cmd != (0, 0) and cmd != (self.speed, self.speed):
                return self._do((0, 0), SETTLE_S, now)   # let a turn coast out before measuring again

        if self.state in ("seeking", "scanning"):
            return self._seek(now)
        if self.state == "arrived":
            if self.emergency and not self.confirmed:
                return (0, 0)
            if self.emergency:
                return self._wave(now)
            return (0, 0)
        if self.state == "returning":
            return self._return(heading, now)
        return (0, 0)

    def _seek(self, now):
        t = self.vision.latest(max_age=0.6)
        if t and t["t"] < self.fresh_after:
            return (0, 0)   # still waiting for a frame from after the last turn
        if t:
            self.last_seen = now
            self.scanned = 0.0
            self.state = "seeking"
            if t["area"] >= ARRIVE_AREA or (t["bottom"] >= ARRIVE_BOTTOM and t["area"] >= ARRIVE_AREA / 2):
                self.state = "arrived"
                self.arrived_at = now
                return (0, 0)
            if abs(t["cx"]) > CENTER_TOL:
                # + cx = person right of centre = turn right (negative deg)
                deg = max(MIN_AIM_DEG, abs(t["cx"]) * CAMERA_FOV_DEG / 2 * AIM_GAIN)
                return self._turn(-deg if t["cx"] > 0 else deg, now, TURN_MAX_S)
            return self._do((self.speed, self.speed), FWD_STEP_S, now)

        if now - self.last_seen < LOST_GRACE_S:
            return (0, 0)
        if self.scanned >= SCAN_MAX_DEG:
            print("No person found, going back")
            self.go_home()
            return (0, 0)
        self.state = "scanning"
        self.scanned += SCAN_PULSE_S * self.turn_rate
        return self._turn(SCAN_PULSE_S * self.turn_rate, now)

    def _wave(self, now):
        """Flag the person down, then lead them back to the fallen wearer."""
        t = now - self.arrived_at
        if t >= WAVE_S:
            self.arm_cmd = b"p"
            self.go_home()
            return (0, 0)
        phase = int(t / WAVE_PERIOD_S) % 2
        if phase != getattr(self, "_wave_phase", None):
            self._wave_phase = phase
            self.arm_cmd = b"o" if phase == 0 else b"p"
        return (0, 0)

    def _return(self, heading, now):
        # Straight line home: face the start, drive it in one go, then face the original way
        dist = math.hypot(self.x, self.y)
        if dist > RETURN_DIST_TOL:
            bearing = math.degrees(math.atan2(-self.y, -self.x))
            err = wrap(bearing - heading)
            tol = RETURN_DRIFT_TOL if self.driving_home else RETURN_TURN_TOL
            if abs(err) > tol:
                self.driving_home = False
                return self._turn(err, now)
            self.driving_home = True
            return self._do((self.speed, self.speed), min(dist, RETURN_CHUNK_S), now)
        self.driving_home = False
        err = wrap(self.origin_heading - heading)
        if abs(err) > RETURN_TURN_TOL:
            return self._turn(err, now)
        self.cancel()
        return None


def calibrate_turn(vision, drive, speed, max_s=30.0):
    """Spin on one motor until the camera sees the starting view again; returns deg/s.

    drive(left, right) sends a motor command. Needs something with texture in view.
    """
    def frame_after(t0):
        while True:
            with vision.lock:
                f = vision.small
            if f and f[0] > t0:
                return f
            time.sleep(0.02)

    def similarity(a, b):
        a = a - a.mean()
        b = b - b.mean()
        return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-6))

    vision.detect = False
    # Wait for a steady stream of frames (the camera can stall for seconds when it starts)
    print("Waiting for the camera to settle...")
    streak, last = 0, 0.0
    last_drive = 0.0
    while streak < 20:
        if time.monotonic() - last_drive >= 0.1:
            drive(0, 0)
            last_drive = time.monotonic()
        t, _ = frame_after(last)
        streak = streak + 1 if t - last < 0.15 else 0
        last = t
    time.sleep(0.5)
    _, ref = frame_after(time.monotonic())
    yaw0, bad0 = vision.yaw_reading()
    print("Spinning; keep the area around the robot still...")
    start = time.monotonic()
    best, best_t, best_yaw, seen_away = -1.0, None, 0.0, False
    trace = []
    try:
        last_t, last_drive = start, 0.0
        while time.monotonic() - start < max_s:
            now = time.monotonic()
            if now - last_drive >= 0.1:   # 10 Hz, like the bridge; faster floods the 9600 baud link
                drive(speed, 0)
                last_drive = now
            with vision.lock:
                latest = vision.small
                yaw = vision.yaw_px
            if not latest or latest[0] <= last_t:
                time.sleep(0.02)
                continue
            t, f = latest
            last_t = t
            sim = similarity(ref, f)
            trace.append((t - start, sim))
            if len(trace) % 5 == 0:
                print(f"  {t - start:5.1f}s  match {sim:+.2f}")
            if sim < 0.3:
                seen_away = True              # we've turned away from the start view
            if seen_away and sim > 0.6 and sim > best:
                best, best_t, best_yaw = sim, t, yaw   # coming back round to the start view
            elif best_t and sim < best - 0.15:
                break                         # passed the best match
    finally:
        drive(0, 0)
    if trace:
        print(f"Match ranged {min(v for _, v in trace):+.2f} to {max(v for _, v in trace):+.2f} over {trace[-1][0]:.1f}s")
    if not best_t:
        raise RuntimeError("never saw the starting view again; point the camera at something with detail")
    rate = 360.0 / (best_t - start)
    cal = {"turn_rate_dps": round(rate, 1), "measured": time.strftime("%Y-%m-%d %H:%M")}
    # We turned right (heading -360) while the view slid slide_px, so deg/px = -360 / slide_px
    slide_px = best_yaw - yaw0
    bad = vision.yaw_reading()[1] - bad0
    if abs(slide_px) > FLOW_W:
        cal["deg_per_px"] = round(-360.0 / slide_px, 5)
        print(f"View slid {slide_px:.0f}px for a full turn ({bad} unreadable frames) -> camera heading on")
    else:
        print(f"View slide too small to use ({slide_px:.0f}px) -> camera heading off, timing only")
    save_calibration(**cal)
    print(f"Full turn in {best_t - start:.2f}s -> turn rate {rate:.1f} deg/s (saved to {TURN_RATE_FILE})")
    return rate
