#!/usr/bin/env bash
# Wrap the one-folder PyInstaller build (dist/Combat-Robot-Gauntlet/) into a
# single-file Linux AppImage. Run from the project root after `pyinstaller`.
#
#   scripts/build_appimage.sh <output.AppImage>
#
# Used by .github/workflows/release.yml on ubuntu-latest.
set -euo pipefail

OUT="${1:-Combat-Robot-Gauntlet-linux-x86_64.AppImage}"
DIST="dist/Combat-Robot-Gauntlet"
APPDIR="AppDir"

[ -d "$DIST" ] || { echo "missing $DIST — run pyinstaller first" >&2; exit 1; }

rm -rf "$APPDIR"
mkdir -p "$APPDIR"
cp -r "$DIST"/. "$APPDIR/"

# AppRun launches the frozen binary (its _internal/ sits beside it in AppDir).
cat > "$APPDIR/AppRun" <<'SH'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/Combat-Robot-Gauntlet" "$@"
SH
chmod +x "$APPDIR/AppRun"

# Desktop entry + icon (top-level, as appimagetool requires).
cp build/gauntlet.png "$APPDIR/combat-robot-gauntlet.png"
cat > "$APPDIR/combat-robot-gauntlet.desktop" <<'DESK'
[Desktop Entry]
Type=Application
Name=Combat-Robot-Gauntlet
Exec=Combat-Robot-Gauntlet
Icon=combat-robot-gauntlet
Categories=Science;Engineering;
Terminal=false
DESK

# appimagetool (continuous release). --appimage-extract-and-run: CI has no FUSE.
TOOL="appimagetool-x86_64.AppImage"
if [ ! -x "$TOOL" ]; then
  wget -q "https://github.com/AppImage/appimagetool/releases/download/continuous/${TOOL}" -O "$TOOL"
  chmod +x "$TOOL"
fi

ARCH=x86_64 "./$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT"
echo "built $OUT"
