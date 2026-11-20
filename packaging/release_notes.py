#!/usr/bin/env python3
"""Notas de una Release: la sección de esa versión en CHANGELOG.md y la línea de descarga.

Uso:  python3 packaging/release_notes.py 1.2.7 > notas.md
Falla si el CHANGELOG no tiene la sección «## [1.2.7] - AAAA-MM-DD».
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOOTER = "\n---\n**Descarga:** el archivo adjunto. Comprueba la descarga con `sha256sum -c SHA256SUMS`.\n"


def section(text: str, version: str) -> str:
    head = re.compile(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}\s*$", re.M)
    m = head.search(text)
    if not m:
        raise SystemExit(f"CHANGELOG.md no tiene la sección «## [{version}] - AAAA-MM-DD»")
    nxt = re.compile(r"^## \[", re.M).search(text, m.end())
    body = text[m.end():nxt.start() if nxt else len(text)].strip("\n")
    if not body.strip():
        raise SystemExit(f"La sección {version} del CHANGELOG está vacía")
    return "\n" + body + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sys.stdout.write(section((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), sys.argv[1]) + FOOTER)
