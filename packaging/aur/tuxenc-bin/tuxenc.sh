#!/bin/sh
# Lanzador de TuxEnc instalado como paquete: lo actualiza el gestor de paquetes, no TuxEnc
export TUXENC_PACKAGED="${TUXENC_PACKAGED:-pacman}"
export APPDIR=/opt/tuxenc          # FFmpeg y bibliotecas propias, como dentro del AppImage
exec /opt/tuxenc/AppRun "$@"
