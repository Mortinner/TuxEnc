#!/usr/bin/env bash
#  smoke_test.sh — Comprueba un AppImage ya compilado sin pantalla:
#  que se extrae, que su Python carga Qt y TuxEnc, que su FFmpeg funciona, qué claves lleva
#  integradas (solo los nombres) y que la ventana arranca y sigue abierta unos segundos.
#
#  Uso:   bash packaging/smoke_test.sh dist/TuxEnc-1.2.7-x86_64.AppImage [tmdb,tvdb]
#         El segundo argumento, opcional, son las claves que deben ir integradas.
set -euo pipefail

APPIMAGE="$(readlink -f "$1")"
REQUIRED="${2:-}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

echo "▶ Extraer $APPIMAGE"
"$APPIMAGE" --appimage-extract >/dev/null
R="$WORK/squashfs-root"

echo "▶ FFmpeg incluido"
"$R/usr/ffmpeg/bin/ffmpeg" -hide_banner -version | head -1
"$R/usr/ffmpeg/bin/ffprobe" -hide_banner -version | head -1

echo "▶ Python, Qt y TuxEnc incluidos"
LD_LIBRARY_PATH="$R/usr/lib" QT_QPA_PLATFORM=offscreen REQUIRED="$REQUIRED" \
  "$R/usr/python/bin/python3.12" -s -E -B - "$R/usr/app" <<'EOF'
import os, sys
sys.path.insert(0, sys.argv[1])
from PySide6 import QtCore, QtWidgets  # noqa: F401
import tuxenc, retitler  # noqa: F401
from tuxenc import builtin_keys
keys = sorted(builtin_keys.load())
print("TuxEnc", tuxenc.VERSION, "· Qt", QtCore.qVersion(), "· claves integradas:", ", ".join(keys) or "ninguna")
missing = {k for k in os.environ["REQUIRED"].split(",") if k} - set(keys)
if missing:
    sys.exit("Faltan claves integradas: " + ", ".join(sorted(missing)))
EOF

echo "▶ La ventana arranca (15 s sin pantalla)"
export XDG_CONFIG_HOME="$WORK/c" XDG_CACHE_HOME="$WORK/k" XDG_STATE_HOME="$WORK/s" XDG_DATA_HOME="$WORK/d"
export QT_QPA_PLATFORM=offscreen PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring
set +e
timeout 15 "$R/AppRun" >"$WORK/app.log" 2>&1
rc=$?
set -e
if [ "$rc" -ne 124 ]; then
  echo "TuxEnc se cerró antes de tiempo (código $rc):"
  tail -40 "$WORK/app.log"
  exit 1
fi
echo "✓ AppImage correcto"
