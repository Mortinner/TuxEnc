#!/usr/bin/env bash
#  fetch_deps.sh — Descarga lo que necesita packaging/build.py para compilar el AppImage.
#
#  Uso:   TUXENC_DEPS=/ruta/deps bash packaging/fetch_deps.sh [python] [ffmpeg] [appimage] [xcb]
#         Sin argumentos, todo. Por defecto deja todo en la carpeta «dl» junto al repositorio,
#         que es donde lo busca build.py. Las pruebas solo necesitan «ffmpeg».
#
#  Deja en $TUXENC_DEPS:
#    pys/cpython-3.12.13-linux-x86_64-gnu/       Python portable (python-build-standalone, vía uv)
#    rel-8.1/ffmpeg-n8.1-latest-linux64-gpl-shared-8.1/   FFmpeg 8.1 compartido (BtbN)
#    runtime-x86_64                              runtime de AppImage (type2-runtime)
#    appimagetool                                appimagetool
#    debs/j/usr/lib/x86_64-linux-gnu/libxcb-cursor.so.0.0.0   de Ubuntu 22.04 (comprobado por SHA-256)
#
#  Requisitos: curl, tar, xz, dpkg-deb, uv (https://docs.astral.sh/uv/).
#  Las bibliotecas X11 que se copian del sistema (libxcb-icccm4, libxcb-image0, libxcb-keysyms1,
#  libxcb-render-util0, libxcb-util1, libxkbcommon-x11-0) se instalan con apt: ver el workflow.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DL="${TUXENC_DEPS:-$(dirname "$REPO")/dl}"
PY_VERSION="3.12.13"
FF_URL="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n8.1-latest-linux64-gpl-shared-8.1.tar.xz"
RUNTIME_URL="https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
XCB_CURSOR_URL="http://archive.ubuntu.com/ubuntu/pool/main/x/xcb-util-cursor/libxcb-cursor0_0.1.1-4ubuntu1_amd64.deb"
XCB_CURSOR_SHA256="c9b5d1ad4af57397b1bd77e0a92750e34419def134c0282a0836ae9efc07cf64"

info() { printf '▶ %s\n' "$*"; }
want() { local c; for c in "${PARTS[@]}"; do [ "$c" = "$1" ] && return 0; done; return 1; }
PARTS=("$@")
[ "${#PARTS[@]}" -gt 0 ] || PARTS=(python ffmpeg appimage xcb)
mkdir -p "$DL"
cd "$DL"

if want python; then
info "Python $PY_VERSION portable"
if [ ! -x "pys/cpython-$PY_VERSION-linux-x86_64-gnu/bin/python3.12" ]; then
  uv python install "$PY_VERSION" --install-dir "$DL/pys"
  py="$(find "$DL/pys" -maxdepth 1 -type d -name "cpython-$PY_VERSION-linux-x86_64-gnu" | head -1)"
  [ -n "$py" ] || { echo "uv no dejó Python en $DL/pys" >&2; ls -la "$DL/pys" >&2; exit 1; }
fi
fi

if want ffmpeg; then
info "FFmpeg 8.1 (BtbN, compartido)"
if [ ! -x rel-8.1/ffmpeg-n8.1-latest-linux64-gpl-shared-8.1/bin/ffmpeg ]; then
  mkdir -p rel-8.1
  curl -fsSL --retry 3 -o ffmpeg-shared.tar.xz "$FF_URL"
  tar -xJf ffmpeg-shared.tar.xz -C rel-8.1
  rm ffmpeg-shared.tar.xz
fi
rel-8.1/ffmpeg-n8.1-latest-linux64-gpl-shared-8.1/bin/ffmpeg -hide_banner -version | head -1
fi

if want appimage; then
info "runtime de AppImage y appimagetool"
[ -s runtime-x86_64 ] || curl -fsSL --retry 3 -o runtime-x86_64 "$RUNTIME_URL"
[ -x appimagetool ] || { curl -fsSL --retry 3 -o appimagetool "$APPIMAGETOOL_URL" && chmod +x appimagetool; }
fi

if want xcb; then
info "libxcb-cursor de Ubuntu 22.04"
if [ ! -f debs/j/usr/lib/x86_64-linux-gnu/libxcb-cursor.so.0.0.0 ]; then
  mkdir -p debs
  curl -fsSL --retry 3 -o debs/jammy-xcb-cursor.deb "$XCB_CURSOR_URL"
  echo "$XCB_CURSOR_SHA256  debs/jammy-xcb-cursor.deb" | sha256sum -c -
  dpkg-deb -x debs/jammy-xcb-cursor.deb debs/j
fi
fi

info "Dependencias listas en $DL"
