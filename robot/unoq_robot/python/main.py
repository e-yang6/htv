"""UNO Q Linux side: receive motor commands from the Mac and hand them to the MCU.

The Mac runs robot/follow_bridge.py --robot-net <host[:port]>. It connects over TCP to
port 5005 and sends the same frames the old USB Uno got, one per line:
    <left,right>   motors, 0-255 each, ~20 per second
    o / p          arms up / down
Over the USB cable: on the Mac, `adb forward tcp:5005 tcp:5005`, then --robot-net localhost.
Over Wi-Fi: --robot-net <board>.local.
Only the newest motor frame is forwarded each time round, so a burst of late packets
never queues up and makes the robot lag.
"""
import socket
import time

from arduino.app_utils import App, Bridge

PORT = 5005
ARM_UP, ARM_DOWN = 150, 30

server = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
server.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("::", PORT))
server.listen(1)
server.setblocking(False)   # polled every loop for new connections
print(f"Listening for robot commands on TCP {PORT}")

client = None
buf = b""


def stop_motors():
    try:
        Bridge.call("drive", 0, 0)
    except Exception:
        pass


def loop():
    global client, buf
    # Always take a new connection, dropping the old one: a Mac that went away without closing
    # (killed, cable pulled) would otherwise block every reconnect
    try:
        new, addr = server.accept()
    except (socket.timeout, BlockingIOError):
        new = None
    if new:
        if client:
            client.close()
            print("Replacing stale connection")
        client = new
        client.settimeout(0.05)
        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        buf = b""
        print(f"Mac connected from {addr[0]}")
    if client is None:
        time.sleep(0.02)
        return
    try:
        data = client.recv(4096)
    except socket.timeout:
        return
    except OSError:
        data = b""
    if not data:
        print("Mac disconnected, motors stopped")
        client.close()
        client = None
        stop_motors()
        return

    buf += data
    *lines, buf = buf.split(b"\n")
    frame = None
    for line in lines:
        msg = line.decode(errors="ignore").strip()
        if msg.startswith("<") and msg.endswith(">"):
            frame = msg
        elif msg == "rx?":   # diagnostics: what the MCU has received on D0
            print(f"MCU has received {Bridge.call('rx_count')} bytes on D0")
            text = Bridge.call("rx_text")
            for t in str(text).replace("\r", "").split("\n"):
                if t.strip():
                    print(f"  D0 says: {t.strip()}")
        elif msg in ("o", "p"):
            Bridge.call("arms", ARM_UP if msg == "o" else ARM_DOWN)
    if frame:
        try:
            left, right = (int(v) for v in frame[1:-1].split(","))
        except ValueError:
            return
        global drives
        ok = Bridge.call("drive", left, right)
        drives += 1
        if drives <= 3 or (drives % 100 == 0) or (left or right) and not ok:
            print(f"drive({left},{right}) -> MCU replied {ok!r} (#{drives})")


drives = 0
App.run(user_loop=loop)
