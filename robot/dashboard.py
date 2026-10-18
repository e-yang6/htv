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

The robot's own controls stay on port 5002 (see follow_bridge.start_http).
"""
import os
import sys
import time
from collections import deque

# robot/modules imports itself as "robot.modules", so the repo root must be importable (as server.py did)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from robot.modules.registry import registry


class DashboardData:
    """Wearer data for the dashboard: G-force history, activity level, fall log."""

    def __init__(self):
        self.gforce = deque(maxlen=300)    # (time, g), 5 per second from the BLE33 = 60 s
        self.falls = []                    # {time, time_str, impact_g, outcome, response_ms}
        self.fall_started = None           # when the current fall was first reported
        self.activity = "low"

    def on_gforce(self, _sender, data):
        """BLE33 G-force notification: uint16, g x 100."""
        g = int.from_bytes(bytes(data)[:2], "little") / 100.0
        self.gforce.append((time.time(), g))
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
        elif new == 2 and old != 2:
            self._log("emergency", now)
            self._trigger_modules("emergency")
        elif new == 0 and old == 1:
            self._log("cancelled", now)

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
        "emergency": follower.fall == 2,
        "fall_waiting": follower.fall == 1,
        "ble_connected": time.monotonic() - follower.last_data < 2 if follower.last_data else False,
        "direction": seeker.state if seeker and seeker.active else follower.state,
        "person_count": seeker.vision.people if seeker else 0,
        "current_g": round(dash.current_g, 2),
        "activity_level": dash.activity,
        "attached_modules": registry.get_attached(),
        "last_module_log": history[0] if history else None,
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
            return handler._json({"status": "normal"}) or True
        if path == "/modules/available":
            return handler._json(registry.get_available()) or True
        if path == "/modules/attached":
            return handler._json(registry.get_attached()) or True
        if path == "/modules/history":
            return handler._json(registry.get_history()) or True
    if method == "POST" and path.startswith("/modules/"):
        import json
        body = handler.rfile.read(int(handler.headers.get("Content-Length", 0)) or 0)
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            data = {}
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
