# Ironheart

## Setup

```
pip install -r requirements.txt
```

### Terminal 1 — Backend (camera + YOLO + BLE)
```
python robot/server.py
```

### Terminal 2 — Frontend
```
cd iron-heart-web
npm i
npm run dev
```

Open http://localhost:5173

### Terminal 3 — Robot follow bridge (optional)
```
python robot/follow_bridge.py --port COM<X>
```

First-time calibration:
```
python robot/follow_bridge.py --port COM<X> --calibrate-turn
```

## Robot on the Arduino UNO Q (all-in-one)

With the UNO Q plugged into the Mac by USB, one command runs everything: BLE33 follow mode, the
iPhone camera (go-to-person, fall rescue, sticker / click-to-follow), the dashboard data that
`robot/server.py` used to serve (port 5001), robot controls (5002) and the dashboard itself:

```
cd robot && ./run_mac.sh
```

If ngrok is installed and signed in (see Mobile access below), it also prints a phone link to the
dashboard.

Don't also run `robot/server.py` (it would fight the bridge for the BLE33 and the camera), and
don't use the dashboard's Web Bluetooth "Connect BLE" (same reason).

Then: reset the BLE33 lying flat, wait 5 s, strap it on, stand ~4 ft in front of the robot facing
the same way and keep still for the 4 s warm-up. Click yourself in the camera feed to lock on.

- Settings: `robot/follow_config.py` (every tunable, commented)
- Follow logic: `robot/follower.py`; robot links: `robot/robots.py`; dashboard API: `robot/dashboard.py`
- Unplugged from the Mac, the UNO Q starts gyro-only follow mode by itself on boot
  (`robot/unoq_robot/start_robot.sh`, no camera features)
- Calibrate turns per direction: `--spin-left 3` / `--spin-right 3`, then
  `--set-turn left|right <degrees / 3>`

### Mobile access (ngrok)

The frontend proxies API requests through Vite, so you only need one tunnel.

1. Install [ngrok](https://ngrok.com/) and sign in.
2. With the Vite dev server running, open a new terminal:
   ```
   ngrok http 5173 --host-header=localhost:5173
   ```
3. Open the `https://xxxx.ngrok-free.app` URL on your phone.
   You may need to click through ngrok's free-tier interstitial page on first load.
