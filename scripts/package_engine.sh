#!/usr/bin/env bash
# Package the Python engine into a standalone binary for the CURRENT platform
# (PyInstaller onefile). Output: dist/dubflow-engine(.exe)
# CI (.github/workflows/release.yml) runs this on all three platforms.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/engine"

.venv/bin/pip install -q pyinstaller

# platform-specific hidden imports / data
EXTRA=""
if [[ "$(uname)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
  # mlx ships metal libs that pyinstaller misses
  EXTRA="--collect-all mlx --collect-all mlx_whisper"
fi

.venv/bin/pyinstaller \
  --name dubflow-engine \
  --onefile \
  --collect-all uvicorn \
  --collect-all mlx_whisper $EXTRA \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan.on \
  dubflow/main.py

echo "engine packaged: $ROOT/engine/dist/dubflow-engine"
