import cv2
import asyncio
import threading
import time
from collections import deque
from flask import Flask, Response, jsonify
from flask_cors import CORS
from ultralytics import YOLO

app = Flask(__name__)
CORS(app)

# --- BLE config ---
ARDUINO_NAME = "FallDetector"
FALL_CHAR_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214"
GFORCE_CHAR_UUID = "19b10002-e8f2-537e-4f6c-d104768a1214"

# --- State ---
emergency = False
fall_waiting = False
ble_connected = False
latest_direction = ""
person_count = 0

# G-force history (timestamp, value) — keep last 60 seconds
gforce_history = deque(maxlen=300)
# Fall event log: [{time, impact_g, outcome, response_ms}]
fall_history = []
# Track when fall was first detected for response time
fall_detected_time = None

# Activity level from G-force variance
activity_level = "low"

model = YOLO("yolov8n.pt")
cap = None


def compute_activity():
    global activity_level
    if len(gforce_history) < 10:
        activity_level = "low"
        return

    recent = [g for _, g in list(gforce_history)[-50:]]
    avg = sum(recent) / len(recent)
    variance = sum((g - avg) ** 2 for g in recent) / len(recent)

    if variance > 0.15:
        activity_level = "high"
    elif variance > 0.03:
        activity_level = "medium"
    else:
        activity_level = "low"


def find_nearest_person(results, frame_width):
    best = None
    best_score = -1
    for r in results:
        for box in r.boxes:
            if int(box.cls[0]) != 0:
                continue
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            w = x2 - x1
            h = y2 - y1
            area = w * h
            center_x = (x1 + x2) / 2
            center_dist = abs(center_x - frame_width / 2) / frame_width
            score = area * (1 - 0.3 * center_dist)
            if score > best_score:
                best_score = score
                best = (int(x1), int(y1), int(x2), int(y2), center_x)
    return best


def get_direction(person_center_x, frame_width):
    third = frame_width / 3
    if person_center_x < third:
        return "LEFT"
    elif person_center_x > third * 2:
        return "RIGHT"
    else:
        return "FORWARD"


def generate_frames():
    global cap, latest_direction, person_count
    cap = cv2.VideoCapture(0)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_width = frame.shape[1]
        results = model(frame, classes=[0], verbose=False)

        count = 0
        for r in results:
            for box in r.boxes:
                if int(box.cls[0]) == 0:
                    count += 1
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                conf = float(box.conf[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"person {conf:.0%}", (x1, y1 - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        person_count = count

        if emergency:
            person = find_nearest_person(results, frame_width)
            if person:
                x1, y1, x2, y2, cx = person
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 4)
                latest_direction = get_direction(cx, frame_width)
                cv2.putText(frame, f"TARGET — {latest_direction}", (x1, y1 - 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            else:
                latest_direction = "SCANNING"

        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')


@app.route('/video')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/status')
def status():
    current_g = gforce_history[-1][1] if gforce_history else 1.0
    return jsonify({
        'emergency': emergency,
        'fall_waiting': fall_waiting,
        'ble_connected': ble_connected,
        'direction': latest_direction,
        'person_count': person_count,
        'current_g': round(current_g, 2),
        'activity_level': activity_level,
    })


@app.route('/gforce')
def gforce_data():
    data = list(gforce_history)
    return jsonify({
        'timestamps': [t for t, _ in data],
        'values': [round(g, 2) for _, g in data],
        'falls': [{'time': f['time'], 'g': f.get('impact_g', 0)} for f in fall_history]
    })


@app.route('/falls')
def falls_data():
    return jsonify(fall_history[-20:])


@app.route('/simulate/emergency')
def sim_emergency():
    global emergency, fall_waiting, fall_detected_time
    emergency = True
    fall_waiting = False
    fall_history.append({
        'time': time.time(),
        'time_str': time.strftime('%H:%M:%S'),
        'impact_g': gforce_history[-1][1] if gforce_history else 0,
        'outcome': 'emergency',
        'response_ms': 5000
    })
    fall_detected_time = None
    return jsonify({'status': 'emergency'})


@app.route('/simulate/fall')
def sim_fall():
    global fall_waiting, fall_detected_time
    fall_waiting = True
    fall_detected_time = time.time()
    return jsonify({'status': 'fall_waiting'})


@app.route('/simulate/reset')
def sim_reset():
    global emergency, fall_waiting, fall_detected_time
    if fall_waiting and fall_detected_time:
        response_ms = int((time.time() - fall_detected_time) * 1000)
        fall_history.append({
            'time': time.time(),
            'time_str': time.strftime('%H:%M:%S'),
            'impact_g': gforce_history[-1][1] if gforce_history else 0,
            'outcome': 'cancelled',
            'response_ms': response_ms
        })
    emergency = False
    fall_waiting = False
    fall_detected_time = None
    return jsonify({'status': 'normal'})


def run_ble():
    global emergency, fall_waiting, ble_connected, fall_detected_time

    try:
        from bleak import BleakClient, BleakScanner
    except ImportError:
        print("BLE disabled — install bleak: pip install bleak")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def ble_loop():
        global emergency, fall_waiting, ble_connected, fall_detected_time
        while True:
            try:
                print("Scanning for FallDetector...")
                device = await BleakScanner.find_device_by_name(ARDUINO_NAME, timeout=10)
                if not device:
                    print("FallDetector not found, retrying...")
                    await asyncio.sleep(2)
                    continue

                async with BleakClient(device) as client:
                    ble_connected = True
                    print(f"Connected to FallDetector ({device.address})")

                    def on_fall(sender, data):
                        global emergency, fall_waiting, fall_detected_time
                        value = data[0]
                        if value == 0:
                            if fall_waiting and fall_detected_time:
                                response_ms = int((time.time() - fall_detected_time) * 1000)
                                fall_history.append({
                                    'time': time.time(),
                                    'time_str': time.strftime('%H:%M:%S'),
                                    'impact_g': gforce_history[-1][1] if gforce_history else 0,
                                    'outcome': 'cancelled',
                                    'response_ms': response_ms
                                })
                            emergency = False
                            fall_waiting = False
                            fall_detected_time = None
                            print("BLE: Normal")
                        elif value == 1:
                            fall_waiting = True
                            emergency = False
                            fall_detected_time = time.time()
                            print("BLE: Fall detected — waiting")
                        elif value == 2:
                            response_ms = int((time.time() - fall_detected_time) * 1000) if fall_detected_time else 5000
                            fall_history.append({
                                'time': time.time(),
                                'time_str': time.strftime('%H:%M:%S'),
                                'impact_g': gforce_history[-1][1] if gforce_history else 0,
                                'outcome': 'emergency',
                                'response_ms': response_ms
                            })
                            emergency = True
                            fall_waiting = False
                            fall_detected_time = None
                            print("BLE: EMERGENCY")

                    def on_gforce(sender, data):
                        raw = int.from_bytes(data[:2], byteorder='little')
                        g = raw / 100.0
                        gforce_history.append((time.time(), g))
                        compute_activity()

                    await client.start_notify(FALL_CHAR_UUID, on_fall)
                    await client.start_notify(GFORCE_CHAR_UUID, on_gforce)

                    while client.is_connected:
                        await asyncio.sleep(1)

                    ble_connected = False
                    print("BLE disconnected")
            except Exception as e:
                ble_connected = False
                print(f"BLE error: {e}")
                await asyncio.sleep(3)

    loop.run_until_complete(ble_loop())


def start_ble_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    run_ble()


if __name__ == "__main__":
    ble_thread = threading.Thread(target=start_ble_thread, daemon=True)
    ble_thread.start()

    print("Server running at http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, threaded=True)
