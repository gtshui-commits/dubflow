#!/usr/bin/env python3
"""End-to-end smoke test: generate speech audio -> engine pipeline -> SRT out.

Usage: engine/.venv/bin/python ../scripts/smoke_test.py
Env: SMOKE_MODEL=tiny|base|large-v3-turbo (default tiny)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1] / "engine"
PORT = int(os.environ.get("SMOKE_PORT", "8799"))
BASE = f"http://127.0.0.1:{PORT}"
MODEL = os.environ.get("SMOKE_MODEL", "tiny")
TEXT = ("Hello, this is a smoke test of the DubFlow video translation engine. "
        "Metal GPU acceleration on Apple Silicon should make transcription fast. "
        "The quick brown fox jumps over the lazy dog.")


def http(method: str, path: str, payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="dubflow-smoke-"))
    aiff = tmp / "sample.aiff"
    wav = tmp / "sample.wav"

    print("[1/5] generating test audio with macOS `say` ...")
    r = subprocess.run(["say", "-o", str(aiff), TEXT], capture_output=True)
    if r.returncode != 0 or not aiff.exists():
        print("  say failed, falling back to sine wave:", r.stderr.decode()[-200:])
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=5", "-ar", "16000", "-ac", "1",
                        str(wav)], check=True, capture_output=True)
    else:
        subprocess.run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1",
                        str(wav)], check=True, capture_output=True)
    print(f"  audio: {wav} ({wav.stat().st_size} bytes)")

    env = dict(os.environ,
               DUBFLOW_DATA_DIR=str(tmp / "data"),
               DUBFLOW_PORT=str(PORT),
               DUBFLOW_HOST="127.0.0.1")
    print("[2/5] starting engine ...")
    engine = subprocess.Popen(
        [str(ENGINE_DIR / ".venv" / "bin" / "python"), "-m", "dubflow"],
        cwd=str(ENGINE_DIR), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(60):
            time.sleep(0.5)
            if engine.poll() is not None:
                print(engine.stdout.read().decode()[-2000:])
                return 1
            try:
                health = http("GET", "/health")
                break
            except Exception:
                continue
        else:
            print("engine did not start in time")
            return 1
        print(f"  health: {health}")

        print(f"[3/5] creating job (asr model={MODEL}, translate=off) ...")
        job = http("POST", "/jobs", {
            "video_path": str(wav),
            "asr": {"provider": "auto", "model": MODEL},
            "translation": {"enabled": False},
        })
        jid = job["id"]
        print(f"  job id: {jid}")

        print("[4/5] waiting for pipeline (first run downloads the model) ...")
        deadline = time.time() + 900
        last = None
        while time.time() < deadline:
            state = http("GET", f"/jobs/{jid}")
            steps = state["steps"]
            brief = state["status"] + " | " + " ".join(
                f"{k}:{v['status']}({int(v['progress'] * 100)}%)"
                for k, v in steps.items())
            if brief != last:
                print("  " + brief)
                last = brief
            if state["status"] in ("done", "failed", "cancelled"):
                break
            time.sleep(1)
        if state["status"] != "done":
            print("  FAILED:", state.get("error"))
            return 1

        print("[5/5] results")
        print("  backend:", state["backend"])
        tr = http("GET", f"/jobs/{jid}/transcript")
        print("  language:", tr["language"])
        for seg in tr["segments"]:
            print(f"    [{seg['start']:7.2f} -> {seg['end']:7.2f}] {seg['text']}")
        srt_path = Path(state["artifacts"]["source_srt"])
        print("  srt head:")
        print("\n".join("    " + l for l in srt_path.read_text().splitlines()[:6]))
        print("\nSMOKE TEST PASSED ✅")
        return 0
    finally:
        engine.terminate()
        try:
            engine.wait(timeout=5)
        except subprocess.TimeoutExpired:
            engine.kill()
        if not os.environ.get("SMOKE_KEEP"):
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
