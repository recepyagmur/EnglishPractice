"""Detect CPU, RAM, GPU/VRAM and disk space (Windows and Linux)."""

import ctypes
import json
import os
import shutil
import subprocess
from pathlib import Path

IS_WINDOWS = os.name == "nt"
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0  # CREATE_NO_WINDOW (Windows only)


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _ram_gb() -> tuple[float, float]:
    if not IS_WINDOWS:
        info = _meminfo()
        return round(info.get("MemTotal", 0) / 1024**2, 1), round(info.get("MemAvailable", 0) / 1024**2, 1)
    stat = _MemoryStatus()
    stat.dwLength = ctypes.sizeof(stat)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    return round(stat.ullTotalPhys / 1024**3, 1), round(stat.ullAvailPhys / 1024**3, 1)


def _run(cmd: list[str], timeout: float = 15) -> str:
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW
        )
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _nvidia_smi() -> str:
    """nvidia-smi from the PATH; under WSL it lives in /usr/lib/wsl/lib, which is not always on the PATH."""
    if shutil.which("nvidia-smi") or IS_WINDOWS:
        return "nvidia-smi"
    wsl = Path("/usr/lib/wsl/lib/nvidia-smi")
    return str(wsl) if wsl.exists() else "nvidia-smi"


def _nvidia_gpus() -> list[dict]:
    out = _run([_nvidia_smi(), "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"])
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 3:
            gpus.append({
                "name": parts[0],
                "vendor": "nvidia",
                "vram_gb": round(int(parts[1]) / 1024, 1),
                "vram_used_gb": round(int(parts[2]) / 1024, 1),
                "shared_memory": False,
            })
    return gpus


def _wmi_info() -> dict:
    script = (
        "$c = Get-CimInstance Win32_Processor | Select-Object -First 1 Name,NumberOfCores,NumberOfLogicalProcessors;"
        "$g = @(Get-CimInstance Win32_VideoController | Select-Object Name,AdapterCompatibility);"
        "@{cpu=$c; gpus=$g} | ConvertTo-Json -Depth 3 -Compress"
    )
    out = _run(["powershell", "-NoProfile", "-Command", script], timeout=30)
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {}


# ------------------------------------------------------------------ Linux

def _meminfo() -> dict[str, int]:
    """/proc/meminfo in kB."""
    out = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            out[key] = int(rest.split()[0])
    except (OSError, ValueError, IndexError):
        pass
    return out


def _linux_cpu() -> dict:
    """The WMI shape (Name, NumberOfCores, NumberOfLogicalProcessors) from /proc/cpuinfo."""
    name, cores = "", set()
    try:
        phys = core = None
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            key, _, value = (x.strip() for x in line.partition(":"))
            if key == "model name" and not name:
                name = value
            elif key == "physical id":
                phys = value
            elif key == "core id":
                core = value
            elif not key and core is not None:  # end of one processor's block
                cores.add((phys, core))
                phys = core = None
        if core is not None:
            cores.add((phys, core))
    except OSError:
        pass
    return {"Name": name, "NumberOfCores": len(cores) or None, "NumberOfLogicalProcessors": os.cpu_count()}


PCI_VENDORS = {"0x10de": "NVIDIA", "0x8086": "Intel", "0x1002": "AMD"}


def _linux_gpus() -> list[dict]:
    """Graphics cards in the WMI shape (Name). lspci gives the model name; without it, the vendor from sysfs."""
    names = []
    out = _run(["lspci"]) if shutil.which("lspci") else ""
    for line in out.splitlines():
        if any(k in line for k in ("VGA compatible controller", "3D controller", "Display controller")):
            names.append(line.split(": ", 1)[-1].strip())
    if not names:
        for card in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
            if "-" in card.name:  # connectors (card0-HDMI-A-1)
                continue
            try:
                vendor = (card / "device" / "vendor").read_text().strip()
            except OSError:
                continue
            if vendor in PCI_VENDORS:
                names.append(f"{PCI_VENDORS[vendor]} graphics")
    return [{"Name": n} for n in dict.fromkeys(names)]


def _vendor(name: str) -> str:
    n = name.lower()
    for vendor in ("nvidia", "intel", "amd", "radeon"):
        if vendor in n:
            return "amd" if vendor == "radeon" else vendor
    return "other"


def scan(root: Path) -> dict:
    total_ram, free_ram = _ram_gb()
    wmi = _wmi_info() if IS_WINDOWS else {"cpu": _linux_cpu(), "gpus": _linux_gpus()}
    cpu = wmi.get("cpu") or {}

    gpus = _nvidia_gpus()
    if not gpus:
        for g in wmi.get("gpus") or []:
            name = (g.get("Name") or "").strip()
            vendor = _vendor(name)
            if vendor in ("intel", "amd"):
                # Integrated GPUs use system RAM; WMI's AdapterRAM is unreliable anyway.
                gpus.append({"name": name, "vendor": vendor, "vram_gb": None, "shared_memory": True})

    if any(g["vendor"] == "nvidia" for g in gpus):
        accel = "cuda"
    elif gpus:
        accel = "vulkan"
    else:
        accel = "cpu"

    return {
        "cpu": (cpu.get("Name") or "").strip(),
        "cpu_cores": cpu.get("NumberOfCores"),
        "cpu_threads": cpu.get("NumberOfLogicalProcessors") or os.cpu_count(),
        "ram_gb": total_ram,
        "ram_free_gb": free_ram,
        "gpus": gpus,
        "gpu": gpus[0]["name"] if gpus else None,
        "vram_gb": gpus[0]["vram_gb"] if gpus else None,
        "accel": accel,
        "disk_free_gb": round(shutil.disk_usage(root).free / 1024**3, 1),
    }


if __name__ == "__main__":
    print(json.dumps(scan(Path.cwd()), indent=2, ensure_ascii=False))
