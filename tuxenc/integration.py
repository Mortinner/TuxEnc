"""Integración en el sistema (acceso directo, menú, iconos) y desinstalación completa.

Todo se instala en la carpeta del usuario; nunca hace falta ser administrador.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from . import APP_ID, APP_NAME, VERSION
from .paths import (ASSETS_DIR, CACHE_DIR, CONFIG_DIR, DATA_DIR, DATA_HOME, STATE_DIR,
                    appimage_path, desktop_dir, run_quiet)

INSTALLED_APPIMAGE = DATA_DIR / f"{APP_NAME}.AppImage"
MANIFEST = DATA_DIR / "manifest.json"
APPS_DIR = DATA_HOME / "applications"
ICONS_DIR = DATA_HOME / "icons" / "hicolor"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)


def running_from_appimage() -> bool:
    return appimage_path() is not None


def is_integrated() -> bool:
    return INSTALLED_APPIMAGE.exists() and (APPS_DIR / f"{APP_ID}.desktop").exists()


def running_installed_copy() -> bool:
    ai = appimage_path()
    try:
        return bool(ai) and INSTALLED_APPIMAGE.exists() and ai.resolve() == INSTALLED_APPIMAGE.resolve()
    except OSError:
        return False


def installed_version() -> str:
    """Versión integrada según el manifiesto ("" si no se sabe: integraciones muy antiguas)."""
    try:
        return str(json.loads(MANIFEST.read_text(encoding="utf-8")).get("version") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def version_key(v: str) -> tuple:
    """«1.1.0-dev.3» → (1, 1, 0, 3); una versión publicada («1.1.0») va después de sus dev."""
    import re
    m = re.match(r"(\d+)\.(\d+)\.(\d+)(?:-dev\.(\d+))?", v or "")
    if not m:
        return ()
    a, b, c, dev = m.groups()
    return int(a), int(b), int(c), int(dev) if dev else 10 ** 9


def _desktop_entry(exec_path: str, icon: str, uninstall: bool = False) -> str:
    q = '"' + exec_path.replace('"', '\\"') + '"'
    if uninstall:
        return "\n".join([
            "[Desktop Entry]",
            "Type=Application",
            "Version=1.0",
            f"Name=Uninstall {APP_NAME}",
            f"Name[es]=Desinstalar {APP_NAME}",
            f"Comment=Remove {APP_NAME} and all its files from this computer",
            f"Comment[es]=Elimina {APP_NAME} y todos sus archivos de este equipo",
            f"Exec={q} --uninstall",
            f"Icon={icon}",
            "Terminal=false",
            "Categories=AudioVideo;Video;",
            "NoDisplay=false",
            "",
        ])
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        f"Name={APP_NAME}",
        "GenericName=Video Transcoder",
        "GenericName[es]=Transcodificador de vídeo",
        "Comment=Convert videos to H.264, H.265, AV1 and VP9 — several at once",
        "Comment[es]=Convierte vídeos a H.264, H.265, AV1 y VP9 — varios a la vez",
        f"Exec={q} %F",
        f"Icon={icon}",
        "Terminal=false",
        "Categories=AudioVideo;Video;AudioVideoEditing;",
        "Keywords=video;transcode;convert;encoder;handbrake;ffmpeg;x265;hevc;av1;"
        "vídeo;convertir;codificar;",
        "MimeType=video/mp4;video/x-matroska;video/webm;video/x-msvideo;video/quicktime;"
        "video/mpeg;video/mp2t;video/x-ms-wmv;video/x-flv;",
        f"StartupWMClass={APP_ID}",
        "StartupNotify=true",
        "",
    ])


_new_dirs: list[str] = []


def _mkdir(path: Path) -> None:
    """Crea carpetas recordando cuáles no existían (para poder borrarlas al desinstalar)."""
    missing = []
    p = path
    while not p.exists():
        missing.append(str(p))
        p = p.parent
    path.mkdir(parents=True, exist_ok=True)
    for d in reversed(missing):
        if d not in _new_dirs:
            _new_dirs.append(d)


def _write_icons(created: list[str]) -> str:
    """Instala los iconos y devuelve la ruta absoluta del icono principal."""
    main_icon = ""
    for size in ICON_SIZES:
        src = ASSETS_DIR / f"{APP_ID}-{size}.png"
        if not src.exists():
            continue
        dst_dir = ICONS_DIR / f"{size}x{size}" / "apps"
        _mkdir(dst_dir)
        dst = dst_dir / f"{APP_ID}.png"
        shutil.copyfile(src, dst)
        created.append(str(dst))
        if size == 256:
            main_icon = str(dst)
    svg = ASSETS_DIR / f"{APP_ID}.svg"
    if svg.exists():
        dst_dir = ICONS_DIR / "scalable" / "apps"
        _mkdir(dst_dir)
        dst = dst_dir / f"{APP_ID}.svg"
        shutil.copyfile(svg, dst)
        created.append(str(dst))
    return main_icon or APP_ID


def _refresh_caches() -> None:
    run_quiet(["update-desktop-database", str(APPS_DIR)])
    if ICONS_DIR.is_dir():
        run_quiet(["gtk-update-icon-cache", "-f", "-t", str(ICONS_DIR)])
    for tool in ("kbuildsycoca6", "kbuildsycoca5"):
        if shutil.which(tool):
            run_quiet([tool])
            break
    run_quiet(["xdg-desktop-menu", "forceupdate"])


def integrate(desktop_shortcut: bool = True) -> list[str]:
    """Copia el AppImage a su sitio fijo y crea menú, iconos y acceso directo."""
    src = appimage_path()
    if src is None:
        raise RuntimeError("not_appimage")
    created: list[str] = []
    try:
        old = json.loads(MANIFEST.read_text(encoding="utf-8"))
        _new_dirs[:] = old.get("dirs", [])
    except (OSError, ValueError):
        _new_dirs.clear()
    _mkdir(DATA_DIR)
    if src.resolve() != INSTALLED_APPIMAGE.resolve():
        tmp = INSTALLED_APPIMAGE.with_suffix(".new")
        shutil.copyfile(src, tmp)
        os.chmod(tmp, 0o755)
        os.replace(tmp, INSTALLED_APPIMAGE)
    created.append(str(INSTALLED_APPIMAGE))

    icon = _write_icons(created)
    _mkdir(APPS_DIR)
    main_desktop = APPS_DIR / f"{APP_ID}.desktop"
    main_desktop.write_text(_desktop_entry(str(INSTALLED_APPIMAGE), icon), encoding="utf-8")
    os.chmod(main_desktop, 0o755)
    created.append(str(main_desktop))
    un_desktop = APPS_DIR / f"{APP_ID}-uninstall.desktop"
    un_desktop.write_text(_desktop_entry(str(INSTALLED_APPIMAGE), icon, uninstall=True),
                          encoding="utf-8")
    os.chmod(un_desktop, 0o755)
    created.append(str(un_desktop))

    if desktop_shortcut:
        ddir = desktop_dir()
        if ddir:
            shortcut = ddir / f"{APP_ID}.desktop"
            shutil.copyfile(main_desktop, shortcut)
            os.chmod(shortcut, 0o755)
            # GNOME (Desktop Icons NG) exige marcarlo como de confianza
            run_quiet(["gio", "set", str(shortcut), "metadata::trusted", "true"])
            created.append(str(shortcut))

    MANIFEST.write_text(json.dumps({"files": created, "dirs": _new_dirs, "version": VERSION}, indent=2),
                        encoding="utf-8")
    _refresh_caches()
    return created


def had_desktop_shortcut() -> bool:
    """Si la integración actual creó el acceso directo del escritorio (para respetarlo al refrescar)."""
    try:
        files = json.loads(MANIFEST.read_text(encoding="utf-8")).get("files", [])
    except (OSError, ValueError, AttributeError):
        return False
    return any(Path(f).name == f"{APP_ID}.desktop" and Path(f).parent != APPS_DIR for f in files)


def finish_self_update() -> str:
    """Primera apertura de una versión que se instaló sola (actualización o vuelta atrás desde la app).

    La copia integrada ya es la nueva, pero el menú, los iconos y el manifiesto son de la anterior:
    se rehacen con los de esta versión. Devuelve la versión anterior ("" si no había nada que hacer).
    """
    if not running_installed_copy():
        return ""
    old = installed_version()
    if not old or old == VERSION:
        return ""
    integrate(desktop_shortcut=had_desktop_shortcut())
    return old


def uninstall() -> list[str]:
    """Elimina absolutamente todo lo que TuxEnc ha creado. Los vídeos del usuario no se tocan."""
    removed: list[str] = []
    files: set[str] = set()
    dirs: list[str] = []
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        files.update(manifest.get("files", []))
        dirs = manifest.get("dirs", [])
    except (OSError, ValueError):
        pass
    # Rutas conocidas por si el manifiesto se perdió
    files.add(str(APPS_DIR / f"{APP_ID}.desktop"))
    files.add(str(APPS_DIR / f"{APP_ID}-uninstall.desktop"))
    for size in ICON_SIZES:
        files.add(str(ICONS_DIR / f"{size}x{size}" / "apps" / f"{APP_ID}.png"))
    files.add(str(ICONS_DIR / "scalable" / "apps" / f"{APP_ID}.svg"))
    ddir = desktop_dir()
    if ddir:
        files.add(str(ddir / f"{APP_ID}.desktop"))
    files.add(str(INSTALLED_APPIMAGE))

    for f in sorted(files):
        p = Path(f)
        if p.is_file() or p.is_symlink():
            try:
                p.unlink()
                removed.append(f)
            except OSError:
                pass
    # Claves de TMDB / OMDb guardadas por TuxEnc (las de Retitler independiente no se tocan)
    try:
        from retitler.config import KeyStore
        for service in ("tmdb", "omdb"):
            KeyStore().for_service(service).clear()
    except Exception:  # noqa: BLE001
        pass
    for d in (DATA_DIR, CONFIG_DIR, CACHE_DIR, STATE_DIR):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            removed.append(str(d))
    _refresh_caches()
    stale_cache = ICONS_DIR / "icon-theme.cache"
    if str(ICONS_DIR) in dirs and stale_cache.exists():
        stale_cache.unlink()
    # Carpetas que creó TuxEnc y han quedado vacías (de la más profunda a la más alta)
    for d in sorted(set(dirs), key=lambda x: x.count("/"), reverse=True):
        try:
            os.rmdir(d)
            removed.append(d)
        except OSError:
            pass
    return removed
