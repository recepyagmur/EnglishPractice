"""macOS (Apple Silicon) code paths, offline on any computer: the parts that differ on a Mac are run with a Mac's
outputs (sysctl, vm_stat, scutil) and folders (Google Drive, /Applications) faked in a temporary folder. It does
not replace a run on a real Mac (README: "macOS'ta kurulum"). Usage: python mac_platform_test.py"""

import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

REPO = Path(__file__).resolve().parents[2]
TMP = Path(tempfile.mkdtemp())
os.environ["EP_DATA_DIR"] = str(TMP / "data")
sys.path[:0] = [str(REPO / "app"), str(REPO)]
problems = []


def check(ok, what):
    print(("✓ " if ok else "✗ ") + what)
    if not ok:
        problems.append(what)


# --- hardware: what an M2 with 16 GB answers -----------------------------------------------------------------
from setup import hardware  # noqa: E402

VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               61234.
Pages active:                            301234.
Pages inactive:                          290001.
Pages speculative:                        12345.
Pages throttled:                              0.
"""
SYSCTL = "Apple M2\n8\n8\n17179869184\n"
free = hardware.parse_vm_stat(VM_STAT)
check(free == round((61234 + 290001 + 12345) * 16384 / 1024**3, 1), f"vm_stat → boş bellek {free} GB")
check(hardware.parse_vm_stat("garbage") is None, "vm_stat okunamazsa None")

real_run = hardware._run
hardware._run = lambda cmd, timeout=15: SYSCTL if cmd[0] == "sysctl" else VM_STAT if cmd[0] == "vm_stat" else ""
hardware.IS_MAC = True
hw = hardware.scan(TMP)
hardware.IS_MAC, hardware._run = False, real_run
check(hw["cpu"] == "Apple M2" and hw["cpu_cores"] == 8 and hw["ram_gb"] == 16.0 and hw["accel"] == "metal"
      and hw["gpu"] == "Apple M2 GPU" and hw["vram_gb"] is None and hw["gpus"][0]["shared_memory"],
      f"donanım: Apple M2, 16 GB, Metal ({hw['cpu']}, {hw['ram_gb']} GB, {hw['accel']})")

# --- model choice and Ollama settings on the Apple GPU ---------------------------------------------------------
from setup import installer  # noqa: E402
from ollama_runtime import env_for  # noqa: E402

gemma = next(m for m in installer.CATALOG["models"] if m["id"] == "gemma4:e4b")
check(installer.badge(gemma, hw, False)["level"] == "fit", "16 GB Mac'te gemma4:e4b 'uygun'")
check(installer.badge(gemma, {**hw, "ram_gb": 8.0}, False)["level"] == "no", "8 GB Mac'te önerilmez (yine seçilebilir)")
check(installer.estimated_speed(gemma, hw, "fit") is None, "Metal hızı ölçülmedi: işlemci tahmini gösterilmez")
cat = installer.catalog_for(hw, False, {})
check(next(m for m in cat if m["badge"] == "recommended")["id"] == "gemma4:e4b", "Mac'te önerilen model gemma4:e4b")
check("OLLAMA_NUM_PARALLEL" not in env_for({}, "metal") and env_for({}, "cpu").get("OLLAMA_NUM_PARALLEL") == "2",
      "Apple GPU'da tek yuva (işlemcideki gibi 2 değil)")
rec = installer.whisper_recommendation(hw)
check(rec["device"] == "cpu" and rec["model"] == "small.en", f"Whisper: {rec['model']} işlemcide")

# --- the Ollama archive: ollama at the top, libraries, symlinks, exec bit ----------------------------------------
arc = TMP / "ollama-darwin.tgz"
with tarfile.open(arc, "w:gz") as t:
    def add(name, data=b"x", mode=0o644, link=None):
        info = tarfile.TarInfo(name)
        if link:
            info.type, info.linkname = tarfile.SYMTYPE, link
            t.addfile(info)
        else:
            info.size, info.mode = len(data), mode
            t.addfile(info, io.BytesIO(data))
    add("ollama", b"#!fake", 0o755)
    add("libggml.0.27.0.dylib", b"lib", 0o755)
    add("libggml.0.dylib", link="libggml.0.27.0.dylib")
    add("mlx_metal_v4/mlx.metallib", b"metal")
    add("../escape.txt", b"no")
dest = TMP / "ollama.new"
try:
    installer.extract_tar(arc, dest, mode="r|gz")
    escaped = False
except tarfile.OutsideDestinationError:
    escaped = True
check(escaped and not (TMP / "escape.txt").exists(), "arşivden klasör dışına dosya yazılmaz (data süzgeci)")
arc2 = TMP / "ok.tgz"
with tarfile.open(arc, "r:gz") as src, tarfile.open(arc2, "w:gz") as t:
    for m in src.getmembers():
        if not m.name.startswith(".."):
            t.addfile(m, src.extractfile(m) if m.isfile() else None)
installer.extract_tar(arc2, dest, mode="r|gz")
check((dest / "ollama").read_bytes() == b"#!fake" and (dest / "mlx_metal_v4" / "mlx.metallib").exists()
      and (dest / "libggml.0.dylib").exists(), "ollama-darwin.tgz düzeni açılıyor (ollama üstte, kütüphaneler, Metal)")
check(installer.CATALOG["ollama_mac"]["url"].endswith("/ollama-darwin.tgz"), "katalogda Mac Ollama adresi")

# --- the bootstrap's Python download matches the catalog (as for Linux) -------------------------------------------
boot = (REPO / "setup" / "bootstrap.sh").read_text(encoding="utf-8")
mac_py = installer.CATALOG["python_mac"]
check(f'PY_URL="{mac_py["url"]}"' in boot and f'PY_SHA256="{mac_py["sha256"]}"' in boot
      and "aarch64-apple-darwin" in mac_py["url"], "bootstrap.sh'taki Mac Python adresi ve SHA256 katalogla aynı")
check(all(s in boot for s in ('[ "$(uname -m)" = "arm64" ]', 'sw_vers -productVersion', '-lt 14', 'shasum -a 256',
                              'xattr -dr com.apple.quarantine')),
      "bootstrap.sh: Apple Silicon, macOS 14+, shasum, karantina işareti")
bash_ok = subprocess.run(["bash", "-n"], input=boot.encode("utf-8"), capture_output=True).returncode == 0  # any bash
check(bash_ok, "bootstrap.sh sözdizimi (bash -n)")

# --- the desktop shortcut (.command) ------------------------------------------------------------------------------
text = installer.mac_launcher()
check(text.startswith("#!/bin/bash\n") and f'exec bash "{installer.ROOT_DIR / installer.script("start")}"' in text,
      "masaüstü kısayolu: English Practice.command baslat.sh'ı çalıştırır")

# --- this computer's name: the stable Local Hostname -------------------------------------------------------------
from backend import machine  # noqa: E402

real_platform, real_srun = sys.platform, machine.subprocess.run
sys.platform = "darwin"
machine.subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="Example-MacBook-Air\n", stderr="")
machine._mac_name = None
name = machine.machine_name()
machine.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(OSError("no scutil"))
machine._mac_name = None
fallback = machine.machine_name()
sys.platform, machine.subprocess.run, machine._mac_name = real_platform, real_srun, None
check(name == "Example-MacBook-Air", f"bilgisayar adı: scutil LocalHostName ({name})")
check(fallback and "." not in fallback, "scutil yoksa ağ adının ilk kısmı")

# --- Google Drive's folder on a Mac -----------------------------------------------------------------------------
from backend import sync  # noqa: E402

home = TMP / "home"
(home / "Library" / "CloudStorage" / "GoogleDrive-someone@example.com" / "My Drive").mkdir(parents=True)
real_home = Path.home
Path.home = classmethod(lambda cls: home)
sys.platform = "darwin"
suggested = sync.suggest_folder()
(home / "Library" / "CloudStorage" / "GoogleDrive-someone@example.com" / "My Drive").rmdir()
(home / "Library" / "CloudStorage" / "GoogleDrive-someone@example.com" / "Drive'ım").mkdir()
suggested_tr = sync.suggest_folder()
sys.platform = real_platform
check(suggested and Path(suggested).parts[-3:] == ("GoogleDrive-someone@example.com", "My Drive", "EnglishPractice"),
      "Drive klasörü önerisi: ~/Library/CloudStorage/GoogleDrive-…/My Drive/EnglishPractice")
check(suggested_tr and Path(suggested_tr).parts[-2] == "Drive'ım", "Türkçe Drive klasörü (Drive'ım) da bulunur")

# --- the app window: Chrome's program inside its .app -----------------------------------------------------------
import launcher  # noqa: E402

chrome = home / "Applications" / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome"
chrome.parent.mkdir(parents=True)
chrome.write_text("")
launcher.IS_MAC = True
found = launcher._app_browser()
chrome.unlink()
none_found = launcher._app_browser()
launcher.IS_MAC = False
Path.home = real_home
check(found == str(chrome), "uygulama penceresi: ~/Applications/Google Chrome.app bulunur")
check(none_found is None or none_found.startswith("/Applications"), "Chrome yoksa varsayılan tarayıcı (Safari: sekme)")

# --- Whisper: int8, then float32 if a CPU has no int8 ----------------------------------------------------------
from backend import stt  # noqa: E402

s = stt.SpeechToText()
tried = []


def fake_create(name, dev, compute):
    tried.append((dev, compute))
    if compute == "int8":
        raise ValueError("int8 not supported")
    return object()


s._create, s._warm_up = fake_create, lambda m: None
s.load("small.en", "cpu")
check(s.state == "ready" and tried == [("cpu", "int8"), ("cpu", "float32")] and "GPU kullanılamadı" not in s.message,
      f"Whisper işlemcide int8 olmazsa float32 ({s.message})")

print("Sorun yok ✓" if not problems else f"{len(problems)} sorun")
sys.exit(1 if problems else 0)
