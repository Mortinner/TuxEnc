"""Rutas de la aplicación, binarios de FFmpeg y entorno limpio para procesos externos."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from . import APP_ID

HOME = Path.home()


def _xdg(var: str, default: Path) -> Path:
    value = os.environ.get(var, "").strip()
    return Path(value) if value and os.path.isabs(value) else default


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", HOME / ".config") / APP_ID
CACHE_DIR = _xdg("XDG_CACHE_HOME", HOME / ".cache") / APP_ID
DATA_HOME = _xdg("XDG_DATA_HOME", HOME / ".local" / "share")
DATA_DIR = DATA_HOME / APP_ID
STATE_DIR = _xdg("XDG_STATE_HOME", HOME / ".local" / "state") / APP_ID   # historial de renombrado
LOG_DIR = CACHE_DIR / "logs"

# Raíz del paquete y recursos
PKG_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PKG_DIR / "assets"


def appdir() -> Path | None:
    """Directorio montado del AppImage, si se está ejecutando desde uno."""
    value = os.environ.get("APPDIR")
    return Path(value) if value else None


def appimage_path() -> Path | None:
    """Ruta real del archivo .AppImage en ejecución."""
    value = os.environ.get("APPIMAGE")
    return Path(value) if value else None


def _find_bin(name: str) -> str:
    env_dir = os.environ.get("TUXENC_FFMPEG_DIR")
    candidates = []
    if env_dir:
        candidates.append(Path(env_dir) / name)
    ad = appdir()
    if ad:
        candidates.append(ad / "usr" / "ffmpeg" / "bin" / name)
    candidates.append(PKG_DIR.parent / "ffmpeg" / "bin" / name)
    candidates.append(PKG_DIR.parent.parent / "ffmpeg" / "bin" / name)   # AppImage extraído (paquete)
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)
    found = shutil.which(name)
    return found or name


def ffmpeg_bin() -> str:
    return _find_bin("ffmpeg")


def ffprobe_bin() -> str:
    return _find_bin("ffprobe")


_VA_DIRS = [
    "/usr/lib/x86_64-linux-gnu/dri",
    "/usr/lib64/dri",
    "/usr/lib/dri",
    "/usr/local/lib/dri",
    "/run/opengl-driver/lib/dri",
]


def clean_env() -> dict:
    """Entorno para lanzar programas del sistema o FFmpeg sin las variables del AppImage.

    El AppRun añade bibliotecas propias a LD_LIBRARY_PATH (para Qt); los programas
    externos deben ver el entorno original del usuario.
    """
    env = dict(os.environ)
    orig = env.pop("TUXENC_ORIG_LD_LIBRARY_PATH", None)
    if orig is not None:
        if orig:
            env["LD_LIBRARY_PATH"] = orig
        else:
            env.pop("LD_LIBRARY_PATH", None)
    for var in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        env.pop(var, None)
    if "LIBVA_DRIVERS_PATH" not in env:
        dirs = [d for d in _VA_DIRS if os.path.isdir(d)]
        if dirs:
            env["LIBVA_DRIVERS_PATH"] = ":".join(dirs)
    env["LC_ALL"] = "C"  # salida de ffmpeg predecible
    return env


def run_quiet(args: list[str], timeout: float = 15) -> subprocess.CompletedProcess | None:
    """Ejecuta un comando del sistema ignorando errores (devuelve None si no existe)."""
    try:
        return subprocess.run(args, env=clean_env(), capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def desktop_dir() -> Path | None:
    """Carpeta del escritorio del usuario (respeta 'Escritorio', 'Desktop', etc.)."""
    res = run_quiet(["xdg-user-dir", "DESKTOP"])
    if res and res.returncode == 0:
        p = Path(res.stdout.strip())
        if p.is_dir() and p != HOME:
            return p
    dirs_file = _xdg("XDG_CONFIG_HOME", HOME / ".config") / "user-dirs.dirs"
    try:
        for line in dirs_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("XDG_DESKTOP_DIR="):
                raw = line.split("=", 1)[1].strip().strip('"').replace("$HOME", str(HOME))
                p = Path(raw)
                if p.is_dir() and p != HOME:
                    return p
    except OSError:
        pass
    for name in ("Escritorio", "Desktop"):
        p = HOME / name
        if p.is_dir():
            return p
    return None


def videos_dir() -> Path:
    res = run_quiet(["xdg-user-dir", "VIDEOS"])
    if res and res.returncode == 0:
        p = Path(res.stdout.strip())
        if p.is_dir() and p != HOME:
            return p
    for name in ("Vídeos", "Videos"):
        p = HOME / name
        if p.is_dir():
            return p
    return HOME


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, CACHE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
