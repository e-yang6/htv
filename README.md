# Fall Detector

## Setup

### Terminal 1 — Backend (camera + YOLO + BLE)
```
pip install -r requirements.txt
python robot/server.py
```

### Terminal 2 — Frontend
```
cd frontend
python -m http.server 8080
```

Open http://localhost:8080
