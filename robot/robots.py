"""Links to the robot. Each has the same interface: drive(left, right), send(b"o"/b"p"/b"<l,r>"),
close(), and .ser (truthy while connected).

  RouterRobot  running ON the UNO Q: talks to its MCU through the board's router socket
  NetRobot     on the Mac: talks to the UNO Q app (robot/unoq_robot) over TCP
  UsbRobot     on the Mac: a classic Uno/Nano over USB serial
"""
import glob
import os
import socket
import time

import follow_config as cfg


def make_robot(args):
    """Pick the link from the command-line options."""
    if args.robot_router:
        return RouterRobot(args.robot_router)
    if args.robot_net:
        return NetRobot(args.robot_net)
    return UsbRobot(args.port)


class RouterRobot:
    """Running ON the UNO Q: call the MCU's drive()/arms() (robot/unoq_robot/sketch) directly through
    the board's router socket, the same msgpack-RPC the App Lab Python Bridge uses. Fire-and-forget
    notifications, so a slow reply never holds up the control loop."""

    SOCKET = "/var/run/arduino-router.sock"

    def __init__(self, address="local"):
        """address: "local" (running on the UNO Q) or "host:port" (from the Mac, through
        `adb forward tcp:5006 localfilesystem:/var/run/arduino-router.sock`)."""
        import msgpack
        self.msgpack = msgpack
        self.address = address
        self.ser = None          # the socket; named like Robot.ser so the control loop can check the link
        self.next_try = 0.0

    def _open(self):
        if self.ser or time.monotonic() < self.next_try:
            return self.ser
        try:
            if self.address == "local":
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(self.SOCKET)
            else:
                host, port = self.address.rsplit(":", 1)
                s = socket.create_connection((host, int(port)), timeout=1.0)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.setblocking(False)  # replies to notifications don't come; anything else is ignored
            self.ser = s
            print(f"Robot connected: UNO Q MCU via {self.SOCKET if self.address == 'local' else self.address}")
        except OSError as e:
            print(f"Robot router not available ({e}), retrying...")
            self.next_try = time.monotonic() + 2
        return self.ser

    def _notify(self, method, *params):
        if not self._open():
            return
        try:
            self.ser.sendall(self.msgpack.packb([2, method, list(params)]))
            try:
                self.ser.recv(4096)   # drain anything the router sends back
            except BlockingIOError:
                pass
        except OSError as e:
            print(f"Robot router link lost ({e}), reconnecting...")
            self.ser.close()
            self.ser = None
            self.next_try = time.monotonic() + 1

    def drive(self, left, right):
        if cfg.MOTORS_SWAPPED:
            left, right = right, left
        self._notify("drive", int(left), int(right))

    def send(self, data):
        """Same interface as the serial robot: b"o"/b"p" = arms up/down, b"<l,r>" = motors."""
        msg = data.decode(errors="ignore").strip()
        if msg in ("o", "p"):
            self._notify("arms", 150 if msg == "o" else 30)
        elif msg.startswith("<") and msg.endswith(">"):
            left, right = (int(v) for v in msg[1:-1].split(","))
            self._notify("drive", left, right)

    def close(self):
        if self.ser:
            self._notify("drive", 0, 0)
        if self.ser:
            self.ser.close()


class NetRobot:
    """Robot on an Arduino UNO Q: frames go over TCP to robot/unoq_robot/python/main.py, which hands
    them to the MCU. Over the USB cable use `adb forward tcp:5005 tcp:5005` and localhost; over
    Wi-Fi use the board's name. Reconnects by itself if the link drops."""

    def __init__(self, target):
        # "host", "host:port", "[ipv6]:port" or a bare IPv6 address
        if target.startswith("[") and "]:" in target:
            host, port = target[1:].split("]:")
        elif target.count(":") == 1:
            host, port = target.split(":")
        else:
            host, port = target.strip("[]"), "5005"
        self.host, self.port = host, int(port)
        self.ser = None          # the socket; named like Robot.ser so the control loop can check the link
        self.next_try = 0.0

    def _open(self):
        if self.ser or time.monotonic() < self.next_try:
            return self.ser
        try:
            s = socket.create_connection((self.host, self.port), timeout=1.0)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.settimeout(0.2)
            self.ser = s
            print(f"Robot connected: UNO Q at {self.host}:{self.port}")
        except OSError as e:
            print(f"Robot (UNO Q) not reachable at {self.host}:{self.port} ({e}), retrying...")
            self.next_try = time.monotonic() + 2
        return self.ser

    def send(self, data):
        if not self._open():
            return
        try:
            self.ser.sendall(data.rstrip(b"\n") + b"\n")
        except OSError as e:
            print(f"Robot link lost ({e}), reconnecting...")
            self.ser.close()
            self.ser = None
            self.next_try = time.monotonic() + 1

    def drive(self, left, right):
        if cfg.MOTORS_SWAPPED:
            left, right = right, left
        self.send(f"<{left},{right}>".encode())

    def close(self):
        if self.ser:
            self.send(b"<0,0>")
        if self.ser:   # send() drops the socket if the link just failed
            self.ser.close()


class UsbRobot:
    """Serial link to the Uno that reopens itself if the USB drops (cable tug, motor brownout)."""

    def __init__(self, port):
        self.port = port
        self.ser = None
        self.next_try = 0.0
        self.rx_buf = b""

    def _open(self):
        if self.ser or time.monotonic() < self.next_try:
            return self.ser
        port = self.port
        if not os.path.exists(port):
            # Plugged into a different USB socket = different name; take any USB-serial adapter
            found = sorted(glob.glob("/dev/cu.usbserial-*") + glob.glob("/dev/cu.wchusbserial*"))
            if found:
                port = found[0]
        try:
            import serial   # only needed for a USB robot (not installed on the UNO Q)
            self.ser = serial.Serial(port, 9600, timeout=0.1)
            time.sleep(2)   # opening the port resets the Uno
            print(f"Robot connected on {port}")
        except OSError as e:   # serial.SerialException is an OSError
            print(f"Robot not available ({e}), retrying...")
            self.next_try = time.monotonic() + 2
        return self.ser

    def _drop(self, e):
        print(f"Robot USB lost ({e}), reconnecting...")
        try:
            self.ser.close()
        except Exception:
            pass
        self.ser = None
        self.next_try = time.monotonic() + 1

    def send(self, data):
        if not self._open():
            return
        try:
            self.ser.write(data)
            # Read whatever has arrived without waiting for a full line (readline could block 100 ms)
            if self.ser.in_waiting:
                self.rx_buf += self.ser.read(self.ser.in_waiting)
                *lines, self.rx_buf = self.rx_buf.split(b"\n")
                for line in lines:
                    line = line.decode(errors="ignore").strip()
                    if line:
                        print(f"robot: {line}")
        except OSError as e:
            self._drop(e)

    def drive(self, left, right):
        if cfg.MOTORS_SWAPPED:
            left, right = right, left
        self.send(f"<{left},{right}>".encode())

    def close(self):
        if self.ser:
            try:
                self.ser.write(b"<0,0>s")
                self.ser.close()
            except Exception:
                pass
