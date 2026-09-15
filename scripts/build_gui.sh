#!/usr/bin/env bash
# Build the GUI (frontend + Tauri shell). Requires: node, rustup toolchain.
# Engine binary must exist first (scripts/package_engine.sh) and be copied to
# src-tauri/binaries/ - see .github/workflows/release.yml for the full flow.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/gui"
npm install
npm run build
npm run tauri build
