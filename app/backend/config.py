import os
from pathlib import Path

# <root>/app/backend/config.py
APP_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = APP_DIR.parent
FRONTEND_DIR = APP_DIR / "frontend"

# Windows and Linux. The folder layout is the same; only the bundled programs and the start scripts differ.
IS_WINDOWS = os.name == "nt"

RUNTIME_DIR = ROOT_DIR / "runtime"
# Windows: Ollama's zip has ollama.exe at the top; Linux: its tarball has bin/ollama and lib/ollama.
OLLAMA_EXE = RUNTIME_DIR / "ollama" / ("ollama.exe" if IS_WINDOWS else "bin/ollama")
PYTHON_EXE = RUNTIME_DIR / "python" / ("python.exe" if IS_WINDOWS else "bin/python3")
MODELS_DIR = ROOT_DIR / "models"
OLLAMA_MODELS_DIR = MODELS_DIR / "ollama"
STT_MODELS_DIR = MODELS_DIR / "stt"
TTS_MODELS_DIR = MODELS_DIR / "tts"
# EP_DATA_DIR: run against another data folder (development / tests).
DATA_DIR = Path(os.environ.get("EP_DATA_DIR") or ROOT_DIR / "data")
DB_PATH = DATA_DIR / "app.db"
BACKUP_DIR = DATA_DIR / "backups"
LOCK_PATH = DATA_DIR / ".lock"
MACHINES_DIR = ROOT_DIR / "config" / "machines"
LOGS_DIR = ROOT_DIR / "logs"
SETUP_DIR = ROOT_DIR / "setup"


# The learner starts the app with these (messages name the right one for this computer).
SCRIPTS = ({"setup": "Kurulum.bat", "start": "Baslat.bat", "update": "Guncelle.bat"} if IS_WINDOWS
           else {"setup": "kurulum.sh", "start": "baslat.sh", "update": "guncelle.sh"})


def script(name: str) -> str:
    """'Baslat.bat' on Windows, 'baslat.sh' on Linux (name: setup | start | update)."""
    return SCRIPTS[name]


def ollama_url() -> str:
    # The launcher sets OLLAMA_HOST to the port of the bundled Ollama it started,
    # so read it at call time rather than import time.
    host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434").strip()
    if not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    return host.replace("0.0.0.0", "127.0.0.1").rstrip("/")


OLLAMA_KEEP_ALIVE = "30m"
OLLAMA_NUM_CTX = 4096

# How many previous messages of a session are sent to the LLM as context.
CHAT_HISTORY_LIMIT = 20

# Personal settings: belong to the user, stored in data/app.db, shared by all machines.
DEFAULT_SETTINGS = {
    "level": "B1",
    "level_confirmed": "0",  # "1" once the learner picked a level (first-run question)
    "correction_mode": "every",  # every | end | off
    "explanation_language": "tr",  # tr | en
    "tts_accent": "a",  # a = American, b = British
    "tts_voice": "af_heart",
    "tts_speed": "1.0",
    "reply_length": "short",  # short | medium
    "interests": "",
    "talk_button_mode": "hold",  # hold | toggle
    "theme": "dark",
}

# Hardware-dependent settings: stored in config/machines/<computer>.json.
# Maps the settings-API key to the machine-profile key.
MACHINE_SETTINGS = {
    "llm_model": "default_model",
    "whisper_model": "whisper_model",
}

for _d in (DATA_DIR, BACKUP_DIR, MACHINES_DIR, LOGS_DIR, OLLAMA_MODELS_DIR, STT_MODELS_DIR, TTS_MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
