from . import machine
from .config import DEFAULT_SETTINGS, MACHINE_SETTINGS
from .db import get_conn

MACHINE_DEFAULTS = {"llm_model": "gemma4:e4b", "whisper_model": "small.en"}


def get_level() -> str:
    """The learner's CEFR level. The one place every module (chat, corrections,
    writing, lessons…) reads it from."""
    return get_settings()["level"]


def get_settings() -> dict:
    """Personal settings from the DB merged with this computer's profile."""
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    stored = {r["key"]: r["value"] for r in rows}
    settings = {key: stored.get(key, default) for key, default in DEFAULT_SETTINGS.items()}

    profile = machine.load_profile()
    for key, profile_key in MACHINE_SETTINGS.items():
        settings[key] = profile.get(profile_key) or MACHINE_DEFAULTS[key]
    return settings


def update_settings(changes: dict) -> dict:
    machine_changes = {
        MACHINE_SETTINGS[k]: str(v) for k, v in changes.items() if k in MACHINE_SETTINGS
    }
    if machine_changes:
        machine.update_profile(machine_changes)

    with get_conn() as conn:
        for key, value in changes.items():
            if key not in DEFAULT_SETTINGS:
                continue
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )
    return get_settings()
