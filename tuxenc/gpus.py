"""Qué tarjetas gráficas hay en el equipo y qué nodo /dev/dri corresponde a cada una.

Se lee /sys/class/drm (no hace falta ningún programa externo). Sirve para:
* probar solo los codificadores que tienen sentido (NVENC → NVIDIA, QSV → Intel,
  VAAPI → AMD o Intel) y no mostrar errores falsos al usuario;
* elegir el nodo correcto en equipos con varias gráficas (p. ej. portátil Intel + NVIDIA).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

VENDORS = {"0x10de": "nvidia", "0x8086": "intel", "0x1002": "amd", "0x1022": "amd"}
NAMES = {"nvidia": "NVIDIA", "intel": "Intel", "amd": "AMD"}

# Qué fabricante necesita cada tipo de codificador por hardware
HW_VENDORS = {"nvenc": ("nvidia",), "qsv": ("intel",), "vaapi": ("amd", "intel")}


@dataclass(frozen=True)
class Gpu:
    vendor: str            # nvidia | intel | amd | otro id
    render: str            # /dev/dri/renderD128 ("" si no tiene nodo de render)


def detect(sys_root: str = "/sys/class/drm", dev_root: str = "/dev/dri") -> list[Gpu] | None:
    """Gráficas encontradas, o None si no se puede saber (sin /sys/class/drm)."""
    root = Path(sys_root)
    if not root.is_dir():
        return None
    found: dict[str, Gpu] = {}          # clave: dispositivo PCI real (card0 y renderD128 son el mismo)
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return None
    for entry in entries:
        name = entry.name
        if not (name.startswith("renderD") or (name.startswith("card") and "-" not in name)):
            continue
        try:
            vendor_id = (entry / "device" / "vendor").read_text().strip().lower()
            dev_key = os.path.realpath(entry / "device")
        except OSError:
            continue
        vendor = VENDORS.get(vendor_id, vendor_id)
        render = os.path.join(dev_root, name) if name.startswith("renderD") else ""
        prev = found.get(dev_key)
        if prev is None or (render and not prev.render):
            found[dev_key] = Gpu(vendor, render or (prev.render if prev else ""))
    gpus = list(found.values())
    # El driver de NVIDIA a veces no registra nodo DRM (sin nvidia-drm.modeset): se mira /proc
    if not any(g.vendor == "nvidia" for g in gpus) and os.path.exists("/proc/driver/nvidia/version") \
            and sys_root == "/sys/class/drm":
        gpus.append(Gpu("nvidia", ""))
    return gpus


_cache: list[Gpu] | None | bool = False


def cached() -> list[Gpu] | None:
    global _cache
    if _cache is False:
        _cache = detect()
    return _cache  # type: ignore[return-value]


def applicable(hw: str, gpus: list[Gpu] | None) -> bool:
    """¿Tiene sentido probar este tipo de codificador en este equipo?"""
    if gpus is None:
        return True                      # no se sabe: se prueba todo, como antes
    return any(g.vendor in HW_VENDORS.get(hw, ()) for g in gpus)


def render_node(hw: str = "vaapi", gpus: list[Gpu] | None | bool = False) -> str:
    """Nodo /dev/dri/renderD* de una gráfica válida para `hw` (VAAPI/QSV nunca la NVIDIA)."""
    if gpus is False:
        gpus = cached()
    wanted = HW_VENDORS.get(hw, ())
    for g in gpus or []:
        if g.vendor in wanted and g.render and os.path.exists(g.render):
            return g.render
    for n in range(128, 136):
        p = f"/dev/dri/renderD{n}"
        if os.path.exists(p):
            return p
    return "/dev/dri/renderD128"


def describe(gpus: list[Gpu] | None) -> str:
    if gpus is None:
        return "no se ha podido leer /sys/class/drm (se prueban todos los codificadores)"
    if not gpus:
        return "ninguna"
    return ", ".join(NAMES.get(g.vendor, g.vendor) + (f" ({os.path.basename(g.render)})"
                                                       if g.render else "") for g in gpus)
