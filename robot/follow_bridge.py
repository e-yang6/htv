"""Follow-me: the robot follows the wearer's BLE33 (fall_detection.ino) using its gyro and step count.

Where things are:
  follow_config.py  every setting (tune here)
  follower.py       the follow logic: heading + steps in, motor command out
  robots.py         links to the robot (UNO Q router, UNO Q over TCP, USB Uno)
  phone_imu.py      optional: iPhone on the robot measures its real turns
  seeker.py         optional: camera go-to-person / fall rescue (--seek)
  dashboard.py      data for frontend/index.html: G-force, falls, modules (port 5001)

Start with you ~4 ft in front of the robot, both facing the same way:
  on the UNO Q:  python3 follow_bridge.py --robot-router          (~/robot/start_robot.sh)
  on the Mac:    ./run_mac.sh   everything incl. camera go-to-person (UNO Q plugged in by USB)
                 python3 follow_bridge.py --port /dev/cu.usbserial-210   (USB Uno)
"""
import argparse
import asyncio
import socket
import threading
import time

import follow_config as cfg
from follower import Follower, wrap
from robots import make_robot


# ---------------------------------------------------------------------- BLE33
async def ble_task(follower, dash=None):
    from bleak import BleakClient, BleakScanner

    while True:
        try:
            print(f"Scanning for {cfg.BLE_NAME}...")
            device = await BleakScanner.find_device_by_name(cfg.BLE_NAME, timeout=10)
            if not device:
                print(f"{cfg.BLE_NAME} not found (is the BLE33 on?), retrying...")
                await asyncio.sleep(2)
                continue
            async with BleakClient(device) as client:
                print(f"Connected to {cfg.BLE_NAME} ({device.address}), assuming you're "
                      f"{cfg.FOLLOW_START_M} m in front of the robot, facing the same way")
                follower.resync()
                await client.start_notify(cfg.FOLLOW_CHAR_UUID, follower.on_data)

                def on_fall(_sender, data):
                    follower.report_fall(data[0])
                    print({0: "BLE33: normal", 1: "BLE33: FALL DETECTED", 2: "BLE33: EMERGENCY"}.get(data[0], data[0]))

                await client.start_notify(cfg.FALL_CHAR_UUID, on_fall)
                if dash:
                    await client.start_notify(cfg.GFORCE_CHAR_UUID, dash.on_gforce)
                while client.is_connected:
                    await asyncio.sleep(0.5)
                print("BLE disconnected")
        except Exception as e:
            print(f"BLE error: {e}, retrying in 3s...")
            await asyncio.sleep(3)


# ---------------------------------------------------------------------- control loop
def status_line(follower, worst_dt, fusion, seeker):
    ph = f"{follower.person_heading:5.0f}" if follower.person_heading is not None else "   --"
    rssi = f"{follower.rssi:.0f}dBm" if follower.rssi is not None else "--"
    state = seeker.state if seeker and seeker.active else follower.state
    return (f"[{state:>14}] behind {follower.gap:4.1f}m  steps {follower.steps if follower.steps is not None else '--'}  "
            f"you {ph}  robot {follower.robot_heading:5.0f}  rssi {rssi}  loop {worst_dt * 1000:.0f}ms  "
            f"ble {follower.packets}/s  drift {follower.drift_dps:+.1f}/s  motion {follower.motion}mg  "
            f"{follower.source}")


async def control_task(follower, robot, seeker=None, phone=None, dash=None):
    from phone_imu import HeadingFusion
    # Started now (not at the first phone packet) so every turn the robot makes is on record
    fusion = HeadingFusion(phone, follower.robot_heading) if phone else None
    period = 1 / cfg.SEND_HZ
    last = last_print = time.monotonic()
    cmd, fall_seen, worst_dt = (0, 0), (0, 0), 0.0
    while True:
        await asyncio.sleep(period)
        now = time.monotonic()
        dt, last = now - last, now
        worst_dt = max(worst_dt, dt)

        # 1. Account for what the robot did since the last tick (nothing, if it isn't connected)
        if not robot.ser:
            cmd = (0, 0)
            follower.reset_distance()   # don't build up a huge gap to chase once it reconnects
        if fusion:
            rate = follower.turn_rate
            commanded = rate if cmd == (0, cfg.SPEED) else -rate if cmd == (cfg.SPEED, 0) else 0.0
            target = fusion.step(now, commanded, cmd != (0, 0), dt)
            follower.track(cmd, dt, dheading=wrap(target - follower.robot_heading))
        else:
            follower.track(cmd, dt)
        if dash and dash.backup:
            dash.backup.tick()
        if seeker:
            seeker.update_pose(cmd, follower.robot_heading, dt)
            fall_seen = handle_fall(follower, seeker, fall_seen)

        # 2. Decide and send (every tick: the robot stops by itself if commands stop)
        if seeker and seeker.active:
            cmd = seeker.step(follower.robot_heading, now)
            if cmd is None:
                print("Back at the start, follow mode")
                follower.reset_distance()
                if follower.fall:
                    follower.report_fall(0)   # rescue done: clear the alarm so the next fall counts
                if dash:
                    dash.reset()
                cmd = (0, 0)
        else:
            sticker = seeker.vision.sticker(cfg.PATCH_FRESH_S) if seeker else None
            person = seeker.vision.followed(cfg.PERSON_FRESH_S) if seeker else None
            cmd = follower.step(sticker, person)
        robot.drive(*cmd)
        if seeker and seeker.arm_cmd:
            robot.send(seeker.arm_cmd)
            seeker.arm_cmd = None

        if now - last_print > 1:
            last_print = now
            print(status_line(follower, worst_dt, fusion, seeker))
            worst_dt = 0.0
            follower.packets, follower.worst_gap = 0, 0.0


def handle_fall(follower, seeker, seen):
    """--seek only: when the wearer falls, fetch the nearest other person, then lead them back.
    seen = (fall events, cancel events) already handled; returns the updated pair."""
    falls, cancels = seen
    if follower.fall_events != falls:
        follower.stop("paused")
        seeker.start(follower.robot_heading, emergency=True)
        print("Fall: going to get the nearest person")
    elif follower.cancel_events != cancels and seeker.emergency and not seeker.returning:
        seeker.cancel()
        follower.reset_distance()
        print("Fall cancelled on the BLE33, back to follow mode")
    return follower.fall_events, follower.cancel_events


# ---------------------------------------------------------------------- dashboard / phone API
def start_http(follower, seeker, phone, port, dash=None, dash_port=None):
    """frontend/index.html and the iPhone talk to this: GET /status, POST /seek, GET /video, POST /phone,
    POST /simulate-fall (test the fall response)."""
    import json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    def status():
        t = seeker.vision.latest(1.0) if seeker else None
        return {
            "mode": seeker.state if seeker and seeker.active else "follow",
            "follow_state": follower.state,
            "camera": bool(seeker and seeker.vision.ok),
            "emergency": bool(seeker and seeker.emergency),
            "people": seeker.vision.people if seeker else 0,
            "following": follower.source,
            "awaiting_confirm": bool(seeker and seeker.awaiting_confirm),
            "target": {k: round(t[k], 2) for k in ("cx", "area", "bottom")} if t else None,
        }

    def toggle_seek():
        if not seeker:
            return
        if not seeker.active:
            follower.stop("paused")
            seeker.start(follower.robot_heading)
        elif seeker.returning or seeker.state == "home":
            seeker.cancel()
            follower.reset_distance()
        else:
            seeker.go_home()

    class Handler(BaseHTTPRequestHandler):
        def _head(self, code, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

        def _json(self, obj):
            self._head(200, "application/json")
            self.wfile.write(json.dumps(obj).encode())

        def do_GET(self):
            if self.path.startswith("/status"):
                self._json(status())
            elif self.path.startswith("/video") and seeker:
                self._head(200, "multipart/x-mixed-replace; boundary=frame")
                try:
                    while True:
                        if seeker.vision.jpeg:
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + seeker.vision.jpeg + b"\r\n")
                        time.sleep(0.1)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            else:
                self._head(404, "text/plain")

        def do_POST(self):
            if self.path.startswith("/phone") and phone:
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                phone.raw(body, "HTTP")
                try:
                    phone.feed(json.loads(body))
                except ValueError:
                    pass
                self._json({"ok": True})
            elif self.path.startswith("/simulate-fall"):
                # Test the fall response without falling: same as the BLE33 reporting a fall (1),
                # /simulate-fall?clear=1 = same as the double-tap cancel (0)
                # A one-off event: leaves the BLE33's real fall status alone, so a real fall after
                # a test is never missed
                if "clear" in self.path:
                    follower.cancel_events += 1
                else:
                    follower.fall_events += 1
                print("Simulated " + ("fall cancelled" if "clear" in self.path else "FALL"))
                self._json(status())
            elif self.path.startswith("/confirm") and seeker:
                seeker.confirm()      # bystander: "yes, I'll come" -> wave, then lead them back
                self._json(status())
            elif self.path.startswith("/reject") and seeker:
                seeker.reject()       # bystander: "no" -> look for someone else
                self._json(status())
            elif self.path.startswith("/camera-reset") and seeker:
                seeker.vision.reopen = True   # reconnect the camera without restarting anything else
                self._json(status())
            elif self.path.startswith("/select") and seeker:
                # Dashboard click on the video: /select?x=0.4&y=0.6 (0-1), /select?clear=1
                from urllib.parse import parse_qs, urlparse
                q = parse_qs(urlparse(self.path).query)
                if "clear" in q:
                    seeker.vision.select(-1, -1)
                else:
                    seeker.vision.select(float(q["x"][0]), float(q["y"][0]))
                self._json(status())
            elif self.path.startswith("/seek"):
                toggle_seek()
                self._json(status())
            else:
                self._head(404, "text/plain")

        def log_message(self, *args):
            pass

    class DashboardHandler(Handler):
        """Port 5001: what robot/server.py used to serve (frontend/index.html polls this)."""
        def do_GET(self):
            import dashboard
            if self.path.startswith("/video"):
                return Handler.do_GET(self)
            if not dashboard.handle(self, dash, follower, seeker, "GET"):
                self._head(404, "text/plain")

        def do_POST(self):
            import dashboard
            if not dashboard.handle(self, dash, follower, seeker, "POST"):
                self._head(404, "text/plain")

        def do_OPTIONS(self):   # CORS preflight for the modules POSTs (JSON body)
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

    class DualStackServer(ThreadingHTTPServer):
        address_family = socket.AF_INET6   # IPv4 and IPv6: an iPhone hotspot only carries IPv6

        def server_bind(self):
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            super().server_bind()

    server = DualStackServer(("::", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Robot API on http://localhost:{port}")
    if dash and dash_port:
        dserver = DualStackServer(("::", dash_port), DashboardHandler)
        threading.Thread(target=dserver.serve_forever, daemon=True).start()
        print(f"Dashboard API on http://localhost:{dash_port} (frontend/index.html)")


# ---------------------------------------------------------------------- calibration helpers
async def hold(robot, cmd, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        robot.drive(*cmd)
        await asyncio.sleep(1 / cfg.SEND_HZ)
    robot.drive(0, 0)


async def calibrate(args, robot):
    """--set-speed / --drive-test / --spin / --calibrate-turn. Returns True if one ran."""
    from calibration import save_calibration
    if args.set_speed:
        save_calibration(speed_mps=args.set_speed)
        print(f"Saved robot speed {args.set_speed} m/s")
    elif args.drive_test:
        print(f"Driving straight for {args.drive_test}s...")
        await hold(robot, (cfg.SPEED, cfg.SPEED), args.drive_test)
        print(f"Measure the distance in metres, then: --set-speed <metres / {args.drive_test}>")
    elif args.spin:
        print(f"Spinning on the left motor for {args.spin}s...")
        await hold(robot, (cfg.SPEED, 0), args.spin)
        print(f"Measure the angle; turn rate = degrees / {args.spin}")
    elif args.spin_left or args.spin_right:
        secs = args.spin_left or args.spin_right
        cmd = (0, cfg.SPEED) if args.spin_left else (cfg.SPEED, 0)
        print(f"Turning {'left (counter-clockwise)' if args.spin_left else 'right (clockwise)'} for {secs}s...")
        await hold(robot, cmd, secs)
        print(f"Measure the angle, then: --set-turn {'left' if args.spin_left else 'right'} <degrees / {secs}>")
    elif args.set_turn:
        side, rate = args.set_turn
        save_calibration(**{f"turn_{side}_dps": float(rate)})
        print(f"Saved {side} turn rate {rate} deg/s")
    elif args.calibrate_turn:
        from seeker import Vision, calibrate_turn
        vision = Vision(args.camera)
        while not vision.small:
            await asyncio.sleep(0.1)
        await asyncio.to_thread(calibrate_turn, vision, robot.drive, cfg.SPEED)
    else:
        return False
    return True


# ---------------------------------------------------------------------- main
async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    link = parser.add_argument_group("robot link (pick one)")
    link.add_argument("--robot-router", nargs="?", const="local", metavar="HOST:PORT",
                      help="UNO Q MCU via its router: no value = running on the board; "
                           "localhost:5006 = from the Mac over USB (run_mac.sh sets this up)")
    link.add_argument("--robot-net", metavar="HOST[:PORT]",
                      help="UNO Q from the Mac: localhost (USB + adb forward) or its Wi-Fi name, e.g. htv.local")
    link.add_argument("--port", help="classic USB Uno/Nano, e.g. /dev/cu.usbserial-210")
    extra = parser.add_argument_group("optional")
    extra.add_argument("--seek", action="store_true",
                       help="camera go-to-person + fall rescue (Mac only; needs OpenCV + YOLO)")
    extra.add_argument("--camera", type=int, default=None,
                       help="camera index for --seek / --calibrate-turn (default: the iPhone, found by name)")
    extra.add_argument("--laptop-on-robot", action="store_true",
                       help="this machine rides on the robot, so signal strength = distance to you")
    extra.add_argument("--http-port", type=int, default=5002, help="robot API port (robot controls, iPhone)")
    extra.add_argument("--dashboard-port", type=int, default=5001,
                       help="dashboard data port (frontend/index.html; replaces robot/server.py)")
    cal = parser.add_argument_group("calibration")
    cal.add_argument("--drive-test", type=float, metavar="SECONDS", help="drive straight, then measure the distance")
    cal.add_argument("--set-speed", type=float, metavar="M_PER_S", help="save the measured forward speed")
    cal.add_argument("--spin", type=float, metavar="SECONDS", help="spin on one motor, then measure the angle")
    cal.add_argument("--calibrate-turn", action="store_true", help="measure the turn rate with the camera")
    cal.add_argument("--spin-left", type=float, metavar="SECONDS", help="turn left (CCW) for SECONDS, then measure")
    cal.add_argument("--spin-right", type=float, metavar="SECONDS", help="turn right (CW) for SECONDS, then measure")
    cal.add_argument("--set-turn", nargs=2, metavar=("left|right", "DEG_PER_S"), help="save a measured turn rate")
    args = parser.parse_args()

    if not (args.port or args.robot_net or args.robot_router or args.set_speed or args.set_turn):
        parser.error("pick a robot link: --robot-router, --robot-net or --port")
    robot = None if (args.set_speed or args.set_turn) else make_robot(args)
    try:
        if await calibrate(args, robot):
            return

        from calibration import load_calibration, load_side_rates, load_speed
        left_dps, right_dps = load_side_rates()
        follower = Follower(use_rssi=args.laptop_on_robot,
                            turn_rate_dps=load_calibration(cfg.TURN_RATE_DPS),
                            speed_mps=load_speed(cfg.ROBOT_SPEED_MPS),
                            left_dps=left_dps, right_dps=right_dps)
        print(f"Turn rate left {follower.rate_left:.1f} / right {follower.rate_right:.1f} deg/s, "
              f"speed {follower.speed_mps:.2f} m/s, deadband {follower.deadband:.1f} deg")

        seeker = None
        if args.seek:
            from seeker import Seeker, Vision
            seeker = Seeker(Vision(args.camera), cfg.SPEED, follower.turn_rate)
            seeker.rate_left, seeker.rate_right = follower.rate_left, follower.rate_right
        phone = None
        if cfg.USE_PHONE_HEADING:
            from phone_imu import PhoneIMU
            phone = PhoneIMU()
        try:
            from dashboard import BackupFallDetector, DashboardData
            dash = DashboardData()
            follower.on_fall_change = dash.on_fall_status
            if cfg.BACKUP_FALL:
                dash.backup = BackupFallDetector(follower, cfg)
        except ImportError as e:   # e.g. on the UNO Q, which doesn't have robot/modules
            print(f"Dashboard API off ({e})")
            dash = None
        start_http(follower, seeker, phone, args.http_port, dash, args.dashboard_port)
        await asyncio.gather(ble_task(follower, dash), control_task(follower, robot, seeker, phone, dash))
    finally:
        if robot:
            robot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")
