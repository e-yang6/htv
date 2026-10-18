"""The host's (wearer's) medical condition (plus, for a condition typed in by hand, a description
and the steps a helper should follow), set in the dashboard's onboarding terminal, and spoken
emergency messages. Shared by dashboard.py (the API and the alert) and seeker.py (the robot asking a
bystander for help). Stored in host_profile.json next to this file.
"""
import json
import os
import platform
import subprocess
import threading
import time

HOST_PROFILE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "host_profile.json")


def get_host_condition(default="an urgent medical condition"):
    """The condition saved during onboarding, or `default` if none is set."""
    try:
        with open(HOST_PROFILE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("condition") or default
    except (OSError, ValueError):
        return default


def get_host_profile():
    """{"condition", "description", "steps"} as saved (empty values if nothing is saved)."""
    try:
        with open(HOST_PROFILE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    return {"condition": data.get("condition") or "", "description": data.get("description") or "",
            "steps": [s for s in data.get("steps") or [] if isinstance(s, str) and s.strip()]}


def save_host_condition(condition, description="", steps=None):
    with open(HOST_PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump({"condition": condition, "description": description, "steps": steps or [],
                   "updated_at": time.time()}, f, indent=2)


def speak_emergency(text):
    """Say `text` out loud (Mac `say`, Linux `espeak`, Windows speech), without blocking."""
    def _run():
        sys_plat = platform.system()
        try:
            if sys_plat == "Darwin":
                subprocess.run(["say", text], check=False)
            elif sys_plat == "Linux":
                subprocess.run(["espeak", text], check=False)
            elif sys_plat == "Windows":
                escaped = text.replace("'", "''")
                ps = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{escaped}')"
                subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)
        except Exception as e:
            print(f"[TTS Error] {e}")
    threading.Thread(target=_run, daemon=True).start()
