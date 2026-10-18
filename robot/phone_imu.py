"""Robot heading from the iPhone riding on the robot (its gyro), for follow_bridge.py.

Without this the bridge only *assumes* how far the robot turned (time x TURN_RATE_DPS),
so slips, coasting and battery sag go unnoticed. With it, every turn is checked against
what the robot really did.

Two iPhone apps work:
  - Sensor Logger: HTTP push to http://<mac>:5002/phone with Gyroscope + Gravity on.
                   Streams in the background (shares the phone with Continuity Camera) but sends
                   batches, so its readings arrive up to ~1 s late.
  - ZIG SIM:       UDP JSON to <mac ip>:50000 with Gyro + Gravity on (IPv4 only).

Late batches are fine: the robot keeps steering in real time from timing, and every batch
corrects that estimate after the fact (HeadingFusion). Heading = gyro integrated around the
gravity axis, so the phone can be mounted any way up; which way is "left" is learned from
the robot's first turns.
"""
import json
import math
import socket
import threading
import time
from collections import deque

UDP_PORT = 50000
STALE_S = 3.0            # no phone data for this long = stop using it
SIGN_LEARN_DEG = 30      # degrees of commanded turning needed to learn which way is left
MOVING_GRACE_S = 0.6     # robot counts as moving this long after a command (it coasts)
SCALE_SMOOTH = 0.2       # how fast the learned turn-rate scale follows each phone batch
CORRECTION_RATE = 0.15   # share of a new phone correction applied per tick (~0.3 s), so batches don't
                         # make the heading jump and the robot lurch after it


class PhoneIMU:
    """Receives the phone's gyro + gravity and turns them into (time, yaw) samples."""

    def __init__(self, udp_port=UDP_PORT):
        self.lock = threading.Lock()
        self.gravity = None
        self.yaw = 0.0           # raw integrated yaw, degrees, phone's own sign
        self.last_t = None       # phone timestamp of the last gyro sample (s)
        self.clock_offset = None # monotonic - phone time (smallest seen = least network delay)
        self.last_rx = 0.0
        self.new = deque()       # (monotonic time of sample, raw yaw) not yet consumed
        self.source = None
        self.calibrated_seen = False
        self._seen_raw = False
        threading.Thread(target=self._udp, args=(udp_port,), daemon=True).start()

    def _udp(self, port):
        # IPv4 and IPv6: an iPhone hotspot reaches the Mac over IPv6 only
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        try:
            sock.bind(("::", port))
        except OSError as e:
            print(f"Phone IMU: can't listen on UDP {port} ({e})")
            return
        while True:
            data, _ = sock.recvfrom(65536)
            self.raw(data, "UDP")
            try:
                self.feed(json.loads(data.decode(errors="ignore")))
            except ValueError:
                pass   # OSC or junk; only JSON is supported

    def raw(self, data, via):
        """Log the first raw packet, so a format mismatch is easy to spot."""
        if not self._seen_raw:
            self._seen_raw = True
            print(f"Phone IMU: first packet via {via} ({len(data)} bytes): {data[:200]!r}")

    def feed(self, msg):
        """Accepts a ZIG SIM JSON packet or a Sensor Logger HTTP push body."""
        rx = time.monotonic()
        if isinstance(msg, dict) and "sensordata" in msg:            # ZIG SIM: no timestamps, one sample
            sd = msg["sensordata"]
            if sd.get("gravity"):
                g = sd["gravity"]
                self.gravity = (g["x"], g["y"], g["z"])
            if sd.get("gyro"):
                w = sd["gyro"]
                self._gyro(w["x"], w["y"], w["z"], rx, rx, "ZIG SIM")
        elif isinstance(msg, dict) and "payload" in msg:             # Sensor Logger: a batch
            items = msg["payload"]
            if any(i.get("name") == "gyroscope" for i in items):
                self.calibrated_seen = True
            times = [i["time"] / 1e9 for i in items if isinstance(i.get("time"), (int, float))]
            if times:
                off = rx - max(times)
                self.clock_offset = off if self.clock_offset is None else min(self.clock_offset, off)
            for item in sorted(items, key=lambda i: i.get("time", 0)):
                v, name = item.get("values", {}), item.get("name", "")
                t = item.get("time")
                t = t / 1e9 if isinstance(t, (int, float)) else None
                if name == "gravity":
                    self.gravity = (v["x"], v["y"], v["z"])
                elif name == "gyroscope" or (name == "gyroscopeuncalibrated" and not self.calibrated_seen):
                    if t is not None and self.clock_offset is not None:
                        self._gyro(v["x"], v["y"], v["z"], t, t + self.clock_offset, "Sensor Logger")

    def _gyro(self, x, y, z, t, mono, source):
        g = self.gravity
        if not g:
            return
        n = math.sqrt(g[0] ** 2 + g[1] ** 2 + g[2] ** 2)
        if n < 1e-6:
            return
        rate = math.degrees((x * g[0] + y * g[1] + z * g[2]) / n)   # rad/s around vertical -> deg/s
        dt = t - self.last_t if self.last_t is not None else 0.0
        if not 0 < dt < 0.2:
            dt = 0.0                     # first sample or a gap: don't integrate across it
        with self.lock:
            self.yaw += rate * dt
            self.last_t = t
            self.last_rx = time.monotonic()
            self.new.append((mono, self.yaw))
        if self.source is None:
            print(f"Phone IMU: receiving from {source}")
        self.source = source

    @property
    def streaming(self):
        return time.monotonic() - self.last_rx < STALE_S

    def take(self):
        with self.lock:
            out = list(self.new)
            self.new.clear()
        return out


class HeadingFusion:
    """Real-time heading from timing, corrected by the phone's (possibly late) measurements.

    Each tick: assumed heading += commanded turn. Each phone sample (taken at time ts): compare how
    much the phone says the robot turned with how much timing assumed it turned, up to ts, and keep
    the difference as a correction. Phone readings while the robot is parked are ignored (gyro drift,
    people bumping it). Heading = start + assumed + correction.
    """

    def __init__(self, phone, start_heading):
        self.phone = phone
        self.start = start_heading
        self.assumed = 0.0                  # commanded turning since start, deg (+ = left)
        self.history = deque(maxlen=400)    # (mono, assumed, moving) for the last ~20 s
        self.last_moving = -1e9
        self.measured = 0.0                 # phone turning while moving, deg (phone's sign)
        self.prev_raw = None
        self.prev_assumed_s = None
        self.corr = 0.0                     # sign learning: phone turn x assumed turn
        self.learn_abs = 0.0
        self.learn_meas = 0.0
        self.sign = None
        self.offset = 0.0                   # measured - assumed, at the latest phone sample
        self.applied = 0.0                  # the part of offset applied so far (eased in)
        self.scale = 1.0                    # real turn rate / calibrated turn rate, learned from the phone
        self._batch_dp = self._batch_da = 0.0
        self.stall = 0.0                    # assumed turning the phone didn't see (stall check)
        self.warned = False

    def _at(self, ts):
        """(assumed, moving) at monotonic time ts, from history."""
        best = None
        for t, a, m in reversed(self.history):
            best = (a, m)
            if t <= ts:
                break
        return best if best else (self.assumed, False)

    def step(self, now, commanded_dps, moving_cmd, dt):
        """commanded_dps: turn we commanded (+ = left); moving_cmd: any motor on. Returns heading (deg)."""
        self.assumed += commanded_dps * dt
        if moving_cmd:
            self.last_moving = now
        self.history.append((now, self.assumed, now - self.last_moving < MOVING_GRACE_S))

        for ts, raw in self.phone.take():
            assumed_s, moving = self._at(ts)
            if self.prev_raw is not None:
                dp = raw - self.prev_raw
                da = assumed_s - self.prev_assumed_s
                if moving:
                    self.measured += dp
                    if self.sign is None:
                        self.corr += dp * da
                        self.learn_abs += abs(da)
                        self.learn_meas += abs(dp)
                        # Only learn from real turning: a robot that isn't moving gives phone jitter, not a sign
                        if self.learn_abs >= SIGN_LEARN_DEG and self.learn_meas < 0.3 * self.learn_abs:
                            self.corr = self.learn_abs = self.learn_meas = 0.0
                        elif self.learn_abs >= SIGN_LEARN_DEG and abs(self.corr) > 1:
                            self.sign = 1 if self.corr > 0 else -1
                            print(f"Phone IMU: heading direction learned (sign {self.sign:+d})")
                    if self.sign is not None and da:
                        self._batch_dp += self.sign * dp * (1 if da > 0 else -1)
                        self._batch_da += abs(da)
                    # Stall check: lots of commanded turning, almost none measured
                    if da and abs(dp) < 0.2 * abs(da):
                        self.stall += abs(da)
                    elif da:
                        self.stall, self.warned = 0.0, False
                    if self.stall > 40 and not self.warned:
                        print("Robot told to turn but the iPhone says it isn't (stuck or slipping?)")
                        self.warned = True
            self.prev_raw, self.prev_assumed_s = raw, assumed_s
            if self.sign is not None:
                self.offset = self.sign * self.measured - assumed_s
        # Learn how fast the robot really turns, so real-time predictions need less correcting
        if self._batch_da >= 10:
            ratio = self._batch_dp / self._batch_da
            if ratio >= 0.3:   # below that the robot is stuck, not slow: don't learn from it
                self.scale += SCALE_SMOOTH * (min(1.5, ratio) - self.scale)
            self._batch_dp = self._batch_da = 0.0

        if self.sign is None:
            return self.start + self.assumed      # timing only until we know the phone's direction
        self.applied += CORRECTION_RATE * (self.offset - self.applied)
        return self.start + self.assumed + self.applied

    @property
    def active(self):
        return self.sign is not None and self.phone.streaming
