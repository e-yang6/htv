"""Saved robot calibration (turn rate, speed) in turn_rate.json, shared by follow_bridge.py and seeker.py.

Kept separate from seeker.py so the bridge can run without OpenCV/YOLO (e.g. on the UNO Q).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TURN_RATE_FILE = os.path.join(HERE, "turn_rate.json")


def save_calibration(**values):
    """Merge values into turn_rate.json."""
    try:
        with open(TURN_RATE_FILE) as f:
            cal = json.load(f)
    except (OSError, ValueError):
        cal = {}
    cal.update(values)
    with open(TURN_RATE_FILE, "w") as f:
        json.dump(cal, f)


def load_speed(default_mps):
    try:
        with open(TURN_RATE_FILE) as f:
            return float(json.load(f)["speed_mps"])
    except (OSError, ValueError, KeyError):
        return default_mps


def load_calibration(default_rate):
    """Turn rate (deg/s) from --calibrate-turn."""
    try:
        with open(TURN_RATE_FILE) as f:
            return float(json.load(f)["turn_rate_dps"])
    except (OSError, ValueError, KeyError):
        return default_rate


def load_side_rates():
    """(left deg/s, right deg/s) measured with --spin-left / --spin-right, or None for each."""
    try:
        with open(TURN_RATE_FILE) as f:
            cal = json.load(f)
        return cal.get("turn_left_dps"), cal.get("turn_right_dps")
    except (OSError, ValueError):
        return None, None
