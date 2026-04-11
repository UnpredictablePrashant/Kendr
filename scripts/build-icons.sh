#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# build-icons.sh  —  Generate electron-app/resources/icon.{png,ico,icns}
#                    from a single high-res source PNG (1024×1024 recommended).
#
# Requires: ImageMagick (brew install imagemagick  /  apt install imagemagick)
# macOS icns: also needs iconutil (ships with Xcode Command Line Tools)
#
# Usage:
#   ./scripts/build-icons.sh path/to/source-logo.png
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SOURCE="${1:-}"
[ -z "$SOURCE" ] && { echo "Usage: $0 path/to/source-logo.png" >&2; exit 1; }
[ -f "$SOURCE" ] || { echo "File not found: $SOURCE" >&2; exit 1; }

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT_DIR/electron-app/resources"
mkdir -p "$OUT_DIR"

command -v convert >/dev/null 2>&1 || {
  echo "ImageMagick 'convert' not found."
  echo "  macOS:  brew install imagemagick"
  echo "  Linux:  sudo apt install imagemagick"
  exit 1
}

echo "Source: $SOURCE"
echo "Output: $OUT_DIR"
echo ""

# ── 1. icon.png (1024×1024) ──────────────────────────────────────────────────
echo "▸ Generating icon.png…"
convert "$SOURCE" -resize 1024x1024! "$OUT_DIR/icon.png"
echo "  ✔ icon.png"

# ── 2. icon.ico (Windows — multi-resolution) ─────────────────────────────────
echo "▸ Generating icon.ico…"
SIZES=(16 24 32 48 64 128 256)
ICO_ARGS=()
for S in "${SIZES[@]}"; do
  TMP="$OUT_DIR/.tmp_${S}.png"
  convert "$SOURCE" -resize "${S}x${S}!" "$TMP"
  ICO_ARGS+=("$TMP")
done
convert "${ICO_ARGS[@]}" "$OUT_DIR/icon.ico"
rm -f "$OUT_DIR"/.tmp_*.png
echo "  ✔ icon.ico"

# ── 3. icon.icns (macOS) ─────────────────────────────────────────────────────
echo "▸ Generating icon.icns…"
if command -v iconutil >/dev/null 2>&1; then
  ICONSET="$OUT_DIR/icon.iconset"
  mkdir -p "$ICONSET"
  for S in 16 32 128 256 512; do
    convert "$SOURCE" -resize "${S}x${S}!"       "$ICONSET/icon_${S}x${S}.png"
    convert "$SOURCE" -resize "$((S*2))x$((S*2))!" "$ICONSET/icon_${S}x${S}@2x.png"
  done
  iconutil -c icns "$ICONSET" -o "$OUT_DIR/icon.icns"
  rm -rf "$ICONSET"
  echo "  ✔ icon.icns"
elif command -v png2icns >/dev/null 2>&1; then
  TMPS=()
  for S in 16 32 128 256 512; do
    T="$OUT_DIR/.icns_${S}.png"
    convert "$SOURCE" -resize "${S}x${S}!" "$T"
    TMPS+=("$T")
  done
  png2icns "$OUT_DIR/icon.icns" "${TMPS[@]}"
  rm -f "${TMPS[@]}"
  echo "  ✔ icon.icns"
else
  echo "  ! iconutil / png2icns not found — icon.icns skipped (macOS only)."
  echo "    Run this script on macOS or install png2icns."
fi

echo ""
echo "Icons written to electron-app/resources/"
ls -lh "$OUT_DIR"/*.png "$OUT_DIR"/*.ico "$OUT_DIR"/*.icns 2>/dev/null || true
