"""Find the iPhone's Continuity Camera among the Mac's cameras.

OpenCV numbers cameras by an internal ID, so the iPhone is sometimes camera 0 and sometimes 1
(and the MacBook's own camera takes the other number). find_camera() looks the cameras up by name
(list_cameras.swift, compiled once into ~/.cache/htv) and returns the iPhone's OpenCV index.
"""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SWIFT_SRC = os.path.join(HERE, "list_cameras.swift")
BINARY = os.path.expanduser("~/.cache/htv/list_cameras")
# The iPhone shows up as "<phone's name> Camera" (e.g. "ye Camera"), so rather than look for "iPhone",
# skip the Mac's own cameras and take what's left
MAC_CAMERAS = ("macbook", "facetime", "desk view", "capture screen", "studio display")


def list_cameras():
    """[(opencv_index, name)], or None if the cameras can't be listed (no Swift compiler)."""
    try:
        if not os.path.exists(BINARY) or os.path.getmtime(BINARY) < os.path.getmtime(SWIFT_SRC):
            os.makedirs(os.path.dirname(BINARY), exist_ok=True)
            subprocess.run(["swiftc", "-O", "-o", BINARY, SWIFT_SRC], check=True,
                           capture_output=True, timeout=180)
        out = subprocess.run([BINARY], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    cams = []
    for line in out.splitlines():
        idx, _, name = line.partition("\t")
        if idx.isdigit():
            cams.append((int(idx), name))
    return cams


def find_camera():
    """OpenCV index of the iPhone camera (an "iPhone" camera, else any camera that isn't the Mac's own),
    or None if it isn't connected right now."""
    cams = list_cameras()
    if cams is None:
        return None
    others = [(idx, name) for idx, name in cams if not any(m in name.lower() for m in MAC_CAMERAS)]
    for idx, name in others:
        if "iphone" in name.lower():
            return idx
    return others[0][0] if others else None


if __name__ == "__main__":
    print(list_cameras())
    print("iPhone camera index:", find_camera())
