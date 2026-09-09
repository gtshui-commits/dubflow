"""Download manager: whisper models + bundled ffmpeg, with progress state.

The GUI polls GET /downloads and triggers POSTs; downloads run in daemon
threads so the engine stays responsive.
"""
from __future__ import annotations

import platform
import shutil
import sys
import threading
import zipfile
from pathlib import Path
from typing import Any, Dict

import httpx

from .config import settings

# ---------------------------------------------------------------------------
# Model catalog: key -> (backend, hf_repo)
# backend "mlx"          -> Apple Silicon (macOS), files land in models_dir/<key>/
# backend "ctranslate2"  -> faster-whisper (NVIDIA CUDA / CPU), TODO(platform): verify on real GPU
# NOTE: mlx-community/whisper-base & whisper-small excluded for now - the CN
# mirror currently 401s their API/resolve endpoints. TODO: restore via fallback.
# ---------------------------------------------------------------------------
_MLX_FILES = ["config.json", "weights.npz"]
_CT2_FILES = ["config.json", "model.bin", "tokenizer.json", "preprocessor_config.json", "vocabulary.json"]

CATALOG: Dict[str, Dict[str, Any]] = {
    "tiny":                    {"backend": "mlx", "repo": "mlx-community/whisper-tiny", "files": _MLX_FILES},
    "medium":                  {"backend": "mlx", "repo": "mlx-community/whisper-medium-4bit", "files": _MLX_FILES},
    "large-v3":                {"backend": "mlx", "repo": "mlx-community/whisper-large-v3-4bit", "files": _MLX_FILES},
    "large-v3-turbo":          {"backend": "mlx", "repo": "mlx-community/whisper-large-v3-turbo", "files": ["config.json", "weights.safetensors"]},
    "large-v3-turbo-q4":       {"backend": "mlx", "repo": "mlx-community/whisper-large-v3-turbo-q4", "files": _MLX_FILES},
    "faster-whisper-tiny":     {"backend": "ctranslate2", "repo": "Systran/faster-whisper-tiny", "files": _CT2_FILES},
    "faster-whisper-base":     {"backend": "ctranslate2", "repo": "Systran/faster-whisper-base", "files": _CT2_FILES},
    "faster-whisper-large-v3": {"backend": "ctranslate2", "repo": "Systran/faster-whisper-large-v3", "files": _CT2_FILES},
}

_BIN_DIR = Path(__file__).resolve().parents[2] / "bin"
_state_lock = threading.Lock()
_state: Dict[str, Dict[str, Any]] = {}


def _set(key: str, **kw: Any) -> None:
    with _state_lock:
        st = _state.setdefault(key, {"status": "idle", "progress": 0.0, "detail": ""})
        st.update(kw)


def _get(key: str) -> Dict[str, Any]:
    with _state_lock:
        return dict(_state.get(key, {"status": "idle", "progress": 0.0, "detail": ""}))


def _model_dir(key: str) -> Path:
    return settings.models_dir / key


def _existing_model_dir(key: str, repo: str) -> Path | None:
    """Local dir may be named by alias, repo id, or repo basename."""
    for name in (key, repo, Path(repo).name):
        d = settings.models_dir / name
        if d.is_dir():
            return d
    return None


def _bundled(binary: str) -> Optional[Path]:
    plat = f"{sys.platform}-{platform.machine()}"
    ext = ".exe" if sys.platform == "win32" else ""
    cand = _BIN_DIR / f"{binary}-{plat}{ext}"
    return cand if cand.is_file() else None


def ffmpeg_status() -> dict:
    ff, fp = _bundled("ffmpeg"), _bundled("ffprobe")
    return {
        "installed": bool(ff and fp),
        "ffmpeg": str(ff) if ff else None,
        "ffprobe": str(fp) if fp else None,
    }


def downloads_snapshot() -> dict:
    models = []
    for key in CATALOG:
        backend, repo = CATALOG[key]["backend"], CATALOG[key]["repo"]
        d = _existing_model_dir(key, repo)
        has_weights = False
        size = 0
        if d is not None:
            files = [f for f in d.iterdir() if f.is_file()]
            has_weights = any(f.suffix in (".npz", ".bin", ".safetensors") for f in files)
            size = sum(f.stat().st_size for f in files)
        info = {"key": key, "repo": repo, "backend": backend,
                "downloaded": has_weights, "size_mb": round(size / 1e6, 1)}
        info.update(_get(f"model:{key}"))
        models.append(info)
    ff = ffmpeg_status()
    ff.update(_get("ffmpeg"))
    return {"ffmpeg": ff, "models": models}


# ---------------------------------------------------------------------------
# model downloads (HF files via configured mirror endpoint)
# ---------------------------------------------------------------------------

def _download_model_sync(key: str, repo: str, fallback_files: list) -> None:
    endpoint = settings.hf_endpoint.rstrip("/")
    dest = _model_dir(key)
    dest.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120, trust_env=True) as client:
        # try tree API for file list + sizes; on redirect/404 fall back to a
        # hardcoded list (some mirrors don't proxy the API for every repo)
        files = []
        try:
            r = client.get(f"{endpoint}/api/models/{repo}/tree/main")
            if r.status_code == 200:
                files = [(f["path"], f["size"]) for f in r.json()
                         if f.get("type") == "file"
                         and not f["path"].startswith(".")
                         and f["path"] not in ("README.md",)]
        except Exception:
            files = []
        if not files:
            files = [(p, 0) for p in fallback_files]
        known = all(s > 0 for _, s in files)
        total = sum(s for _, s in files)
        done_bytes = 0
        done_files = 0
        for path, size in files:
            out = dest / path
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_name(out.name + ".part")
            url = f"{endpoint}/{repo}/resolve/main/{path}"
            try:
                with client.stream("GET", url, follow_redirects=True) as r:
                    if r.status_code == 404:
                        done_files += 1
                        continue
                    r.raise_for_status()
                    with open(tmp, "wb") as w:
                        for chunk in r.iter_bytes(1 << 20):
                            w.write(chunk)
                            done_bytes += len(chunk)
            finally:
                if tmp.exists():
                    tmp.rename(out)
                done_files += 1
            prog = (done_bytes / total) if known else (done_files / len(files))
            _set(f"model:{key}", progress=round(min(prog, 1.0), 4),
                 detail=f"{path} ({done_files}/{len(files)})")
    _set(f"model:{key}", status="done", progress=1.0, detail="completed")


def _worker(state_key: str, fn, *args) -> None:
    try:
        fn(*args)
    except Exception as e:  # noqa: BLE001
        _set(state_key, status="failed", detail=f"{type(e).__name__}: {e}")


def start_model_download(key: str) -> dict:
    if key not in CATALOG:
        raise ValueError(f"unknown model: {key}")
    st = _get(f"model:{key}")
    if st["status"] == "downloading":
        return {"ok": True, "already_running": True}
    _set(f"model:{key}", status="downloading", progress=0.0, detail="starting")
    entry = CATALOG[key]
    threading.Thread(
        target=_worker,
        args=(f"model:{key}", _download_model_sync, key, entry["repo"], entry["files"]),
        daemon=True).start()
    return {"ok": True}


# ---------------------------------------------------------------------------
# bundled ffmpeg download (current platform only)
# ---------------------------------------------------------------------------

def _download_ffmpeg_sync() -> None:
    bin_dir = _BIN_DIR
    bin_dir.mkdir(parents=True, exist_ok=True)
    plat_tag = f"{sys.platform}-{platform.machine()}"
    ext = ".exe" if sys.platform == "win32" else ""
    client = httpx.Client(timeout=300, trust_env=True, follow_redirects=True)
    tmp = Path(settings.data_dir) / "ffmpeg_dl"
    tmp.mkdir(parents=True, exist_ok=True)

    def fetch(url: str, dest: Path) -> None:
        with client.stream("GET", url) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0)) or 1
            done = 0
            with open(dest, "wb") as w:
                for chunk in r.iter_bytes(1 << 20):
                    w.write(chunk)
                    done += len(chunk)
                    _set("ffmpeg", progress=round(done / total, 4),
                         detail=f"{dest.name} {done // 1_000_000}/{total // 1_000_000}MB")

    def extract(archive: Path, want: str) -> Path:
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as zf:
                for n in zf.namelist():
                    if n.endswith("/" + want) or n == want:
                        out = tmp / want
                        out.write_bytes(zf.read(n))
                        return out
        elif archive.suffix == ".xz" or archive.name.endswith(".tar.xz"):
            import tarfile
            with tarfile.open(archive) as tf:
                for n in tf.getnames():
                    if n.endswith("/" + want):
                        tf.extract(n, tmp)
                        return tmp / n
        raise RuntimeError(f"{want} not found in {archive.name}")

    pairs = []
    if sys.platform == "darwin":
        arch = "arm" if platform.machine() == "arm64" else "intel"
        pairs = [("ffmpeg", f"https://www.osxexperts.net/ffmpeg9{arch}.zip"),
                 ("ffprobe", f"https://www.osxexperts.net/ffprobe9{arch}.zip")]
        for i, (name, url) in enumerate(pairs):
            a = tmp / f"dl{i}.zip"
            fetch(url, a)
            got = extract(a, name)
            target = bin_dir / f"{name}-{plat_tag}"
            shutil.copy2(got, target)
            target.chmod(0o755)
    elif sys.platform == "win32":
        url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        a = tmp / "dl.zip"
        fetch(url, a)
        with zipfile.ZipFile(a) as zf:
            for n, out_name in (("ffmpeg.exe", "ffmpeg-win32-x86_64.exe"),
                                ("ffprobe.exe", "ffprobe-win32-x86_64.exe")):
                for member in zf.namelist():
                    if member.endswith("/" + n):
                        (bin_dir / out_name).write_bytes(zf.read(member))
                        break
    elif sys.platform == "linux":
        url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
        a = tmp / "dl.tar.xz"
        fetch(url, a)
        with tarfile.open(a) as tf:
            for n, out_name in (("ffmpeg", "ffmpeg-linux-x86_64"),
                                ("ffprobe", "ffprobe-linux-x86_64")):
                for member in tf.getnames():
                    if member.endswith("/" + n):
                        tf.extract(member, tmp)
                        src = tmp / member
                        shutil.copy2(src, bin_dir / out_name)
                        (bin_dir / out_name).chmod(0o755)
                        break
    else:
        raise RuntimeError(f"unsupported platform: {sys.platform}")

    # generic names so third-party libs calling bare "ffmpeg" hit ours
    try:
        (bin_dir / "ffmpeg").symlink_to(f"ffmpeg-{plat_tag}{ext}")
        (bin_dir / "ffprobe").symlink_to(f"ffprobe-{plat_tag}{ext}")
    except (OSError, NotImplementedError):
        shutil.copy2(bin_dir / f"ffmpeg-{plat_tag}{ext}", bin_dir / "ffmpeg")
        shutil.copy2(bin_dir / f"ffprobe-{plat_tag}{ext}", bin_dir / "ffprobe")
    shutil.rmtree(tmp, ignore_errors=True)
    _set("ffmpeg", status="done", progress=1.0, detail="installed")


def start_ffmpeg_download() -> dict:
    st = _get("ffmpeg")
    if st["status"] == "downloading":
        return {"ok": True, "already_running": True}
    _set("ffmpeg", status="downloading", progress=0.0, detail="starting")
    threading.Thread(target=_worker, args=(_download_ffmpeg_sync, "ffmpeg"),
                     daemon=True).start()
    return {"ok": True}
