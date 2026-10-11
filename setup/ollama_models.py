"""Read and copy models in Ollama's on-disk store (manifests/ + blobs/).

Used to reuse models that a system-wide Ollama already downloaded, instead of
downloading them again.
"""

import json
import os
import shutil
from pathlib import Path
from typing import Callable

DEFAULT_REGISTRY = "registry.ollama.ai"


def _split_name(name: str) -> tuple[str, str, str, str]:
    """'qwen3:8b' -> (registry.ollama.ai, library, qwen3, 8b)."""
    base, _, tag = name.partition(":")
    tag = tag or "latest"
    parts = base.split("/")
    if len(parts) == 1:
        return DEFAULT_REGISTRY, "library", parts[0], tag
    if len(parts) == 2:
        return DEFAULT_REGISTRY, parts[0], parts[1], tag
    return parts[0], parts[1], "/".join(parts[2:]), tag


def manifest_path(models_dir: Path, name: str) -> Path:
    registry, namespace, model, tag = _split_name(name)
    return models_dir / "manifests" / registry / namespace / model / tag


def list_models(models_dir: Path) -> list[str]:
    root = models_dir / "manifests"
    names = []
    if not root.is_dir():
        return names
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).parts  # registry, namespace, model..., tag
        if len(rel) < 4:
            continue
        registry, namespace, *model, tag = rel
        model = "/".join(model)
        if registry == DEFAULT_REGISTRY:
            base = model if namespace == "library" else f"{namespace}/{model}"
        else:
            base = f"{registry}/{namespace}/{model}"
        names.append(f"{base}:{tag}")
    return sorted(names)


def _blob_path(models_dir: Path, digest: str) -> Path:
    return models_dir / "blobs" / digest.replace(":", "-")


def model_blobs(models_dir: Path, name: str) -> list[tuple[Path, int]]:
    manifest = json.loads(manifest_path(models_dir, name).read_text(encoding="utf-8"))
    layers = [manifest["config"], *manifest.get("layers", [])]
    return [(_blob_path(models_dir, layer["digest"]), int(layer.get("size", 0))) for layer in layers]


def model_size(models_dir: Path, name: str) -> int:
    return sum(size for _, size in model_blobs(models_dir, name))


def has_model(models_dir: Path, name: str) -> bool:
    try:
        return all(p.exists() and p.stat().st_size == s for p, s in model_blobs(models_dir, name))
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return False


def copy_model(
    name: str,
    src_dir: Path,
    dst_dir: Path,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    """Copy one model (never move). Returns bytes copied. Resumable: complete blobs are skipped."""
    blobs = model_blobs(src_dir, name)
    total = sum(size for _, size in blobs)
    done = copied = 0
    (dst_dir / "blobs").mkdir(parents=True, exist_ok=True)

    for src, size in blobs:
        dst = dst_dir / "blobs" / src.name
        if not (dst.exists() and dst.stat().st_size == size):
            tmp = dst.with_name(dst.name + ".partial")
            with open(src, "rb") as fin, open(tmp, "wb") as fout:
                while chunk := fin.read(16 * 1024 * 1024):
                    fout.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
            tmp.replace(dst)
            copied += size
        else:
            done += size
            if progress:
                progress(done, total)

    # Manifest last, so an interrupted copy never looks like an installed model.
    dst_manifest = manifest_path(dst_dir, name)
    dst_manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(manifest_path(src_dir, name), dst_manifest)
    return copied


def system_model_dirs(exclude: Path | None = None) -> list[Path]:
    """Model stores of a system-wide Ollama install (env var or default location)."""
    candidates = [os.environ.get("OLLAMA_MODELS")]
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            candidates.append(winreg.QueryValueEx(key, "OLLAMA_MODELS")[0])
    except (ImportError, OSError):  # Linux has no registry
        pass
    candidates.append(str(Path.home() / ".ollama" / "models"))
    candidates.append("/usr/share/ollama/.ollama/models")  # Linux: Ollama installed as a system service

    seen, dirs = set(), []
    for c in candidates:
        if not c:
            continue
        path = Path(os.path.expandvars(c)).resolve()
        if path in seen or (exclude and path == exclude.resolve()):
            continue
        seen.add(path)
        if (path / "manifests").is_dir():
            dirs.append(path)
    return dirs
