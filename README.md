# Fall Detector

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