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

### Mobile access (ngrok)

The frontend proxies API requests through Vite, so you only need one tunnel.

1. Install [ngrok](https://ngrok.com/) and sign in.
2. With the Vite dev server running, open a new terminal:
   ```
   ngrok http 5173 --host-header=localhost:5173
   ```
3. Open the `https://xxxx.ngrok-free.app` URL on your phone.
   You may need to click through ngrok's free-tier interstitial page on first load.