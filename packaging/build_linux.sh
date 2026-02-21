#!/usr/bin/env bash
set -euo pipefail

ARCH="${1:-x64}"
OUT_ROOT="${2:-release_bundle}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_ROOT="$ROOT/.build_out/linux-$ARCH"
DIST_PATH="$BUILD_ROOT/dist"
WORK_PATH="$BUILD_ROOT/build"
ART_DIR="$ROOT/$OUT_ROOT/installers/linux/$ARCH"

rm -rf "$BUILD_ROOT"
mkdir -p "$ART_DIR"

python3 -m PyInstaller --noconfirm --clean "$ROOT/ASCIIStudio.spec" \
  --distpath "$DIST_PATH" \
  --workpath "$WORK_PATH"

OUT_TGZ="$ART_DIR/ASCIIStudio_linux_${ARCH}_portable.tar.gz"
tar -C "$DIST_PATH" -czf "$OUT_TGZ" ASCIIStudio

(
  cd "$ART_DIR"
  sha256sum "$(basename "$OUT_TGZ")" > SHA256SUMS.txt
)

echo "Done. Artifacts: $ART_DIR"

