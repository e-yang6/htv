import cv2
import asyncio
import threading
from ultralytics import YOLO

# --- BLE config ---
ARDUINO_NAME = "FallDetector"
FALL_CHAR_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214"
FALL_SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214"

# --- State ---
emergency = False
fall_waiting = False
ble_connected = False

model = YOLO("yolov8n.pt")

def find_nearest_person(results, frame_width):
    """Find the person closest to center with the largest bounding box (closest to camera)."""
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
            # Score: bigger box = closer person, bonus for being centered
            center_dist = abs(center_x - frame_width / 2) / frame_width
            score = area * (1 - 0.3 * center_dist)
            if score > best_score:
                best_score = score
                best = (int(x1), int(y1), int(x2), int(y2), center_x)

    return best


def get_direction(person_center_x, frame_width):
    """Return direction the robot should move to face the person."""
    third = frame_width / 3
    if person_center_x < third:
        return "LEFT"
    elif person_center_x > third * 2:
        return "RIGHT"
    else:
        return "FORWARD"


def run_camera():
    global emergency, fall_waiting

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Cannot open camera")
        return

    print("Camera running. Press 'q' to quit, 'e' to simulate emergency, 'r' to reset.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_width = frame.shape[1]

        # Run YOLO person detection
        results = model(frame, classes=[0], verbose=False)

        # Draw all detected people
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                conf = float(box.conf[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"person {conf:.0%}", (x1, y1 - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Status bar
        if emergency:
            status = "EMERGENCY — Seeking nearest person"
            color = (0, 0, 255)
        elif fall_waiting:
            status = "Fall detected — Waiting for response..."
            color = (0, 165, 255)
        else:
            status = "Monitoring" + (" | BLE connected" if ble_connected else " | BLE disconnected")
            color = (0, 200, 0) if ble_connected else (128, 128, 128)

        cv2.rectangle(frame, (0, 0), (frame_width, 40), (0, 0, 0), -1)
        cv2.putText(frame, status, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        # If emergency, highlight nearest person and show direction
        if emergency:
            person = find_nearest_person(results, frame_width)
            if person:
                x1, y1, x2, y2, cx = person
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 4)
                direction = get_direction(cx, frame_width)
                cv2.putText(frame, f"TARGET — {direction}", (x1, y1 - 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                # TODO: send direction command to robot
                # serial_port.write(direction.encode())
            else:
                cv2.putText(frame, "NO PERSON FOUND — SCANNING", (10, 70),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        cv2.imshow("Fall Detector — Person Detection", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('e'):
            emergency = True
            fall_waiting = False
            print("SIMULATED EMERGENCY")
        elif key == ord('r'):
            emergency = False
            fall_waiting = False
            print("Reset to monitoring")

    cap.release()
    cv2.destroyAllWindows()


async def run_ble():
    global emergency, fall_waiting, ble_connected

    try:
        from bleak import BleakClient, BleakScanner
    except ImportError:
        print("BLE disabled — install bleak: pip install bleak")
        return

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
                        print("BLE: Status normal")
                    elif value == 1:
                        fall_waiting = True
                        emergency = False
                        print("BLE: Fall detected — waiting for response")
                    elif value == 2:
                        emergency = True
                        fall_waiting = False
                        print("BLE: EMERGENCY — deploying robot!")

                await client.start_notify(FALL_CHAR_UUID, on_notify)

                while client.is_connected:
                    await asyncio.sleep(1)

                ble_connected = False
                print("BLE disconnected")
        except Exception as e:
            ble_connected = False
            print(f"BLE error: {e}, retrying in 3s...")
            await asyncio.sleep(3)


def start_ble_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_ble())


if __name__ == "__main__":
    # Start BLE listener in background thread
    ble_thread = threading.Thread(target=start_ble_thread, daemon=True)
    ble_thread.start()

    # Run camera + detection on main thread (OpenCV needs main thread)
    run_camera()
