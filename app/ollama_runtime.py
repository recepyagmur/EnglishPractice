"""Run the bundled Ollama (runtime/ollama) as a child process.

Shared by the launcher (the app) and the setup wizard. Only the standard library
is used, so it works before the Python packages are installed.
"""

import ctypes
import os
import shutil
import signal
import socket
import subprocess
import threading
import time
import urllib.request
from datetime import datetime

from backend.config import IS_WINDOWS, LOGS_DIR, OLLAMA_EXE, OLLAMA_MODELS_DIR

if IS_WINDOWS:
    from ctypes import wintypes

# Ports Windows may have reserved (or another program uses) are skipped automatically (see README, ports).
OLLAMA_PORTS = (11435, 11535, 11635, 11735, 12345, 13435)
OLLAMA_LOG_MAX_BYTES = 10 * 1024 * 1024


def can_bind(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def pick_port(preferred: tuple[int, ...]) -> int:
    for port in preferred:
        if can_bind(port):
            return port
    with socket.socket() as s:  # let Windows choose one that is not reserved
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http_ok(url: str, timeout: float = 2) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except OSError:
        return False


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if not IS_WINDOWS:
        try:
            os.kill(pid, 0)  # signal 0: only checks that the process exists
        except ProcessLookupError:
            return False
        except PermissionError:  # exists, owned by someone else
            return True
        return True
    PROCESS_QUERY_LIMITED_INFORMATION, STILL_ACTIVE = 0x1000, 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    code = wintypes.DWORD()
    kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel32.CloseHandle(handle)
    return code.value == STILL_ACTIVE


def env_for(profile: dict, accel: str | None = None) -> dict:
    """Ollama settings for this computer: the profile's own (e.g. OLLAMA_VULKAN=0) plus defaults.
    Without an NVIDIA GPU the model runs on the CPU, which reads a long prompt slowly (~35 tokens/s):
    two slots let chat and corrections each keep their prompt cached instead of evicting each other
    (measured on the CPU: a correction 20 s → 10 s, and the chat history is not read again every turn)."""
    env = {k: str(v) for k, v in (profile.get("ollama_env") or {}).items()}
    if (accel or (profile.get("detected") or {}).get("accel")) != "cuda":
        env.setdefault("OLLAMA_NUM_PARALLEL", "2")
    return env


# ------------------------------------------- unused GPU libraries (disk)

# Windows: runtime/ollama/lib/ollama; Linux: runtime/ollama/bin/ollama → runtime/ollama/lib/ollama.
LIB_DIR = (OLLAMA_EXE.parent if IS_WINDOWS else OLLAMA_EXE.parent.parent) / "lib" / "ollama"


def has_amd_gpu(gpu_names) -> bool:
    """A discrete AMD card that ROCm can use (Radeon RX / PRO). Integrated Radeon graphics
    ("AMD Radeon(TM) Graphics", "Radeon 780M") are not supported by ROCm: Vulkan or the CPU runs there."""
    for n in gpu_names:
        name = (n or "").lower()
        if ("amd" in name or "radeon" in name) and (" rx " in f" {name} " or "radeon pro" in name or " w7" in name):
            return True
    return False


def prune_gpu_libs(gpu_names) -> int:
    """Ollama ships ROCm libraries for AMD cards (~1 GB). Remove them on a computer without
    an AMD GPU; the setup wizard puts them back on one that has one. Returns bytes freed."""
    if has_amd_gpu(gpu_names):
        return 0
    freed = 0
    for d in LIB_DIR.glob("rocm*"):
        if d.is_dir():
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            try:
                shutil.rmtree(d)
                freed += size
            except OSError:
                pass  # in use: try again next start
    return freed


def missing_gpu_libs(gpu_names) -> bool:
    """An AMD GPU but the ROCm libraries were removed on another computer."""
    return OLLAMA_EXE.exists() and has_amd_gpu(gpu_names) and not any(LIB_DIR.glob("rocm*"))


# ------------------------------------------------- kill children on exit

if IS_WINDOWS:
    class _IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimits),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]


_jobs = []  # job handles stay open until this process exits


def _die_with_parent() -> None:
    """Linux, in the child before exec: get SIGTERM when the process that started us dies (also when it is
    killed or crashes). Ollama then stops its runners itself."""
    PR_SET_PDEATHSIG = 1
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
    except OSError:
        pass


def popen_options() -> dict:
    """How to start a background program: no console window on Windows; on Linux, tied to this process.
    (Linux sends the signal when the *thread* that started the child ends, so only from the main thread —
    the setup wizard starts Ollama from worker threads; there Ctrl+C / closing the terminal still stops it,
    as the terminal signals the whole process group.)"""
    if IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    if threading.current_thread() is threading.main_thread():
        return {"preexec_fn": _die_with_parent}
    return {}


def kill_with_this_process(proc: subprocess.Popen) -> None:
    """Windows: put proc (and its llama-server children) in a job that dies with this process,
    even if the console window is closed or Python crashes. (Linux: popen_options.)"""
    if not IS_WINDOWS:
        return
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, JobObjectExtendedLimitInformation = 0x2000, 9
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

    job = kernel32.CreateJobObjectW(None, None)
    info = _ExtendedLimits()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    kernel32.SetInformationJobObject(job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info))
    kernel32.AssignProcessToJobObject(job, int(proc._handle))
    _jobs.append(job)


# ------------------------------------------------------------------ ollama

class OllamaProcess:
    """The bundled `ollama serve` on a free local port."""

    def __init__(self, env: dict | None = None, log_name: str = "ollama.log") -> None:
        self.extra_env = {k: str(v) for k, v in (env or {}).items()}
        self.log_path = LOGS_DIR / log_name
        self.port: int | None = None
        self.proc: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def host(self) -> str:
        return f"127.0.0.1:{self.port}"

    def start(self, timeout: float = 60) -> bool:
        """Start and wait until it answers. Returns False if it did not come up."""
        if not OLLAMA_EXE.exists():
            return False
        self.port = pick_port(OLLAMA_PORTS)
        if self.log_path.exists() and self.log_path.stat().st_size > OLLAMA_LOG_MAX_BYTES:
            try:
                self.log_path.replace(self.log_path.with_suffix(".old.log"))
            except OSError:  # still held by an Ollama that is closing: keep appending, rotate next time
                pass
        env = dict(os.environ)
        env.update({"OLLAMA_HOST": self.host, "OLLAMA_MODELS": str(OLLAMA_MODELS_DIR)})
        env.update(self.extra_env)  # per-machine overrides, e.g. OLLAMA_VULKAN=0
        log_file = open(self.log_path, "a", encoding="utf-8")
        log_file.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} port {self.port} {self.extra_env} =====\n")
        log_file.flush()
        self.proc = subprocess.Popen(
            [str(OLLAMA_EXE), "serve"], env=env, cwd=OLLAMA_EXE.parent,
            stdout=log_file, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **popen_options(),
        )
        kill_with_this_process(self.proc)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                return False
            if http_ok(f"{self.url}/api/version"):
                return True
            time.sleep(0.3)
        return False

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def running(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)
