"""Per-computer profile: config/machines/<COMPUTERNAME>.json.

Holds everything that depends on the hardware (default LLM, Whisper model and
device, benchmarks), so the same folder can be used on several computers.
"""

import json
import os
import socket
import subprocess
import sys
import threading

from .config import MACHINES_DIR

_lock = threading.Lock()


_mac_name: str | None = None


def machine_name() -> str:
    """This computer's name (its profile file, and the name the other computer sees in the sync).
    macOS: the "Local Hostname" (System Settings → Sharing), which stays the same; the network host name there
    changes with the network (e.g. 192-168-1-5.home)."""
    global _mac_name
    if sys.platform == "darwin":
        if _mac_name is None:
            try:
                out = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True,
                                     timeout=5).stdout.strip()
            except (OSError, subprocess.TimeoutExpired):
                out = ""
            _mac_name = out or socket.gethostname().split(".")[0]
        return _mac_name
    return os.environ.get("COMPUTERNAME") or socket.gethostname()


def profile_path():
    return MACHINES_DIR / f"{machine_name()}.json"


def profile_exists() -> bool:
    return profile_path().exists()


def load_profile() -> dict:
    try:
        return json.loads(profile_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def save_profile(profile: dict) -> None:
    with _lock:
        path = profile_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


def update_profile(changes: dict) -> dict:
    profile = load_profile()
    profile.update(changes)
    save_profile(profile)
    return profile
