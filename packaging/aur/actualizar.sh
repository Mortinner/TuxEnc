#!/bin/bash
# Pone el PKGBUILD de tuxenc-bin en la versión publicada que se indique y rehace .SRCINFO.
# Uso (en Arch/CachyOS):  bash packaging/aur/actualizar.sh 1.3.7
set -euo pipefail
ver="${1:?Uso: actualizar.sh VERSIÓN (p. ej. 1.3.7)}"
cd "$(dirname "$0")/tuxenc-bin"
sum=$(curl -fsSL "https://github.com/Mortinner/TuxEnc/releases/download/v$ver/SHA256SUMS" \
      | awk -v f="TuxEnc-$ver-linux-x86_64.zip" '$2 == f || $2 == "*"f {print $1}')
[ -n "$sum" ] || { echo "No encuentro la suma de TuxEnc-$ver-linux-x86_64.zip en la Release v$ver" >&2; exit 1; }
launcher=$(sha256sum tuxenc.sh | cut -d' ' -f1)
sed -i -e "s/^pkgver=.*/pkgver=$ver/" -e "s/^pkgrel=.*/pkgrel=1/" PKGBUILD
python3 - "$sum" "$launcher" <<'PY'
import re, sys
from pathlib import Path
p = Path("PKGBUILD")
s = p.read_text()
s = re.sub(r"sha256sums=\('[0-9a-f]{64}'\n\s+'[0-9a-fA-Z]+'\)",
           f"sha256sums=('{sys.argv[1]}'\n            '{sys.argv[2]}')", s)
p.write_text(s)
PY
makepkg --printsrcinfo > .SRCINFO
echo "PKGBUILD y .SRCINFO en la $ver. Prueba con: makepkg -si   (y luego git commit + push al repo de AUR)"
