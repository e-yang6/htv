"""Robot heading from the iPhone riding on the robot (its gyro), for follow_bridge.py.

Without this the bridge only *assumes* how far the robot turned (time x TURN_RATE_DPS),
so slips, coasting and battery sag go unnoticed. With it, every turn is checked against
what the robot really did.

Two iPhone apps work:
  - ZIG SIM:       UDP, JSON format, sensors Gyro + Gravity, to <mac ip>:50000
  - Sensor Logger: HTTP push to http://<mac ip>:5002/phone (Gyroscope + Gravity enabled);
                   keeps streaming in the background, so it can share the phone with Continuity Camera

Heading = gyro integrated around the gravity axis, so the phone can be mounted any way up.
Which way is "left" is learned automatically from the first turns the robot makes.
"""
import json
import math
import socket
import threading
import time

UDP_PORT = 50000
FRESH_S = 0.3           # readings older than this = phone not streaming
SIGN_LEARN_DEG = 30     # degrees of commanded turning needed to learn the sign


class PhoneIMU:
    def __init__(self, udp_port=UDP_PORT):
        self.lock = threading.Lock()
        self.gravity = None        # (x, y, z), any units
        self.yaw = 0.0             # integrated heading, degrees, unsigned (sign applied in reading())
        self.rate = 0.0            # latest yaw rate, deg/s
        self.last_t = None         # timestamp of the last gyro sample (seconds, phone clock)
        self.last_rx = 0.0         # monotonic time we last got a gyro sample
        self.samples = 0
        self.source = None
        self.sign = None           # +1/-1 once learned; None = not yet
        self._learn = 0.0          # sum of (commanded direction x measured rate x dt)
        self._learn_cmd = 0.0      # total commanded turning (deg) seen while learning
        threading.Thread(target=self._udp, args=(udp_port,), daemon=True).start()

    # --- input ---
    def _udp(self, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError as e:
            print(f"Phone IMU: can't listen on UDP {port} ({e})")
            return
        while True:
            data, _ = sock.recvfrom(65536)
            try:
                self.feed(json.loads(data.decode(errors="ignore")))
            except ValueError:
                pass   # OSC or junk; only JSON is supported

    def feed(self, msg):
        """Accepts a ZIG SIM JSON packet or a Sensor Logger HTTP push body."""
        if isinstance(msg, dict) and "sensordata" in msg:            # ZIG SIM
            sd = msg["sensordata"]
            g, w = sd.get("gravity"), sd.get("gyro")
            if g:
                self._gravity(g["x"], g["y"], g["z"])
            if w:
                self._gyro(w["x"], w["y"], w["z"], None, "ZIG SIM")
        elif isinstance(msg, dict) and "payload" in msg:             # Sensor Logger
            for item in msg["payload"]:
                v, name = item.get("values", {}), item.get("name", "")
                t = item.get("time")
                t = t / 1e9 if isinstance(t, (int, float)) and t > 1e12 else None   # ns -> s
                if name == "gravity":
                    self._gravity(v["x"], v["y"], v["z"])
                elif name in ("gyroscope", "gyroscopeuncalibrated"):
                    self._gyro(v["x"], v["y"], v["z"], t, "Sensor Logger")

    def _gravity(self, x, y, z):
        with self.lock:
            self.gravity = (x, y, z)

    def _gyro(self, x, y, z, t, source):
        now = time.monotonic()
        with self.lock:
            g = self.gravity
            if not g:
                return
            n = math.sqrt(g[0] ** 2 + g[1] ** 2 + g[2] ** 2)
            if n < 1e-6:
                return
            rate = math.degrees((x * g[0] + y * g[1] + z * g[2]) / n)   # rad/s around vertical -> deg/s
            t = t if t is not None else now
            dt = t - self.last_t if self.last_t is not None else 0.0
            if not 0 < dt < 0.2:
                dt = 0.0                     # first sample or a gap: don't integrate across it
            self.yaw += rate * dt
            self.rate = rate
            self.last_t = t
            self.last_rx = now
            self.samples += 1
            if self.source is None:
                print(f"Phone IMU: receiving from {source}")
            self.source = source

    # --- output ---
    @property
    def fresh(self):
        return time.monotonic() - self.last_rx < FRESH_S

    def learn_sign(self, commanded_dps, dt):
        """Called every tick with the turn we commanded (+ = left). Works out which way the phone's 'left' is."""
        if self.sign is not None or not commanded_dps or not self.fresh:
            return
        with self.lock:
            self._learn += math.copysign(1, commanded_dps) * self.rate * dt
            self._learn_cmd += abs(commanded_dps) * dt
            if self._learn_cmd >= SIGN_LEARN_DEG and abs(self._learn) > 5:
                self.sign = 1 if self._learn > 0 else -1
                print(f"Phone IMU: heading direction learned (sign {self.sign:+d}), "
                      f"measured {abs(self._learn):.0f} deg for {self._learn_cmd:.0f} commanded")

    def reading(self):
        """Signed heading in degrees (+ = left), or None if not usable yet."""
        if self.sign is None or not self.fresh:
            return None
        with self.lock:
            return self.sign * self.yaw
