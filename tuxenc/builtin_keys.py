"""Claves de los buscadores que trae el AppImage oficial.

Las claves NO están en el código fuente: el script de compilación (packaging/build.py) genera
``_builtin_keys.py`` dentro del AppImage a partir de ``packaging/keys.env`` (que no se sube al
repositorio) o de variables de entorno del CI. Van algo ofuscadas para que no aparezcan como texto
plano al buscar en el binario; no es una protección real.

Quien compile desde las fuentes sin ese archivo tendrá TuxEnc sin claves integradas y podrá
poner las suyas en Ajustes → Renombrado y buscadores.
"""
from __future__ import annotations

import base64
import hashlib

SERVICES = ("tmdb", "tvdb", "omdb")
_SALT = b"TuxEnc/GPLv3/builtin-keys"


def _stream(n: int) -> bytes:
    out, block = b"", _SALT
    while len(out) < n:
        block = hashlib.sha256(block).digest()
        out += block
    return out[:n]


def obfuscate(value: str) -> str:
    raw = value.encode("utf-8")
    return base64.b64encode(bytes(a ^ b for a, b in zip(raw, _stream(len(raw))))).decode("ascii")


def reveal(token: str) -> str:
    try:
        raw = base64.b64decode(token.encode("ascii"))
    except (ValueError, UnicodeError):
        return ""
    return bytes(a ^ b for a, b in zip(raw, _stream(len(raw)))).decode("utf-8", "replace")


def render_module(keys: dict[str, str]) -> str:
    """Contenido de _builtin_keys.py (lo usa el script de compilación)."""
    lines = ['"""Generado al compilar. No editar ni subir al repositorio."""', "KEYS = {"]
    for name in SERVICES:
        if keys.get(name):
            lines.append(f"    {name!r}: {obfuscate(keys[name])!r},")
    lines.append("}")
    return "\n".join(lines) + "\n"


def load() -> dict[str, str]:
    """Claves integradas disponibles ({} si este TuxEnc se compiló sin ellas)."""
    try:
        from . import _builtin_keys  # type: ignore[attr-defined]
    except ImportError:
        return {}
    keys = getattr(_builtin_keys, "KEYS", {})
    return {k: reveal(v) for k, v in keys.items() if k in SERVICES and isinstance(v, str)}
