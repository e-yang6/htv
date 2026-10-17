import cv2
import asyncio
import threading
import time
from flask import Flask, Response, jsonify
from ultralytics import YOLO

app = Flask(__name__)

# --- BLE config ---
ARDUINO_NAME = "FallDetector"
FALL_CHAR_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214"

# --- State ---
emergency = False
fall_waiting = False
ble_connected = False
latest_direction = ""

model = YOLO("yolov8n.pt")
cap = None


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
    global cap, latest_direction
    cap = cv2.VideoCapture(0)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_width = frame.shape[1]
        results = model(frame, classes=[0], verbose=False)

        # Draw all detected people
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                conf = float(box.conf[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"person {conf:.0%}", (x1, y1 - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Emergency mode — highlight target
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
    return jsonify({
        'emergency': emergency,
        'fall_waiting': fall_waiting,
        'ble_connected': ble_connected,
        'direction': latest_direction
    })


@app.route('/simulate/emergency')
def sim_emergency():
    global emergency, fall_waiting
    emergency = True
    fall_waiting = False
    return jsonify({'status': 'emergency'})


@app.route('/simulate/reset')
def sim_reset():
    global emergency, fall_waiting
    emergency = False
    fall_waiting = False
    return jsonify({'status': 'normal'})


def run_ble():
    global emergency, fall_waiting, ble_connected

    try:
        from bleak import BleakClient, BleakScanner
    except ImportError:
        print("BLE disabled — install bleak: pip install bleak")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def ble_loop():
        global emergency, fall_waiting, ble_connected
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

                    def on_notify(sender, data):
                        global emergency, fall_waiting
                        value = data[0]
                        if value == 0:
                            emergency = False
                            fall_waiting = False
                            print("BLE: Normal")
                        elif value == 1:
                            fall_waiting = True
                            emergency = False
                            print("BLE: Fall detected — waiting")
                        elif value == 2:
                            emergency = True
                            fall_waiting = False
                            print("BLE: EMERGENCY")

                    await client.start_notify(FALL_CHAR_UUID, on_notify)
                    while client.is_connected:
                        await asyncio.sleep(1)

                    ble_connected = False
                    print("BLE disconnected")
            except Exception as e:
                ble_connected = False
                print(f"BLE error: {e}")
                await asyncio.sleep(3)

    loop.run_until_complete(ble_loop())


if __name__ == "__main__":
    ble_thread = threading.Thread(target=run_ble, daemon=True)
    ble_thread.start()

    print("Server running at http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, threaded=True)
