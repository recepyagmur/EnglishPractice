"""Migrate a first-version install into the portable layout.

1. Backs up the user database and verifies row counts (data/app.db).
2. Moves hardware settings (LLM / Whisper model) from the DB into this computer's profile.
3. Copies models a system-wide Ollama already downloaded into models/ollama
   (copy, never move — the system Ollama keeps working).

Usage:  runtime\\python\\python.exe -m setup.migrate [--models qwen3:8b ...] [--yes]
"""

import argparse
import sqlite3
import sys

from backend import backup, machine
from backend.config import DB_PATH, OLLAMA_MODELS_DIR, ROOT_DIR

from . import hardware, ollama_models

# Files of the first version that are replaced by the portable layout.
LEGACY_PATHS = ["start.bat", ".venv"]


def migrate_database() -> None:
    if not DB_PATH.exists():
        print("Veritabanı yok, geçiş gerekmiyor.")
        return
    before = backup.row_counts()
    saved = backup.backup_now("pre-migration")
    after = backup.row_counts(saved)
    print(f"Yedek alındı: {saved.relative_to(ROOT_DIR)}")
    for table, count in before.items():
        mark = "✓" if after[table] == count else "✗"
        print(f"  {mark} {table:<12} {count:>6} kayıt")
    if before != after:
        sys.exit("HATA: Yedekteki kayıt sayıları farklı! Geçiş durduruldu.")


def migrate_machine_settings() -> dict:
    profile = machine.load_profile()
    legacy = {}
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        legacy = dict(conn.execute(
            "SELECT key, value FROM settings WHERE key IN ('llm_model', 'whisper_model')"
        ).fetchall())
        conn.close()

    if not profile:
        print("Bilgisayar taranıyor…")
        hw = hardware.scan(ROOT_DIR)
        profile = {
            "machine_name": machine.machine_name(),
            "detected": {k: hw[k] for k in ("cpu", "ram_gb", "gpu", "vram_gb", "accel")},
            "default_model": legacy.get("llm_model", "qwen3:8b"),
            "whisper_model": legacy.get("whisper_model", "small.en"),
            "whisper_device": "cuda" if hw["accel"] == "cuda" else "cpu",
            "benchmarks": {},
        }
        machine.save_profile(profile)
        print(f"Bilgisayar profili oluşturuldu: config/machines/{machine.machine_name()}.json")
    return profile


def migrate_models(names: list[str], assume_yes: bool) -> None:
    sources = ollama_models.system_model_dirs(exclude=OLLAMA_MODELS_DIR)
    for name in names:
        if ollama_models.has_model(OLLAMA_MODELS_DIR, name):
            print(f"{name}: uygulama klasöründe zaten var ✓")
            continue
        src = next((d for d in sources if ollama_models.has_model(d, name)), None)
        if src is None:
            print(f"{name}: sistemde bulunamadı, kurulumda indirilecek.")
            continue
        size_gb = ollama_models.model_size(src, name) / 1024**3
        if not assume_yes:
            answer = input(f"{name} ({size_gb:.1f} GB) bilgisayarında zaten var ({src}). "
                           "Uygulama klasörüne kopyalayayım mı? [E/h] ").strip().lower()
            if answer not in ("", "e", "evet", "y", "yes"):
                continue

        def show(done: int, total: int) -> None:
            print(f"\r  {name}: {done / 1024**3:5.1f} / {total / 1024**3:.1f} GB", end="", flush=True)

        ollama_models.copy_model(name, src, OLLAMA_MODELS_DIR, show)
        print(f"\n{name}: kopyalandı ✓ (sistem Ollama'sındaki kopya yerinde duruyor)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", help="Kopyalanacak modeller (varsayılan: profildeki model)")
    parser.add_argument("--yes", action="store_true", help="Sormadan kopyala")
    args = parser.parse_args()

    migrate_database()
    profile = migrate_machine_settings()
    migrate_models(args.models or [profile["default_model"]], args.yes)

    leftovers = [p for p in LEGACY_PATHS if (ROOT_DIR / p).exists()]
    if leftovers:
        print("Artık kullanılmayan eski dosyalar (silinebilir): " + ", ".join(leftovers))


if __name__ == "__main__":
    main()
