"""Follow-me logic: BLE33 heading + steps in, motor command out. No I/O here, so it's easy to
read, test and change. All the numbers live in follow_config.py.

Heading (the important part):
  Your gyro heading is smoothed (HEADING_TAU_S). When the robot is off by more than the deadband it
  makes ONE turn pulse sized to the error, then waits (SETTLE_S) while it coasts to a stop, then
  looks again. A one-wheel robot with on/off motors can't steer gently, and reacting every tick makes
  it twitch; pulse-and-settle is smooth and lands where it's aimed, at the cost of a little delay.

Distance:
  distance you've walked (steps) - distance the robot has driven = how far ahead you are.
  Drive above FOLLOW_MAX_M, stop below FOLLOW_MIN_M.

Sticker (optional, camera on the Mac): while the camera sees the sticker on your pants, steer
straight at it and judge distance from its size (calibrated during the warm-up, when you stand
FOLLOW_START_M away). The gyro heading and step distance are pulled into line with it, so losing
the sticker (e.g. round a corner) just carries on smoothly with the BLE33.
"""
import math
import struct
import time
from collections import deque

import follow_config as cfg


def wrap(deg):
    return (deg + 180) % 360 - 180


def long_enough(rates):
    """Enough still readings, spanning nearly the whole drift window, to judge drift from."""
    return len(rates) > 12 and rates[-1][0] - rates[0][0] > 0.9 * cfg.DRIFT_RELEARN_STILL_S


def median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2]


class Follower:
    def __init__(self, use_rssi=False, turn_rate_dps=cfg.TURN_RATE_DPS, speed_mps=cfg.ROBOT_SPEED_MPS,
                 left_dps=None, right_dps=None):
        self.use_rssi = use_rssi
        self.turn_rate = turn_rate_dps
        # Left and right turns run different motors, so each has its own rate
        self.rate_left = left_dps or cfg.TURN_RATE_LEFT_DPS or turn_rate_dps
        self.rate_right = right_dps or cfg.TURN_RATE_RIGHT_DPS or turn_rate_dps
        self.speed_mps = speed_mps
        # Wearer
        self.heading_zero = None
        self.raw_heading = None      # last accepted raw heading from the BLE33
        self.jump_pending = None     # a big heading jump waiting for a second packet to confirm it
        self.person_heading = None   # smoothed, in the robot's frame
        self.steps = None
        self.has_steps = False       # False = old BLE33 firmware without step counting
        self.walked = 0.0
        self.motion = 0
        self.last_step_t = 0.0
        self.drift_dps = 0.0         # learned BLE33 gyro drift (cfg.DRIFT_FIX)
        self.drift_offset = 0.0      # total drift removed so far
        self.prev_drift_raw = None
        self.warmup_until = 0.0      # robot holds still until then, learning the drift
        self.still_rates = deque()   # (time, heading rate) while you're still, for drift re-learning
        self.warm_sum = self.warm_time = 0.0   # drift measurement during the warm-up
        self.rssi_samples = deque()
        self.rssi = None
        self.fall = 0                # latest fall status from the BLE33 (0 normal, 1 fall, 2 emergency)
        self.fall_events = 0         # +1 every time a new fall is reported (so none are ever missed)
        self.cancel_events = 0       # +1 every time a fall is cancelled with the double-tap
        self.on_fall_change = None   # callback(old, new), e.g. the dashboard's fall log
        self.last_data = 0.0
        self.packets = 0             # BLE packets since the status line was last printed
        self.worst_gap = 0.0         # longest gap between them
        # Robot (dead-reckoned from the commands actually sent)
        self.rx = self.ry = 0.0
        self.robot_heading = 0.0
        self.driven = 0.0
        # Controller
        self.driving = False
        self.pulse = None            # (command, end time) of the turn pulse in progress
        self.settle_until = 0.0
        self.gap = cfg.FOLLOW_START_M
        self.sticker_ref = None      # (sticker height as share of frame, distance it was measured at)
        self.person_ref = None       # (clicked person's height, distance, selection id)
        self.source = "gyro"         # what it's steering by: sticker, person or gyro
        self.drive_started = 0.0
        self.last_turn_end = 0.0
        self.sticker_sizes = []      # sightings during the warm-up, for sticker_ref
        self.using_sticker = False
        self.cmd = (0, 0)
        self.state = "waiting for BLE33"

    # ------------------------------------------------------------------ setup
    @property
    def deadband(self):
        """Never smaller than half the smallest turn the robot can make, or it would swing back and forth."""
        return max(cfg.DEADBAND_DEG, 0.55 * cfg.MIN_TURN_S * max(self.rate_left, self.rate_right))

    def resync(self, raw_heading=None):
        """You're FOLLOW_START_M in front of the robot, facing the same way.
        Called on every (re)connect, since the BLE33's heading and step count may have restarted."""
        self.walked = self.driven = 0.0
        self.driving = False
        self.pulse = None
        self.steps = None
        self.sticker_ref, self.sticker_sizes = None, []
        if cfg.DRIFT_FIX:
            self.warmup_until = time.monotonic() + cfg.DRIFT_WARMUP_S
            self.drift_dps = self.drift_offset = 0.0
            self.warm_sum = self.warm_time = 0.0
            self.prev_drift_raw = None
        self.heading_zero = None if raw_heading is None else raw_heading - self.robot_heading
        self.person_heading = None if raw_heading is None else self.robot_heading

    def reset_distance(self):
        """The robot moved on its own (or was offline): assume it's FOLLOW_START_M behind again."""
        self.walked = self.driven = 0.0
        self.driving = False

    def report_fall(self, value):
        """BLE33 fall status changed (or a simulated one): 0 normal, 1 fall detected, 2 emergency.
        Counts events, so a new one is never missed because an earlier one left the status set.
        A rescue starts when the status reaches cfg.RESCUE_ON."""
        old = self.fall
        if value >= cfg.RESCUE_ON > old:
            self.fall_events += 1
        elif not value and old == 1:
            self.cancel_events += 1   # 1 -> 0 is the double-tap cancel; 2 -> 0 is just the alert ending
        self.fall = value
        if self.on_fall_change and value != old:
            self.on_fall_change(old, value)

    # ------------------------------------------------------------------ input
    def on_data(self, _sender, data):
        """BLE33 notification: int16 heading x10, int16 yaw rate, uint8 motion, int8 rssi, uint16 steps."""
        data = bytes(data)
        heading, _rate, motion, rssi = struct.unpack("<hhBb", data[:6])
        heading = cfg.YAW_SIGN * heading / 10
        now = time.monotonic()
        dt = now - self.last_data if self.last_data else 0.05

        # A huge jump in one packet is a glitch unless the next packet agrees
        if self.raw_heading is not None and abs(wrap(heading - self.raw_heading)) > cfg.HEADING_JUMP_DEG:
            if self.jump_pending is None or abs(wrap(heading - self.jump_pending)) > cfg.HEADING_JUMP_DEG:
                self.jump_pending = heading
                heading = self.raw_heading
            else:
                self.jump_pending = None
        else:
            self.jump_pending = None
        self.raw_heading = heading

        # Gyro drift: while you're standing still the heading shouldn't move, so any steady change is
        # drift. Learn its rate then, and take it out all the time.
        if cfg.DRIFT_FIX and self.prev_drift_raw is not None and 0 < dt < 0.5:
            change = wrap(heading - self.prev_drift_raw)
            rate = change / dt
            warming = now < self.warmup_until
            # During the warm-up you're asked to stand still, so trust it whatever the motion reads
            still = warming or (motion < cfg.STILL_MOTION_MG and now - self.last_step_t > cfg.WALKING_GRACE_S)
            # Recent rates while still (for telling constant drift from a real turn)
            if still:
                self.still_rates.append((now, rate))
            else:
                self.still_rates.clear()
            while self.still_rates and now - self.still_rates[0][0] > cfg.DRIFT_RELEARN_STILL_S:
                self.still_rates.popleft()
            target, tau = None, None
            if warming:
                # Just connected and you're standing still: drift = plain average of every reading
                if abs(rate) < cfg.MAX_DRIFT_DPS:
                    self.warm_sum += rate * dt
                    self.warm_time += dt
                    self.drift_dps = self.warm_sum / self.warm_time
            elif still and long_enough(self.still_rates):
                # Still for a while: compare the average rate in each third of the window. Drift gives
                # three equal thirds; a real turn (speeding up, then slowing down) makes one differ.
                # Averaging first keeps breathing/sway noise from hiding a steady drift.
                rs = [r for _, r in self.still_rates]
                k = len(rs) // 3
                thirds = [sum(rs[i * k:(i + 1) * k]) / k for i in range(3)]
                mean = sum(rs) / len(rs)
                if max(thirds) - min(thirds) < cfg.DRIFT_STEADY_SPREAD_DPS and abs(mean) < cfg.MAX_DRIFT_DPS:
                    target, tau = mean, cfg.DRIFT_WARMUP_TAU_S
            if target is None and not warming and still and abs(rate - self.drift_dps) < cfg.DRIFT_ACCEPT_DPS:
                # Only just still: fine-tune slowly from readings close to the known drift
                target, tau = rate, cfg.DRIFT_LEARN_TAU_S
            if target is not None:
                self.drift_dps += (1 - math.exp(-dt / tau)) * (target - self.drift_dps)
            self.drift_offset += self.drift_dps * dt
        self.prev_drift_raw = heading
        heading = wrap(heading - self.drift_offset)

        if self.heading_zero is None or now < self.warmup_until:
            self.heading_zero = heading - self.robot_heading   # "straight ahead" = where you face once warm
            self.person_heading = None
        h = wrap(heading - self.heading_zero)
        if self.person_heading is None:
            self.person_heading = h
        else:
            alpha = 1 - math.exp(-min(dt, 0.5) / cfg.HEADING_TAU_S)   # time-based, so packet rate doesn't matter
            self.person_heading = wrap(self.person_heading + alpha * wrap(h - self.person_heading))
        self.motion = motion

        if len(data) >= 8:
            self.has_steps = True
            steps = struct.unpack("<H", data[6:8])[0]
            if self.steps is not None:
                new = (steps - self.steps) & 0xFFFF
                if new > cfg.MAX_STEPS_PER_PACKET:
                    print(f"Step count jumped {self.steps} -> {steps}: BLE33 restarted, re-syncing")
                    self.resync(heading)
                else:
                    self.walked += new * cfg.STEP_LENGTH_M
                    if new:
                        self.last_step_t = now
            self.steps = steps

        if rssi < 0:
            self.rssi_samples.append((now, rssi))
        while self.rssi_samples and now - self.rssi_samples[0][0] > cfg.RSSI_WINDOW_S:
            self.rssi_samples.popleft()
        if self.rssi_samples:
            self.rssi = median([r for _, r in self.rssi_samples])
        if self.last_data:
            self.worst_gap = max(self.worst_gap, dt)
        self.packets += 1
        self.last_data = now

    def track(self, cmd, dt, dheading=None):
        """Dead-reckon the robot from the command that was actually sent.
        dheading: a measured heading change (e.g. the iPhone), otherwise worked out from the turn rate."""
        left, right = cmd
        if dheading is None:
            dheading = (-self.rate_right if left and not right else
                        self.rate_left if right and not left else 0.0) * dt
        self.robot_heading = wrap(self.robot_heading + dheading)
        v = self.speed_mps if (left and right) else self.speed_mps / 2 if (left or right) else 0.0
        a = math.radians(self.robot_heading)
        self.rx += v * math.cos(a) * dt
        self.ry += v * math.sin(a) * dt
        if left and right:
            self.driven += v * dt   # spinning on one wheel barely closes the gap, so only count driving

    # ------------------------------------------------------------------ decide
    def stop(self, state):
        self.state = state
        self.pulse = None
        self.cmd = (0, 0)
        return self.cmd

    def _use_camera(self, hit, kind, now):
        """The camera sees its target (kind "sticker" or "person"): return the heading error to steer
        by, and re-anchor the gyro heading and step distance on it. None if it can't be used yet.

        Distance comes from the target's size, so each kind needs one reference: the sticker is
        measured during the warm-up (you stand FOLLOW_START_M away); a clicked person when first seen
        after the click (taking the distance the robot believed at that moment)."""
        if kind == "sticker":
            if now < self.warmup_until:
                self.sticker_sizes.append(hit["size"])
                return None
            if self.sticker_ref is None:
                if len(self.sticker_sizes) < 3:
                    self.sticker_sizes.append(hit["size"])
                    return None
                self.sticker_ref = (median(self.sticker_sizes), cfg.FOLLOW_START_M)
                print(f"Sticker: {self.sticker_ref[0]:.3f} of the frame tall = {cfg.FOLLOW_START_M} m")
            ref_size, ref_dist = self.sticker_ref
        else:
            if now < self.warmup_until:
                return None
            if self.person_ref is None or self.person_ref[2] != hit["sel"]:
                dist = min(3.0, max(cfg.FOLLOW_MIN_M, self.gap))
                self.person_ref = (hit["size"], dist, hit["sel"])
                print(f"Following the clicked person: {hit['size']:.3f} of the frame tall = {dist:.1f} m")
            ref_size, ref_dist = self.person_ref[:2]

        err = -hit["cx"] * cfg.CAMERA_FOV_DEG / 2
        # Pull the gyro heading toward what the camera sees (gently: the camera is the better
        # direction, the gyro the smoother one)
        delta = wrap(self.person_heading - (self.robot_heading + err))
        self.heading_zero += 0.2 * delta
        self.person_heading = wrap(self.person_heading - 0.2 * delta)
        # Distance from size (twice as far = half as tall), and re-anchor the step distance on it
        dist = ref_dist * ref_size / max(hit["size"], 1e-3)
        self.walked = self.driven + dist - cfg.FOLLOW_START_M
        return err

    def step(self, sticker=None, person=None):
        """Called every tick; returns the motor command (left, right).
        sticker: the camera's latest sticker sighting (patch_tracker.py) or None.
        person: the camera's latest sighting of the person clicked on the dashboard, or None."""
        now = time.monotonic()
        if self.person_heading is None or now - self.last_data > cfg.DATA_TIMEOUT_S:
            self.driving = False
            return self.stop("no data")
        if not self.has_steps:
            return self.stop("reflash BLE33")
        if self.rssi is not None and self.rssi < cfg.LOST_RSSI:
            self.driving = False
            return self.stop("lost")

        # Camera target, best first: the sticker, then the clicked person, else the BLE33 gyro
        cam_err, self.source = None, "gyro"
        if sticker and cfg.PATCH_TRACKING:
            cam_err = self._use_camera(sticker, "sticker", now)
            self.source = "sticker" if cam_err is not None else "gyro"
        if cam_err is None and person and cfg.PERSON_TRACKING:
            cam_err = self._use_camera(person, "person", now)
            self.source = "person" if cam_err is not None else "gyro"
        self.using_sticker = cam_err is not None
        if now < self.warmup_until:
            self.driving = False
            return self.stop("learning drift")   # stand still: measuring the BLE33's gyro drift

        # Distance: should we be driving?
        lag_cap = cfg.FOLLOW_START_M + cfg.MAX_LAG_M
        if cfg.FOLLOW_START_M + self.walked - self.driven > lag_cap:
            self.walked = lag_cap - cfg.FOLLOW_START_M + self.driven   # forget distance it can't make up
        self.gap = cfg.FOLLOW_START_M + self.walked - self.driven
        walking = now - self.last_step_t < cfg.WALKING_GRACE_S
        if self.gap > cfg.MAX_GAP_M:
            self.driving = False
            return self.stop("too far")   # bad data or lost you: never chase blindly
        near = self.use_rssi and self.rssi is not None and self.rssi > cfg.NEAR_RSSI
        # With the sticker in view the distance is measured, so drive on it whether or not you're walking
        walk_gate = cfg.DRIVE_ONLY_WHILE_WALKING and not self.using_sticker
        committed = self.driving and now - self.drive_started < cfg.MIN_DRIVE_S
        if self.gap > cfg.FOLLOW_MAX_M and (walking or not walk_gate):
            if not self.driving:
                self.drive_started = now
            self.driving = True
        elif self.gap < cfg.FOLLOW_MIN_M * 0.7 or near:
            self.driving = False             # really close: stop even mid-move
        elif (self.gap < cfg.FOLLOW_MIN_M or (walk_gate and not walking)) and not committed:
            self.driving = False
            if walk_gate and not walking:
                self.walked = self.driven   # you've stopped: wherever it is now counts as the right distance

        forward = (cfg.SPEED, cfg.SPEED) if self.driving else (0, 0)

        # A turn pulse in progress always runs to its end
        if self.pulse:
            cmd, end = self.pulse
            if now < end:
                self.cmd = cmd
                return cmd
            self.pulse = None
            self.last_turn_end = now
            # After a pivot (or when parked) stop and coast before looking again; while driving, an
            # arc just carries on forward
            if not self.driving or self.state.startswith("turn"):
                self.settle_until = now + cfg.SETTLE_S
        if now < self.settle_until:
            self.state = "settle"
            self.cmd = (0, 0)
            return self.cmd

        err = cam_err if cam_err is not None else wrap(self.person_heading - self.robot_heading)
        deadband = cfg.PATCH_DEADBAND_DEG if cam_err is not None else self.deadband
        if abs(err) > cfg.BEHIND_DEG and not self.driving:
            return self.stop("coming back")   # you turned to face the robot: wait for you

        # Smoothness: no correction below the deadband (bigger while driving, so it holds a straight
        # line), and a cooldown between turns so it doesn't twitch, unless the error is big
        if self.driving:
            deadband = max(deadband, cfg.DRIVE_DEADBAND_DEG)
        cooling = now - self.last_turn_end < cfg.TURN_COOLDOWN_S and abs(err) < cfg.BIG_TURN_DEG
        if not cooling and abs(err) >= max(deadband, 0.55 * cfg.MIN_TURN_S * min(self.rate_left, self.rate_right)):
            rate = self.rate_left if err > 0 else self.rate_right
            gain = cfg.CAMERA_TURN_GAIN if cam_err is not None else cfg.TURN_GAIN
            seconds = min(cfg.MAX_TURN_S, max(cfg.MIN_TURN_S, abs(err) * gain / rate))
            cmd = (0, cfg.SPEED) if err > 0 else (cfg.SPEED, 0)
            side = "left" if err > 0 else "right"
            kind = "arc" if self.driving and abs(err) <= cfg.PIVOT_DEG else "turn"
            self.pulse = (cmd, now + seconds)
            self.state = f"{kind} {side} {abs(err):.0f}" + ("*" if cam_err is not None else "")
            self.cmd = cmd
            return cmd

        self.state = ("forward" if self.driving else "waiting") + ("*" if cam_err is not None else "")
        self.cmd = forward
        return forward
