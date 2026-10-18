"""Dashboard data for frontend/index.html (and iron-heart-web): the API robot/server.py used to serve on
port 5001, now served by follow_bridge.py itself so one program owns the BLE33 and the camera.

  GET  /status              wearer + robot state (G-force, activity, fall/emergency, people, modules)
  GET  /gforce              G-force history (last ~60 s) + fall markers
  GET  /falls               fall log
  GET  /video               robot camera (with detection boxes)
  GET  /simulate/fall       pretend the BLE33 reported a fall      (robot waits, like the real thing)
  GET  /simulate/emergency  pretend no double-tap came: emergency  (robot goes for help)
  GET  /simulate/reset      pretend the double-tap cancel
  GET  /modules/available|attached|history,  POST /modules/attach|detach|execute   (robot/modules)
  GET  /api/host/profile    host's medical condition (onboarding terminal);
                            POST {"condition", "description"?, "steps"?: [...]} sets it

The robot's own controls stay on port 5002 (see follow_bridge.start_http).
"""
import os
import sys
import time
from collections import deque

# robot/modules imports itself as "robot.modules", so the repo root must be importable (as server.py did)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from robot.modules.registry import registry
from host_profile import get_host_condition, get_host_profile, save_host_condition, speak_emergency


class DashboardData:
    """Wearer data for the dashboard: G-force history, activity level, fall log."""

    def __init__(self):
        self.gforce = deque(maxlen=300)    # (time, g), 5 per second from the BLE33 = 60 s
        # The BLE33 drops its fall/emergency flag after ~3 s; the dashboard keeps them up until RESET
        # (or the rescue ends), like robot/server.py did
        self.fall_latched = False
        self.emergency_latched = False
        # Backup fall detector state (see BackupFallDetector)
        self.backup = None
        self.falls = []                    # {time, time_str, impact_g, outcome, response_ms}
        self.fall_started = None           # when the current fall was first reported
        self.activity = "low"

    def on_gforce(self, _sender, data):
        """BLE33 G-force notification: uint16, g x 100."""
        g = int.from_bytes(bytes(data)[:2], "little") / 100.0
        self.gforce.append((time.time(), g))
        if self.backup:
            self.backup.on_g(g)
        recent = [v for _, v in list(self.gforce)[-50:]]
        if len(recent) >= 10:
            mean = sum(recent) / len(recent)
            var = sum((v - mean) ** 2 for v in recent) / len(recent)
            self.activity = "high" if var > 0.15 else "medium" if var > 0.03 else "low"

    @property
    def current_g(self):
        return self.gforce[-1][1] if self.gforce else 1.0

    def impact_g(self):
        """Biggest G in the last few seconds (the impact of the fall)."""
        cutoff = time.time() - 4
        return round(max([g for t, g in self.gforce if t >= cutoff] or [self.current_g]), 2)

    def on_fall_status(self, old, new):
        """BLE33 (or simulated) fall status changed: 0 normal, 1 fall detected, 2 emergency."""
        now = time.time()
        if new == 1 and old != 1:
            self.fall_started = now
            self.fall_latched = True
        elif new == 2 and old != 2:
            self.fall_latched, self.emergency_latched = False, True
            self._log("emergency", now)
            self._trigger_modules("emergency")
            # Say it out loud, with the host's condition (as robot/server.py did)
            speak_emergency(f"Emergency detected! Host has fallen. Host condition is: "
                            f"{get_host_condition('Not specified')}.")
        elif new == 0 and old == 1:
            self.fall_latched = False
            self._log("cancelled", now)

    def reset(self):
        """Dashboard RESET: clear the latched alerts."""
        self.fall_latched = self.emergency_latched = False

    def _log(self, outcome, now):
        response = int((now - self.fall_started) * 1000) if self.fall_started else 5000
        self.falls.append({"time": now, "time_str": time.strftime("%H:%M:%S"),
                           "impact_g": self.impact_g(), "outcome": outcome, "response_ms": response})
        self.fall_started = None

    def _trigger_modules(self, action):
        for slot in ("right_arm", "left_arm"):
            if registry._attached.get(slot):
                registry.execute(slot, action=action, robot_state={"emergency": True})


def status(dash, follower, seeker):
    history = registry.get_history()
    return {
        "emergency": dash.emergency_latched or follower.fall == 2,
        "fall_waiting": (dash.fall_latched or follower.fall == 1) and not dash.emergency_latched,
        "ble_connected": time.monotonic() - follower.last_data < 2 if follower.last_data else False,
        "direction": seeker.state if seeker and seeker.active else follower.state,
        "person_count": seeker.vision.people if seeker else 0,
        "current_g": round(dash.current_g, 2),
        "activity_level": dash.activity,
        "attached_modules": registry.get_attached(),
        "last_module_log": history[0] if history else None,
        "host_condition": get_host_condition("Not specified"),
        # robot extras (the new UI's robot panel can use these)
        "robot_mode": seeker.state if seeker and seeker.active else "follow",
        "following": follower.source,
        "awaiting_confirm": bool(seeker and seeker.awaiting_confirm),
    }


def handle(handler, dash, follower, seeker, method):
    """Serve one dashboard request on `handler` (a BaseHTTPRequestHandler). Returns False if the path
    isn't a dashboard path."""
    path = handler.path.split("?")[0]
    robot_state = {"emergency": follower.fall == 2, "fall_waiting": follower.fall == 1,
                   "direction": follower.state, "activity_level": dash.activity}
    if method == "GET":
        if path == "/status":
            return handler._json(status(dash, follower, seeker)) or True
        if path == "/gforce":
            data = list(dash.gforce)
            return handler._json({"timestamps": [t for t, _ in data], "values": [round(g, 2) for _, g in data],
                                  "falls": [{"time": f["time"], "g": f["impact_g"]} for f in dash.falls]}) or True
        if path == "/falls":
            return handler._json(dash.falls[-20:]) or True
        if path == "/simulate/fall":
            follower.report_fall(1)
            return handler._json({"status": "fall_waiting"}) or True
        if path == "/simulate/emergency":
            if follower.fall != 1:
                follower.report_fall(1)
            follower.report_fall(2)
            return handler._json({"status": "emergency"}) or True
        if path == "/simulate/reset":
            follower.report_fall(0)
            dash.reset()
            if dash.backup:
                dash.backup.cancel()
            return handler._json({"status": "normal"}) or True
        if path == "/api/host/profile":
            p = get_host_profile()
            return handler._json({"success": True, **p, "condition": p["condition"] or "Not specified"}) or True
        if path == "/modules/available":
            return handler._json(registry.get_available()) or True
        if path == "/modules/attached":
            return handler._json(registry.get_attached()) or True
        if path == "/modules/history":
            return handler._json(registry.get_history()) or True
    if method == "POST" and (path.startswith("/modules/") or path == "/api/host/profile"):
        import json
        body = handler.rfile.read(int(handler.headers.get("Content-Length", 0)) or 0)
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            data = {}
        if path == "/api/host/profile":
            cond = (data.get("condition") or "").strip()
            if not cond:
                return handler._json({"success": False, "error": "Condition cannot be empty"}, 400) or True
            description = (data.get("description") or "").strip()
            steps = [str(s).strip() for s in data.get("steps") or [] if str(s).strip()]
            save_host_condition(cond, description, steps)
            print(f"[HostProfile] Saved condition: {cond}" + (f" ({len(steps)} steps)" if steps else ""))
            return handler._json({"success": True, "condition": cond, "description": description,
                                  "steps": steps}) or True
        slot = data.get("slot")
        if not slot:
            return handler._json({"success": False, "error": "Missing slot"}) or True
        if path == "/modules/attach":
            return handler._json(registry.attach(slot, data.get("module_id"), robot_state=robot_state)) or True
        if path == "/modules/detach":
            return handler._json(registry.detach(slot, robot_state=robot_state)) or True
        if path == "/modules/execute":
            return handler._json(registry.execute(slot, action=data.get("action", "trigger"),
                                                  params=data.get("params"), robot_state=robot_state)) or True
    return False


class BackupFallDetector:
    """Backup fall detection from the G-force stream (see BACKUP_* in follow_config.py).
    Reports through follower.report_fall exactly like the BLE33, so the dashboard and the rescue
    react the same way. Call tick() regularly; it's fed by DashboardData.on_gforce."""

    def __init__(self, follower, cfg):
        self.follower, self.cfg = follower, cfg
        self.spike_at = None       # time of a big G spike being checked
        self.fall_at = None        # time we reported a fall (waiting for a cancel)

    def on_g(self, g):
        if self.follower.fall == 0 and self.fall_at is None and self.spike_at is None and g >= self.cfg.BACKUP_IMPACT_G:
            self.spike_at = time.monotonic()
            print(f"Backup fall check: {g:.2f} g spike, waiting to see if you stay down...")

    def cancel(self):
        self.spike_at = self.fall_at = None

    def tick(self):
        f, now = self.follower, time.monotonic()
        if self.spike_at is not None:
            moved = f.last_step_t > self.spike_at or f.motion > self.cfg.BACKUP_STILL_MG
            if moved and now - self.spike_at > 0.5:      # got up / kept walking: not a fall
                self.spike_at = None
            elif now - self.spike_at >= self.cfg.BACKUP_STILL_S:
                self.spike_at = None
                if f.fall == 0:
                    print("Backup fall detector: FALL (big impact, then staying down)")
                    self.fall_at = now
                    f.report_fall(1)
        if self.fall_at is not None:
            if f.fall != 1:                               # cancelled (RESET) or the BLE33 took over
                self.fall_at = None
            elif now - self.fall_at >= self.cfg.BACKUP_CONFIRM_S:
                print("Backup fall detector: no cancel, EMERGENCY")
                self.fall_at = None
                f.report_fall(2)
