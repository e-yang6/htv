"""Go-to-nearest-person mode for follow_bridge.py.

The camera rides low on the robot's chest, so it mostly sees feet/legs. YOLO still
tags those as "person"; the box gets bigger (and reaches the bottom of the frame)
as the robot closes in, which is what "arrived" is based on.

The robot can't reverse, so "return" goes the direct way: one turn to face the
start point, one straight drive, one turn back to the original heading. Position is
dead-reckoned from the motor commands, so it is only as good as the turn rate:
run follow_bridge.py --calibrate-turn once to measure it with the camera.
"""
import math
import os
import threading
import time

import cv2
import numpy as np

from calibration import HERE, TURN_RATE_FILE, save_calibration
from host_profile import get_host_condition, speak_emergency

# --- Camera ---
CAMERA_FOV_DEG = 60.0     # horizontal field of view of the chest camera (rough is fine)
MIN_CONF = 0.25           # low on purpose: feet-only views score low (enough to keep tracking a locked target)
PICK_CONF = 0.45          # but picking a NEW target needs a confident detection
PICK_MIN_AREA = 0.01      # and one that isn't tiny / far away / a reflection
LOCK_IOU = 0.2            # a detection overlapping the locked target this much = same person
LOCK_MAX_JUMP = 0.25      # ...or its centre moved less than this share of the frame width
LOCK_LOST_S = 1.5         # locked person unseen this long = pick someone new
FRAME_W, FRAME_H = 640, 480
CAMERA_LAG_S = 0.25       # frames this much newer than a move show where the robot ended up

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
SCAN_PULSE_S = 0.5        # scan = left turns of this length (longer = fewer short turns, so the
                          # timed heading stays closer to the truth for the trip back)...
SCAN_MAX_DEG = 360        # ...until we've looked all the way round

# --- Fall response ---
LYING_ASPECT = 1.3        # box this many times wider than tall (and not cut off at the top) = lying down
WAVE_S = 5.0              # (no-confirm path) wave this long on arrival, then lead them back. During a fall
                          # rescue it waves the whole time the dashboard asks "will you help?" instead
WAVE_PERIOD_S = 0.6
RECITE_AFTER_S = 6.0      # on reaching a bystander, say the host's condition this long after arriving
                          # (after the dashboard's "owner fell" / "willing to help" clips)

REJECT_TURN_DEG = 90      # bystander rejected: turn this far away before looking for someone else

# --- Return ---
# Going back means going back to the wearer. Timing alone gets the direction badly wrong after a
# search (lots of short turns), so as soon as the camera sees the wearer - their sticker, someone
# lying down, or the clicked person - it steers straight at them instead.
HOME_STICKER_SIZE = 0.18  # sticker this tall (share of frame) = back next to the wearer
HOME_LYING_AREA = 0.25    # someone lying down filling this much of the frame = back
HOME_PERSON_SIZE = 0.6    # clicked person this tall = back
RETURN_CAM_TOL = 0.3      # wearer within this of centre = drive straight at them
RETURN_TURN_TOL = 10      # deg off the way home before driving
# The heading is only timed from the turns, so after a search it can be well off. After turning for
# home the robot looks for the wearer (sticker / lying down / clicked) with the camera before driving:
# it faces the timed way home plus each of these offsets, looking LOOK_S at each, and homes in on the
# wearer as soon as it sees them. Not seen at all: back to the timed way home and drive.
LOOK_OFFSETS = (0, 35, -35, 70, -70, 0)
LOOK_S = 0.6
RETURN_DRIFT_TOL = 20     # deg the robot may drift while driving before it stops to correct
RETURN_CHUNK_S = 0.5      # bearing is re-checked this often while driving home (no stop)
# "Almost there" counts as home. Chasing the exact spot made it circle: every pivot moves the robot,
# so close to the start the way home swings round and it keeps turning after it.
# Distances are in forward-seconds (1 = one second of driving straight, ~ROBOT_SPEED_MPS metres).
HOME_RADIUS = 1.5         # this close to the start = home
NEAR_RADIUS = 3.0         # within this, also stop if...
NEAR_BEHIND_DEG = 90      # ...the start is behind the robot (it drove past), or
NEAR_BACKOFF = 0.5        # ...it's getting further away again
RETURN_MAX_S = 60         # give up and call it home after this long
HOME_WAVE_S = 4.0         # at home, wave the arms this long (same wave as on arrival), then follow mode


def wrap(deg):
    return (deg + 180) % 360 - 180


def box_iou(a, b):
    """Overlap of two (x1, y1, x2, y2) boxes, 0-1."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class Vision:
    """Robot camera. A fast thread reads frames and measures how far the view slides sideways
    (= how much the robot turned); a second thread runs YOLO on the newest frame."""

    def __init__(self, camera_index=None):
        """camera_index None = the iPhone (Continuity Camera), found by name."""
        from ultralytics import YOLO
        self.model = YOLO(os.path.join(HERE, "yolov8n.pt"))
        self.camera_index = camera_index
        self.lock = threading.Lock()
        self.target = None        # dict(cx=-1..1, area=0..1, bottom=0..1, conf, t)
        self.people = 0
        self.jpeg = None
        self.frame = None         # (time, newest BGR frame)
        self.small = None         # (time, tiny grey frame) for turn calibration
        self.overlay = ""         # status text drawn on the feed
        self.ok = False
        self.detect = True        # False = skip YOLO (calibration wants the CPU)
        self.reopen = False       # set True to reset the camera (POST /camera-reset)
        self.patch = None         # (time, latest sticker sighting or None), see patch_tracker.py
        # Click-to-follow: the person clicked on the dashboard, tracked frame to frame
        self.click = None         # (x, y) 0-1 in the frame, waiting to be matched to a person
        self.follow_box = None    # (x1, y1, x2, y2 as 0-1, time last seen)
        self.follow_hit = None    # (time, dict(cx, size, sel)) latest sighting
        self.follow_sel = 0       # +1 per click, so the follower knows to re-measure its distance
        self.lying_hit = None     # (time, biggest person lying down) - the fallen wearer, for going home
        self.patch_tracker = None
        import follow_config as fcfg
        if fcfg.PATCH_TRACKING:
            from patch_tracker import PatchTracker
            self.patch_tracker = PatchTracker(os.path.join(HERE, fcfg.PATCH_IMAGE))
        self.exclude_lying = False  # True = never pick someone lying down (the fallen wearer)
        self.lock_on = False      # True while seeking: stick with one person instead of re-picking every frame
        self.locked = None        # (box normalised x1, y1, x2, y2, time last seen)
        threading.Thread(target=self._capture, daemon=True).start()
        threading.Thread(target=self._detect, daemon=True).start()

    def _open(self):
        """Open the robot's camera: the given --camera index, or (by default) the iPhone's Continuity
        Camera, looked up by name each time since its number changes. Waits for the iPhone rather
        than falling back to the Mac's own camera."""
        from camera import find_camera
        waiting = False
        while True:
            index = self.camera_index if self.camera_index is not None else find_camera()
            if index is not None:
                cap = cv2.VideoCapture(index)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
                if cap.isOpened():
                    name = "iPhone camera" if self.camera_index is None else "Camera"
                    print(f"{name} {index} running")
                    return cap
                cap.release()
            if not waiting:
                print("Waiting for the iPhone Continuity Camera (phone locked, near the Mac, "
                      "same Apple ID, Wi-Fi + Bluetooth on)...")
                waiting = True
            self.ok = False
            time.sleep(3.0)

    def _capture(self):
        cap = self._open()
        self.ok = True
        fails = 0
        while True:
            if self.reopen:
                # Reset the camera (e.g. Continuity Camera dropped): close and find it again
                self.reopen = False
                cap.release()
                time.sleep(1.0)
                cap = self._open()
                self.ok = True
            ok, frame = cap.read()
            if not ok:
                fails += 1
                if fails == 40:   # ~2 s without frames: try reopening by itself
                    self.reopen, fails = True, 0
                time.sleep(0.05)
                continue
            fails = 0
            now = time.monotonic()
            grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            hit = self.patch_tracker.find(frame) if self.patch_tracker else None
            with self.lock:
                self.frame = (now, frame)
                self.small = (now, cv2.resize(grey, (64, 48)).astype(np.float32))
                self.patch = (now, hit)

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
            people, candidates, lying_people = 0, [], []
            for r in results:
                for box in r.boxes:
                    people += 1
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    area = (x2 - x1) * (y2 - y1) / (w * h)
                    # Wide box that isn't cut off at the top = lying down. A standing person seen
                    # from this low camera is cut off at the top (only legs/feet in view).
                    lying = (x2 - x1) > LYING_ASPECT * (y2 - y1) and y1 > 0.02 * h
                    colour = (0, 200, 255) if lying else (0, 200, 0)
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), colour, 2)
                    cv2.putText(frame, f"{'lying ' if lying else ''}{conf:.0%}", (int(x1), int(y1) - 6),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 2)
                    cand = dict(
                        cx=((x1 + x2) / 2 - w / 2) / (w / 2), area=area, bottom=y2 / h, conf=conf,
                        box=(int(x1), int(y1), int(x2), int(y2)),
                        norm=(x1 / w, y1 / h, x2 / w, y2 / h))
                    if lying:
                        lying_people.append(cand)
                        if self.exclude_lying:
                            continue
                    candidates.append(cand)
            self._track_followed(candidates, last)
            best = self._choose(candidates, last)
            if best:
                x1, y1, x2, y2 = best["box"]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                cv2.putText(frame, "TARGET", (x1, max(14, y1 - 22)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                best["t"] = last   # time the frame was taken, not when YOLO finished
            if self.patch_tracker and self.patch:
                self.patch_tracker.draw(frame, self.patch[1])
            if self.follow_box and self.follow_hit and self.follow_hit[0] == last:
                fx1, fy1, fx2, fy2, _ = self.follow_box
                p1, p2 = (int(fx1 * w), int(fy1 * h)), (int(fx2 * w), int(fy2 * h))
                cv2.rectangle(frame, p1, p2, (255, 255, 0), 3)
                cv2.putText(frame, "FOLLOW", (p1[0], max(14, p1[1] - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            cv2.line(frame, (w // 2, 0), (w // 2, h), (255, 255, 255), 1)
            cv2.rectangle(frame, (0, 0), (w, 30), (0, 0, 0), -1)
            cv2.putText(frame, self.overlay, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            with self.lock:
                self.target = best          # None when nobody suitable is in view (no stale targets)
                biggest = max(lying_people, key=lambda c: c["area"]) if lying_people else None
                self.lying_hit = (last, biggest) if biggest else self.lying_hit
                self.people = people
                self.jpeg = jpg.tobytes()

    def _choose(self, candidates, t):
        """Pick who to go to. Locked on: the same person as last time. Otherwise: the closest one."""
        if self.lock_on and self.locked and t - self.locked[4] < LOCK_LOST_S:
            lx1, ly1, lx2, ly2, _ = self.locked
            lcx = (lx1 + lx2) / 2

            def iou(n):
                ix = max(0.0, min(lx2, n[2]) - max(lx1, n[0]))
                iy = max(0.0, min(ly2, n[3]) - max(ly1, n[1]))
                inter = ix * iy
                union = (lx2 - lx1) * (ly2 - ly1) + (n[2] - n[0]) * (n[3] - n[1]) - inter
                return inter / union if union > 0 else 0.0

            same = [(iou(c["norm"]), c) for c in candidates
                    if iou(c["norm"]) >= LOCK_IOU or abs((c["norm"][0] + c["norm"][2]) / 2 - lcx) < LOCK_MAX_JUMP]
            if same:
                best = max(same, key=lambda x: x[0])[1]
                self.locked = (*best["norm"], t)
                return best
            return None   # locked person not visible this frame: wait for them rather than switch
        # Closest = biggest box whose feet are lowest in the frame (nearer = lower from a low camera)
        pickable = [c for c in candidates if c["conf"] >= PICK_CONF and c["area"] >= PICK_MIN_AREA]
        if self.exclude_lying:
            pickable = [c for c in pickable if not self._is_wearer(c)]   # never "rescue" the fallen wearer
        if not pickable:
            return None
        best = max(pickable, key=lambda c: c["area"] * (0.5 + c["bottom"]) * (1 - 0.2 * abs(c["cx"])))
        if self.lock_on:
            self.locked = (*best["norm"], t)
            print(f"Camera: locked onto a person ({best['conf']:.0%} sure, {best['area']:.0%} of frame)")
        return best

    def select(self, x, y):
        """Dashboard click at (x, y), 0-1 across/down the video: follow the person there.
        Clicking empty space clears the selection."""
        self.click = (x, y)

    def _track_followed(self, candidates, t):
        """Keep the clicked person locked: same matching as the go-to-person lock (overlap, or a small
        move), so it doesn't jump to someone else."""
        import follow_config as fcfg
        if self.click:
            x, y = self.click
            self.click = None
            inside = [c for c in candidates if c["norm"][0] <= x <= c["norm"][2] and c["norm"][1] <= y <= c["norm"][3]]
            if inside:
                c = min(inside, key=lambda c: (c["norm"][2] - c["norm"][0]) * (c["norm"][3] - c["norm"][1]))
                self.follow_box = (*c["norm"], t)
                self.follow_sel += 1
                print(f"Click: following the person at ({x:.2f}, {y:.2f})")
            else:
                self.follow_box = None
                print("Click: nobody there, follow selection cleared")
        if not self.follow_box:
            return
        lx1, ly1, lx2, ly2, seen = self.follow_box
        if t - seen > fcfg.PERSON_LOST_S:
            print("Followed person lost (click them again)")
            self.follow_box = None
            return

        def iou(n):
            ix = max(0.0, min(lx2, n[2]) - max(lx1, n[0]))
            iy = max(0.0, min(ly2, n[3]) - max(ly1, n[1]))
            inter = ix * iy
            union = (lx2 - lx1) * (ly2 - ly1) + (n[2] - n[0]) * (n[3] - n[1]) - inter
            return inter / union if union > 0 else 0.0

        lcx = (lx1 + lx2) / 2
        same = [(iou(c["norm"]), c) for c in candidates
                if iou(c["norm"]) >= LOCK_IOU or abs((c["norm"][0] + c["norm"][2]) / 2 - lcx) < LOCK_MAX_JUMP]
        if same:
            c = max(same, key=lambda x: x[0])[1]
            self.follow_box = (*c["norm"], t)
            with self.lock:
                self.follow_hit = (t, dict(cx=c["cx"], size=c["norm"][3] - c["norm"][1], sel=self.follow_sel))

    def followed(self, max_age):
        """Latest sighting of the clicked person if recent enough, else None."""
        with self.lock:
            f = self.follow_hit
        if self.follow_box and f and time.monotonic() - f[0] <= max_age:
            return f[1]
        return None

    def sticker(self, max_age):
        """Latest sticker sighting if recent enough, else None."""
        with self.lock:
            p = self.patch
        if p and p[1] and time.monotonic() - p[0] <= max_age:
            return p[1]
        return None

    def _is_wearer(self, c):
        """Is this detection the wearer? Their box overlaps the clicked/followed person, or contains the sticker."""
        if self.follow_box and box_iou(c["norm"], self.follow_box[:4]) > 0.2:
            return True
        p = self.patch[1] if self.patch else None
        if p and self.frame is not None:
            fh, fw = self.frame[1].shape[:2]
            sx, sy = (p["box"][0] + p["box"][2]) / 2 / fw, (p["box"][1] + p["box"][3]) / 2 / fh
            x1, y1, x2, y2 = c["norm"]
            if x1 <= sx <= x2 and y1 <= sy <= y2:
                return True
        return False

    def wearer(self, max_age):
        """Where the wearer is, for going back to them: their sticker, else someone lying down, else
        the clicked person. Returns dict(cx, size, kind) or None."""
        now = time.monotonic()
        st = self.sticker(max_age)
        if st:
            return dict(cx=st["cx"], size=st["size"], kind="sticker")
        lh = self.lying_hit
        if lh and now - lh[0] <= max_age:
            x1, y1, x2, y2 = lh[1]["norm"]
            return dict(cx=lh[1]["cx"], size=y2 - y1, area=lh[1]["area"], kind="lying")
        fp = self.followed(max_age)
        if fp:
            return dict(cx=fp["cx"], size=fp["size"], kind="person")
        return None

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
        self.return_started = self.home_at = 0.0
        self.closest = 0.0
        self.drove_home = False
        self.rate_left = self.rate_right = turn_rate_dps   # per direction; the bridge sets the measured ones
        self.emergency = False    # started by a fall rather than the button
        self.confirmed = False    # True once the frontend confirms "lead this person back"
        self.recited_condition = False   # said the host's condition to this bystander yet
        self.arrived_at = 0.0
        self.arm_cmd = None       # b"o"/b"p" for the control loop to send

    # --- control ---
    def start(self, heading, emergency=False):
        self.emergency = emergency
        self.confirmed = False
        self.recited_condition = False
        self.vision.exclude_lying = emergency
        self.vision.locked = None
        self.vision.lock_on = True
        self.x = self.y = 0.0
        self.origin_heading = heading
        self.scanned = 0.0
        self.last_seen = time.monotonic()
        self.action = None
        self.state = "seeking"

    def go_home(self):
        self.action = None
        self.driving_home = False
        self.return_started = time.monotonic()
        self.closest = math.hypot(self.x, self.y)
        self.drove_home = False   # the "drove past" checks only count once it has headed home
        self.look = list(LOOK_OFFSETS)   # camera look-round for the wearer still to do
        self.look_until = None
        self.state = "returning"

    def _arrive_home(self, why, now):
        """Close enough to the start: stop, wave, then hand back to follow mode."""
        print(f"Home ({why}): waving")
        self.action = None
        self.driving_home = False
        self.home_at = now
        self._wave_phase = None
        self.state = "home"
        return (0, 0)

    def cancel(self):
        if self.state in ("arrived", "home"):
            self.arm_cmd = b"p"   # stopped mid-wave: put the arms down
        self.action = None
        self.state = "off"
        self.emergency = False
        self.confirmed = False
        self.vision.exclude_lying = False
        self.vision.lock_on = False
        self.vision.locked = None

    @property
    def awaiting_confirm(self):
        """Reached someone during a fall rescue; waiting for them to confirm on the dashboard."""
        return self.state == "arrived" and self.emergency and not self.confirmed

    @property
    def returning(self):
        """On the way back (display state 'returning' or e.g. 'returning (sticker)')."""
        return self.state.startswith("returning")

    def confirm(self):
        """They said yes: arms down and lead them back (they've been waved at during the question)."""
        if self.state == "arrived" and not self.confirmed:
            self.confirmed = True
            self.arm_cmd = b"p"
            self._wave_phase = None
            self.go_home()

    def reject(self):
        """Bystander said no: let go of this person and turn away before looking for someone else
        (otherwise it would lock straight back onto the same person)."""
        if self.state == "arrived" and not self.confirmed:
            now = time.monotonic()
            self.last_seen = now
            self.scanned = 0.0
            self.vision.locked = None
            self.arm_cmd = b"p"   # stop waving at them
            self.recited_condition = False   # tell the next person too
            self._wave_phase = None
            self.state = "scanning"
            self._turn(REJECT_TURN_DEG, now)

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
        s = abs(deg) / (self.rate_left if deg > 0 else self.rate_right)
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
                # Asking "will you help?" on the dashboard: wave the whole time to get their attention,
                # and say what's wrong with the host once the dashboard's voice clips have played
                self._wave_arms(now - self.arrived_at, float("inf"))
                if not self.recited_condition and now - self.arrived_at >= RECITE_AFTER_S:
                    self.recited_condition = True
                    msg = (f"Emergency! Please help! My host has collapsed and has {get_host_condition()}. "
                           "Please follow me to assist them!")
                    print(f"[Seeker TTS] {msg}")
                    speak_emergency(msg)
                return (0, 0)
            if self.emergency:
                return self._wave(now)
            return (0, 0)
        if self.returning:
            return self._return(heading, now)
        if self.state == "home":
            return self._home_wave(now)
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
        if self._wave_arms(now - self.arrived_at, WAVE_S):
            self.go_home()
        return (0, 0)

    def _home_wave(self, now):
        """Back at the start: wave, then done (None = back to follow mode)."""
        if self._wave_arms(now - self.home_at, HOME_WAVE_S):
            print("Back at the start, done waving")
            self.cancel()
            return None
        return (0, 0)

    def _wave_arms(self, t, length):
        """Arms up/down every WAVE_PERIOD_S; True once `length` seconds are up (arms left down)."""
        if t >= length:
            self.arm_cmd = b"p"
            self._wave_phase = None
            return True
        phase = int(t / WAVE_PERIOD_S) % 2
        if phase != getattr(self, "_wave_phase", None):
            self._wave_phase = phase
            self.arm_cmd = b"o" if phase == 0 else b"p"
        return False

    def _return(self, heading, now):
        dist = math.hypot(self.x, self.y)
        self.closest = min(self.closest, dist)
        if now - self.return_started > RETURN_MAX_S:
            return self._arrive_home("took too long", now)

        # 1. The camera sees the wearer: go straight to them (this is what actually gets it home).
        # Only frames from after the last turn count (blurred / stale ones point the wrong way).
        age = min(0.6, now - self.fresh_after)
        if age <= 0:
            return (0, 0)
        w = self.vision.wearer(age)
        if w:
            self.look = []        # found them: no more looking round
            close = ((w["kind"] == "sticker" and w["size"] >= HOME_STICKER_SIZE) or
                     (w["kind"] == "lying" and w.get("area", 0) >= HOME_LYING_AREA) or
                     (w["kind"] == "person" and w["size"] >= HOME_PERSON_SIZE))
            if close:
                return self._arrive_home(f"next to the wearer, saw their {w['kind']}", now)
            self.state = f"returning ({w['kind']})"
            if abs(w["cx"]) > RETURN_CAM_TOL:
                return self._turn(-w["cx"] * CAMERA_FOV_DEG / 2, now, TURN_MAX_S)
            return self._do((self.speed, self.speed), RETURN_CHUNK_S, now)

        # 2. Not in view: head for where timing says the start is, and stop once it's nearly there
        self.state = "returning"
        if dist <= HOME_RADIUS:
            return self._arrive_home(f"{dist:.1f} from the start", now)
        bearing = math.degrees(math.atan2(-self.y, -self.x))
        # 2a. Look round for the wearer around the timed way home before driving there
        if self.look:
            self.state = "returning (looking)"
            look_err = wrap(bearing + self.look[0] - heading)
            if self.look_until is None:
                if abs(look_err) > RETURN_TURN_TOL:
                    return self._turn(look_err, now)
                self.look_until = now + LOOK_S
            if now < self.look_until:
                return (0, 0)
            self.look.pop(0)
            self.look_until = None
            if self.look:
                return (0, 0)
            print("Didn't see the wearer, going by timing")
            self.state = "returning"
        err = wrap(bearing - heading)
        if dist <= NEAR_RADIUS and self.drove_home:
            if abs(err) > NEAR_BEHIND_DEG:
                return self._arrive_home("drove past the start", now)
            if dist > self.closest + NEAR_BACKOFF:
                return self._arrive_home("getting further away", now)
        tol = RETURN_DRIFT_TOL if self.driving_home else RETURN_TURN_TOL
        if abs(err) > tol:
            self.driving_home = False
            return self._turn(err, now)
        self.driving_home = self.drove_home = True
        return self._do((self.speed, self.speed), min(dist, RETURN_CHUNK_S), now)


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
    print("Spinning; keep the area around the robot still...")
    start = time.monotonic()
    best, best_t, seen_away = -1.0, None, False
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
                best, best_t = sim, t         # coming back round to the start view
            elif best_t and sim < best - 0.15:
                break                         # passed the best match
    finally:
        drive(0, 0)
    if trace:
        print(f"Match ranged {min(v for _, v in trace):+.2f} to {max(v for _, v in trace):+.2f} over {trace[-1][0]:.1f}s")
    if not best_t:
        raise RuntimeError("never saw the starting view again; point the camera at something with detail")
    rate = 360.0 / (best_t - start)
    save_calibration(turn_rate_dps=round(rate, 1), measured=time.strftime("%Y-%m-%d %H:%M"))
    print(f"Full turn in {best_t - start:.2f}s -> turn rate {rate:.1f} deg/s (saved to {TURN_RATE_FILE})")
    return rate
