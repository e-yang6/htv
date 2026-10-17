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
cd frontend
python -m http.server 8080
```

Open http://localhost:8080

### Terminal 3 — Robot follow bridge (optional)
```
python robot/follow_bridge.py --port COM<X>
```

First-time calibration:
```
python robot/follow_bridge.py --port COM<X> --calibrate-turn
```

# Frontend Web
```
cd iron-heart-web
npm i
npm run dev
```