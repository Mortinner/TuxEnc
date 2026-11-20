#!/usr/bin/env python3
"""Construye TuxEnc-<versión>-x86_64.AppImage y el zip de distribución.

Uso:  python3 packaging/build.py
Requiere en $TUXENC_DEPS (por defecto ../dl): Python portable, FFmpeg compartido (BtbN),
runtime de AppImage, appimagetool y libxcb-cursor de Ubuntu 22.04. Los descarga
packaging/fetch_deps.sh. pip: $TUXENC_PIP o, si no, el del Python que ejecuta este script.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DL = Path(os.environ.get("TUXENC_DEPS") or ROOT.parent / "dl").resolve()
BUILD = ROOT / "build"
APPDIR = BUILD / "AppDir"
DIST = ROOT / "dist"

PY_SRC = DL / "pys" / "cpython-3.12.13-linux-x86_64-gnu"
FF_SRC = DL / "rel-8.1" / "ffmpeg-n8.1-latest-linux64-gpl-shared-8.1"
RUNTIME = DL / "runtime-x86_64"
APPIMAGETOOL = DL / "appimagetool"
XCB_CURSOR = DL / "debs" / "j" / "usr" / "lib" / "x86_64-linux-gnu"
SYS_LIBDIR = Path("/lib/x86_64-linux-gnu")
PIP = os.environ.get("TUXENC_PIP", "").split() or [sys.executable, "-m", "pip"]
PYSIDE_VERSION = "6.12.0"
KEYRING_VERSION = "25.7.0"      # llavero del sistema para las claves de TMDB / OMDb (como Retitler)

sys.path.insert(0, str(ROOT))
from tuxenc import VERSION  # noqa: E402

KEYS_FILE = ROOT / "packaging" / "keys.env"     # NO se sube al repositorio (.gitignore)


def builtin_keys_from_env() -> dict[str, str]:
    """Claves de los buscadores para el AppImage oficial: de packaging/keys.env o de las variables
    TUXENC_KEY_TMDB / TUXENC_KEY_TVDB / TUXENC_KEY_OMDB (p. ej. secretos del CI)."""
    keys: dict[str, str] = {}
    if KEYS_FILE.exists():
        for line in KEYS_FILE.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.strip().partition("=")
            if sep and not name.startswith("#") and value.strip():
                keys[name.strip().lower().removeprefix("tuxenc_key_")] = value.strip().strip('"\'')
    for name in ("tmdb", "tvdb", "omdb"):
        env = os.environ.get(f"TUXENC_KEY_{name.upper()}", "").strip()
        if env:
            keys[name] = env
    return {k: v for k, v in keys.items() if k in ("tmdb", "tvdb", "omdb")}

PY_STRIP = [
    "lib/python3.12/test", "lib/python3.12/idlelib", "lib/python3.12/tkinter",
    "lib/python3.12/turtledemo", "lib/python3.12/ensurepip", "lib/python3.12/lib2to3",
    "lib/python3.12/pydoc_data", "lib/python3.12/unittest", "lib/python3.12/venv",
    "lib/python3.12/config-3.12-x86_64-linux-gnu", "lib/python3.12/site-packages/pip",
    "include", "share", "lib/pkgconfig", "lib/itcl4.2.4", "lib/tcl9", "lib/tk9.0",
    "lib/thread3.0.1", "lib/tcl8", "lib/tcl8.6", "lib/tk8.6",
]
PY_STRIP_GLOBS = ["lib/libtcl*", "lib/libtk*", "lib/python3.12/lib-dynload/_tkinter*",
                  "lib/python3.12/lib-dynload/*test*", "lib/libpython3.12.a",
                  "lib/python3.12/site-packages/pip*", "bin/idle*", "bin/pydoc*", "bin/pip*",
                  "bin/2to3*", "bin/python3*-config"]

QT_PY_MODULES = {"QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtDBus"}
QT_PLUGINS_KEEP = {
    "platforms": {"libqxcb.so", "libqwayland.so", "libqoffscreen.so"},
    "platformthemes": None, "platforminputcontexts": {"libcomposeplatforminputcontextplugin.so",
                                                      "libibusplatforminputcontextplugin.so"},
    "xcbglintegrations": None, "wayland-decoration-client": None,
    "wayland-graphics-integration-client": None, "wayland-shell-integration": None,
    "imageformats": {"libqsvg.so", "libqico.so", "libqjpeg.so", "libqgif.so"},
    "iconengines": None,
}
BUNDLED_SYS_LIBS = ["libxcb-icccm.so.4", "libxcb-image.so.0", "libxcb-keysyms.so.1",
                    "libxcb-render-util.so.0", "libxcb-util.so.1", "libxkbcommon-x11.so.0"]


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def rm(p: Path):
    if p.is_symlink() or p.is_file():
        p.unlink()
    elif p.is_dir():
        shutil.rmtree(p)


def needed(lib: Path) -> list[str]:
    out = subprocess.run(["readelf", "-d", str(lib)], capture_output=True, text=True).stdout
    return re.findall(r"\(NEEDED\).*\[(.+?)\]", out)


def build_python(usr: Path) -> Path:
    py = usr / "python"
    shutil.copytree(PY_SRC, py, symlinks=True)
    for rel in PY_STRIP:
        rm(py / rel)
    for pat in PY_STRIP_GLOBS:
        for p in py.glob(pat):
            rm(p)
    for p in py.rglob("__pycache__"):
        rm(p)
    site = py / "lib/python3.12/site-packages"
    run([*PIP, "install", "--quiet", "--no-compile", "--target", site,
         f"PySide6-Essentials=={PYSIDE_VERSION}", f"keyring=={KEYRING_VERSION}"])
    trim_pyside(site / "PySide6")
    for p in site.glob("*.dist-info"):
        for f in p.iterdir():
            if f.name not in ("METADATA", "LICENSE", "LICENSE.txt", "licenses"):
                rm(f)
    return py


def trim_pyside(ps: Path):
    # Módulos Python que no usamos
    for f in ps.glob("Qt*.abi3.so"):
        if f.name.split(".")[0] not in QT_PY_MODULES:
            f.unlink()
    for f in ps.glob("Qt*.pyi"):
        f.unlink()
    for d in ("include", "typesystems", "glue", "scripts", "examples", "doc"):
        rm(ps / d)
    for f in list(ps.iterdir()):
        if f.is_file() and os.access(f, os.X_OK) and not f.suffix:
            f.unlink()   # designer, lupdate, uic…
    qt = ps / "Qt"
    for d in ("qml", "libexec", "metatypes", "resources", "mkspecs", "modules", "bin"):
        rm(qt / d)
    tr_dir = qt / "translations"
    for f in tr_dir.glob("*"):
        if f.name not in ("qtbase_es.qm",):
            rm(f)
    plug = qt / "plugins"
    for d in plug.iterdir():
        keep = QT_PLUGINS_KEEP.get(d.name, False)
        if keep is False:
            rm(d)
        elif keep is not None:
            for f in d.iterdir():
                if f.name not in keep:
                    rm(f)
    # Cierre de dependencias: solo las bibliotecas Qt que hacen falta
    libdir = qt / "lib"
    roots = [p for p in ps.glob("*.so")] + [p for p in plug.rglob("*.so")]
    roots += list((ps.parent / "shiboken6").glob("*.so*"))
    want: set[str] = set()
    todo = list(roots)
    while todo:
        f = todo.pop()
        for n in needed(f):
            cand = libdir / n
            if cand.exists() and n not in want:
                want.add(n)
                todo.append(cand)
    for f in libdir.iterdir():
        if f.name not in want and f.name.startswith("libQt6"):
            rm(f)
    print("Qt libs kept:", sorted(want))


def build():
    rm(BUILD)
    APPDIR.mkdir(parents=True)
    usr = APPDIR / "usr"
    usr.mkdir()

    py = build_python(usr)

    # Aplicación
    app = usr / "app"
    app.mkdir()
    shutil.copy2(ROOT / "run.py", app / "run.py")
    for pkg in ("tuxenc", "retitler"):
        shutil.copytree(ROOT / pkg, app / pkg, ignore=shutil.ignore_patterns("__pycache__", "*.pyc",
                                                                              "_builtin_keys.py",
                                                                              "_build_info.py"))
    keys = builtin_keys_from_env()
    # Compilación oficial (CI): sin las claves de TMDB y TheTVDB, mejor fallar que publicar sin ellas
    required = {k.strip() for k in os.environ.get("TUXENC_REQUIRE_KEYS", "").split(",") if k.strip()}
    if required - keys.keys():
        sys.exit(f"Faltan claves integradas: {', '.join(sorted(required - keys.keys()))}")
    from tuxenc.builtin_keys import render_module
    (app / "tuxenc" / "_builtin_keys.py").write_text(render_module(keys))
    print("claves integradas:", ", ".join(sorted(keys)) or "ninguna (cada usuario pondrá las suyas)")
    # De dónde sale esta compilación («Acerca de»): GitHub Actions (oficial) o local
    import time as _time
    from tuxenc.build_info import render_module as render_info
    built = _time.strftime("%Y-%m-%d %H:%M UTC", _time.gmtime())
    (app / "tuxenc" / "_build_info.py").write_text(render_info(dict(os.environ), built))
    print("compilación:", "GitHub Actions" if os.environ.get("GITHUB_ACTIONS") == "true" else "local")

    # FFmpeg (binarios + bibliotecas compartidas, RPATH=$ORIGIN/../lib)
    ff = usr / "ffmpeg"
    (ff / "bin").mkdir(parents=True)
    for b in ("ffmpeg", "ffprobe"):
        shutil.copy2(FF_SRC / "bin" / b, ff / "bin" / b)
    shutil.copytree(FF_SRC / "lib", ff / "lib", symlinks=True,
                    ignore=shutil.ignore_patterns("pkgconfig", "*.so"))
    shutil.copy2(FF_SRC / "LICENSE.txt", ff / "LICENSE.txt")

    # Bibliotecas X11 que faltan en algunas distros (sobre todo libxcb-cursor)
    lib = usr / "lib"
    lib.mkdir()
    shutil.copy2(XCB_CURSOR / "libxcb-cursor.so.0.0.0", lib / "libxcb-cursor.so.0")
    for name in BUNDLED_SYS_LIBS:
        shutil.copy2(SYS_LIBDIR / name, lib / name, follow_symlinks=True)

    # Precompilar .pyc (el AppImage es de solo lectura)
    run([py / "bin" / "python3.12", "-m", "compileall", "-q", "-j", "0",
         py / "lib" / "python3.12", app], stdout=subprocess.DEVNULL)

    # AppRun, .desktop, icono, metainfo
    apprun = APPDIR / "AppRun"
    apprun.write_text((ROOT / "packaging" / "AppRun").read_text())
    apprun.chmod(0o755)
    desktop = (ROOT / "packaging" / "tuxenc.desktop").read_text()
    (APPDIR / "tuxenc.desktop").write_text(desktop)
    shutil.copy2(ROOT / "tuxenc" / "assets" / "tuxenc-256.png", APPDIR / "tuxenc.png")
    (APPDIR / ".DirIcon").symlink_to("tuxenc.png")
    meta = usr / "share" / "metainfo"
    meta.mkdir(parents=True)
    shutil.copy2(ROOT / "packaging" / "tuxenc.appdata.xml", meta / "io.github.tuxenc.appdata.xml")
    icons = usr / "share" / "icons" / "hicolor" / "256x256" / "apps"
    icons.mkdir(parents=True)
    shutil.copy2(ROOT / "tuxenc" / "assets" / "tuxenc-256.png", icons / "tuxenc.png")
    shutil.copy2(FF_SRC / "LICENSE.txt", APPDIR / "LICENSE")

    # Empaquetar
    DIST.mkdir(exist_ok=True)
    out = DIST / f"TuxEnc-{VERSION}-x86_64.AppImage"
    rm(out)
    env = dict(os.environ, ARCH="x86_64", APPIMAGE_EXTRACT_AND_RUN="1")
    run([APPIMAGETOOL, "--appimage-extract-and-run", "--runtime-file", RUNTIME,
         "--comp", "zstd", "--mksquashfs-opt", "-Xcompression-level", "--mksquashfs-opt", "19",
         "--no-appstream", APPDIR, out], env=env)
    out.chmod(0o755)
    make_zip(out)


def make_zip(appimage: Path):
    folder = f"TuxEnc-{VERSION}"
    zpath = DIST / f"TuxEnc-{VERSION}-linux-x86_64.zip"
    rm(zpath)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        def add(src: Path, name: str, mode: int):
            info = zipfile.ZipInfo(f"{folder}/{name}")
            info.date_time = (2026, 11, 16, 12, 0, 0)
            info.create_system = 3                      # Unix: conserva los permisos
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(src, "rb") as fh:
                z.writestr(info, fh.read())
        add(appimage, appimage.name, 0o755)
        add(ROOT / "README.md", "README.md", 0o644)
        add(ROOT / "LICENSE", "LICENSE.txt", 0o644)
        add(ROOT / "CHANGELOG.md", "CHANGELOG.md", 0o644)
    print("ZIP:", zpath, f"{zpath.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    build()
