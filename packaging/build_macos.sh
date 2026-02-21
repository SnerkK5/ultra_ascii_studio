#!/usr/bin/env bash
set -euo pipefail

ARCH="${1:-x64}"
OUT_ROOT="${2:-release_bundle}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_ROOT="$ROOT/.build_out/macos-$ARCH"
DIST_PATH="$BUILD_ROOT/dist"
WORK_PATH="$BUILD_ROOT/build"
ART_DIR="$ROOT/$OUT_ROOT/installers/macos/$ARCH"

rm -rf "$BUILD_ROOT"
mkdir -p "$ART_DIR"

python3 -m PyInstaller --noconfirm --clean "$ROOT/ASCIIStudio.spec" \
  --distpath "$DIST_PATH" \
  --workpath "$WORK_PATH"

OUT_ZIP="$ART_DIR/ASCIIStudio_macos_${ARCH}_portable.zip"
(
  cd "$DIST_PATH"
  rm -f "$OUT_ZIP"
  zip -r "$OUT_ZIP" ASCIIStudio >/dev/null
)

(
  cd "$ART_DIR"
  shasum -a 256 "$(basename "$OUT_ZIP")" > SHA256SUMS.txt
)

echo "Done. Artifacts: $ART_DIR"

