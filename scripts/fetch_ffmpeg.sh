#!/usr/bin/env bash
# Download static ffmpeg/ffprobe builds (with libass) for all three platforms
# into dubflow/bin/. Binaries are gitignored (too large for git); re-run this
# script to restore them after a fresh clone.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/bin"; mkdir -p "$BIN"; TMP="$(mktemp -d)"

echo "==> macOS arm64 (osxexperts.net, FFmpeg 9.0)"
curl -sL -o "$TMP/ff9arm.zip" "https://www.osxexperts.net/ffmpeg9arm.zip"
curl -sL -o "$TMP/fp9arm.zip" "https://www.osxexperts.net/ffprobe9arm.zip"
unzip -o -j "$TMP/ff9arm.zip" ffmpeg -d "$TMP/m" >/dev/null
unzip -o -j "$TMP/fp9arm.zip" ffprobe -d "$TMP/m" >/dev/null
cp "$TMP/m/ffmpeg"  "$BIN/ffmpeg-darwin-arm64"
cp "$TMP/m/ffprobe" "$BIN/ffprobe-darwin-arm64"

echo "==> Windows x64 (BtbN win64-gpl, needs proxy in CN: export HTTPS_PROXY=...)"
curl -sL -o "$TMP/win64.zip" "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
unzip -o -q "$TMP/win64.zip" -d "$TMP/w"
cp "$TMP/w"/ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe  "$BIN/ffmpeg-win32-x86_64.exe"
cp "$TMP/w"/ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe "$BIN/ffprobe-win32-x86_64.exe"

echo "==> Linux x64 (BtbN linux64-gpl)"
curl -sL -o "$TMP/linux64.tar.xz" "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
tar -xJf "$TMP/linux64.tar.xz" -C "$TMP"
cp "$TMP"/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg  "$BIN/ffmpeg-linux-x86_64"
cp "$TMP"/ffmpeg-master-latest-linux64-gpl/bin/ffprobe "$BIN/ffprobe-linux-x86_64"

chmod +x "$BIN"/ffmpeg-* "$BIN"/ffprobe-*
# generic names for third-party libs that call bare "ffmpeg" (mlx_whisper etc.)
cd "$BIN" && ln -sf ffmpeg-darwin-arm64 ffmpeg && ln -sf ffprobe-darwin-arm64 ffprobe
echo "==> done:"; ls -la "$BIN"
