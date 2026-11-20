"""Actualizaciones desde las Releases de GitHub: comprobar, descargar, verificar e instalar.

Sin Qt: lo usa tuxenc/ui/update_ctrl.py desde un hilo aparte.

- Comprobar: una petición a la API de Releases (las publicadas; ni borradores, ni «prerelease»,
  ni «-dev»). Sin red, no pasa nada.
- Descargar: el zip de la Release y su ``SHA256SUMS``, solo desde GitHub y por HTTPS.
- Verificar: el SHA-256 del zip tiene que coincidir con el de ``SHA256SUMS``; dentro, el AppImage
  de esa versión, que tiene que ser de verdad un AppImage. Si algo falla, no se toca nada.
- Instalar: el AppImage nuevo sustituye a la copia integrada (~/.local/share/tuxenc) con un
  renombrado atómico. El anterior se guarda al lado para poder volver a él. El TuxEnc abierto
  sigue funcionando (tiene montada la versión vieja) y la nueva se usa al reiniciar.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from . import APP_NAME, VERSION
from .integration import DATA_DIR, INSTALLED_APPIMAGE, version_key
from .paths import LOG_DIR

REPO = "Mortinner/TuxEnc"
DEFAULT_API = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
# Para las pruebas: otra API (p. ej. un servidor local). Ese origen se admite también por http.
API_OVERRIDE_ENV = "TUXENC_UPDATE_API"
TRUSTED_HOST_SUFFIXES = ("github.com", "githubusercontent.com")

INSTALLED = INSTALLED_APPIMAGE
PREVIOUS = DATA_DIR / f"{APP_NAME}-anterior.AppImage"
PREVIOUS_INFO = DATA_DIR / "anterior.json"
STAGING = DATA_DIR / ".actualizacion"       # mismo disco que INSTALLED: el cambio es atómico
LOG_FILE = LOG_DIR / "actualizaciones.log"

MAX_ZIP_BYTES = 600 * 1024 * 1024
MIN_FREE_BYTES = 450 * 1024 * 1024           # zip + AppImage extraído, con margen
USER_AGENT = f"{APP_NAME}/{VERSION} (+https://github.com/{REPO})"


class UpdateError(Exception):
    """Fallo con un código para el mensaje de la interfaz (``upd_err_<código>`` en i18n)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class Cancelled(Exception):
    pass


@dataclass
class Release:
    version: str
    tag: str
    page: str
    notes: str
    published: str = ""
    zip_name: str = ""
    zip_url: str = ""
    zip_size: int = 0
    sums_url: str = ""

    @property
    def installable(self) -> bool:
        return bool(self.zip_url and self.sums_url)


@dataclass
class UpdateInfo:
    current: str
    newer: list[Release] = field(default_factory=list)     # de la más nueva a la más antigua

    @property
    def latest(self) -> Release:
        return self.newer[0]


# ------------------------------------------------------------------ registro
def log(msg: str) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


# ------------------------------------------------------------------ red
def api_url() -> str:
    return os.environ.get(API_OVERRIDE_ENV, "").strip() or DEFAULT_API


def _trusted(url: str) -> bool:
    parts = urlsplit(url)
    override = os.environ.get(API_OVERRIDE_ENV, "").strip()
    if override and parts.netloc == urlsplit(override).netloc:
        return parts.scheme in ("http", "https")
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == s or host.endswith("." + s)
                                           for s in TRUSTED_HOST_SUFFIXES)


def _open(url: str, timeout: float, accept: str):
    if not _trusted(url):
        raise UpdateError("untrusted", url)
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT,
                                               "X-GitHub-Api-Version": "2022-11-28"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 (origen comprobado)
    except urllib.error.HTTPError as exc:
        raise UpdateError("http", f"HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise UpdateError("network", str(getattr(exc, "reason", exc))) from None
    if not _trusted(resp.geturl()):              # tras las redirecciones, sigue siendo GitHub
        resp.close()
        raise UpdateError("untrusted", resp.geturl())
    return resp


def _version_of(tag: str) -> str:
    v = tag[1:] if tag[:1] in ("v", "V") else tag
    return v if re.fullmatch(r"\d+\.\d+\.\d+", v) else ""


def parse_releases(data) -> list[Release]:
    """Releases publicadas y válidas, de la más nueva a la más antigua."""
    out: list[Release] = []
    for r in data if isinstance(data, list) else []:
        if not isinstance(r, dict) or r.get("draft") or r.get("prerelease"):
            continue
        version = _version_of(str(r.get("tag_name") or ""))
        if not version:
            continue
        rel = Release(version=version, tag=str(r["tag_name"]), page=str(r.get("html_url") or RELEASES_PAGE),
                      notes=str(r.get("body") or ""), published=str(r.get("published_at") or "")[:10])
        want = f"{APP_NAME}-{version}-linux-x86_64.zip"
        for a in r.get("assets") or []:
            name, url = str(a.get("name") or ""), str(a.get("browser_download_url") or "")
            if name == want:
                rel.zip_name, rel.zip_url, rel.zip_size = name, url, int(a.get("size") or 0)
            elif name == "SHA256SUMS":
                rel.sums_url = url
        out.append(rel)
    out.sort(key=lambda x: version_key(x.version), reverse=True)
    return out


def check(current: str = VERSION, timeout: float = 15.0) -> UpdateInfo | None:
    """None si ya es la última; si no, las versiones más nuevas que la actual."""
    with _open(api_url(), timeout, "application/vnd.github+json") as resp:
        try:
            data = json.loads(resp.read(5 * 1024 * 1024).decode("utf-8"))
        except (OSError, ValueError):
            raise UpdateError("bad_reply") from None
    mine = version_key(current)
    newer = [r for r in parse_releases(data) if version_key(r.version) > mine]
    log(f"comprobación: tienes {current}; " + (f"hay {', '.join(r.version for r in newer)}"
                                                if newer else "es la última"))
    return UpdateInfo(current, newer) if newer else None


# ------------------------------------------------------------------ notas
_FOOTER = re.compile(r"\n-{3,}\s*\n\*\*Descarga:\*\*.*\Z", re.S)


def release_notes(rel: Release, lang: str) -> str:
    """Notas de una Release en el idioma de la interfaz (el CHANGELOG lleva ES y, al final, EN)."""
    body = _FOOTER.sub("", rel.notes.replace("\r\n", "\n")).strip()
    es, sep, en = body.partition("### English")
    if sep:
        body = en.strip() if lang == "en" else es.strip()
    return body


def notes_markdown(info: UpdateInfo, lang: str) -> str:
    parts = []
    for rel in info.newer:
        head = f"## {APP_NAME} {rel.version}" + (f" · {rel.published}" if rel.published else "")
        parts.append(head + "\n\n" + (release_notes(rel, lang) or "—"))
    return "\n\n".join(parts)


# ------------------------------------------------------------------ descarga y verificación
def free_bytes(path: Path) -> int:
    p = path
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return 1 << 62


def _download(url: str, dest: Path, size_hint: int, progress: Callable[[int, int], None] | None,
              cancel: threading.Event | None) -> None:
    tmp = dest.with_name(dest.name + ".part")
    with _open(url, 30.0, "application/octet-stream") as resp:
        total = int(resp.headers.get("Content-Length") or 0) or size_hint
        if total > MAX_ZIP_BYTES:
            raise UpdateError("too_big", str(total))
        done = 0
        with open(tmp, "wb") as fh:
            while True:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                try:
                    chunk = resp.read(1024 * 256)
                except OSError as exc:
                    raise UpdateError("network", str(exc)) from None
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if done > MAX_ZIP_BYTES:
                    raise UpdateError("too_big", str(done))
                if progress:
                    progress(done, total)
    if total and done != total:
        raise UpdateError("incomplete", f"{done}/{total}")
    os.replace(tmp, dest)


def expected_sha256(sums_text: str, name: str) -> str:
    for line in sums_text.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[1].lstrip("*") == name and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            return parts[0].lower()
    raise UpdateError("no_checksum", name)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def is_appimage(path: Path) -> bool:
    """ELF con la marca de AppImage tipo 2 («AI\\x02» en el byte 8)."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(11)
    except OSError:
        return False
    return head[:4] == b"\x7fELF" and head[8:11] == b"AI\x02"


def extract_appimage(zip_path: Path, version: str, dest: Path) -> Path:
    member = f"{APP_NAME}-{version}/{APP_NAME}-{version}-x86_64.AppImage"
    try:
        with zipfile.ZipFile(zip_path) as z:
            if member not in z.namelist():
                raise UpdateError("bad_zip", member)
            tmp = dest.with_name(dest.name + ".part")
            with z.open(member) as src, open(tmp, "wb") as out:
                shutil.copyfileobj(src, out, 1024 * 1024)
    except (zipfile.BadZipFile, OSError) as exc:
        raise UpdateError("bad_zip", str(exc)) from None
    if not is_appimage(tmp):
        tmp.unlink(missing_ok=True)
        raise UpdateError("not_appimage")
    os.chmod(tmp, 0o755)
    os.replace(tmp, dest)
    return dest


def prepare(rel: Release, progress: Callable[[int, int], None] | None = None,
            cancel: threading.Event | None = None) -> Path:
    """Descarga y verifica: devuelve el AppImage nuevo, listo para instalar (en STAGING)."""
    if not rel.installable:
        raise UpdateError("no_assets")
    if free_bytes(STAGING) < MIN_FREE_BYTES:
        raise UpdateError("no_space")
    cleanup_staging()
    STAGING.mkdir(parents=True, exist_ok=True)
    log(f"descargando {rel.zip_name} de {rel.tag}")
    try:
        with _open(rel.sums_url, 30.0, "application/octet-stream") as resp:
            sums = resp.read(64 * 1024).decode("utf-8", "replace")
        want = expected_sha256(sums, rel.zip_name)
        zpath = STAGING / rel.zip_name
        _download(rel.zip_url, zpath, rel.zip_size, progress, cancel)
        got = sha256_of(zpath)
        if got != want:
            log(f"SHA-256 NO coincide: esperado {want}, descargado {got}")
            raise UpdateError("checksum")
        log(f"SHA-256 correcto ({got})")
        app = extract_appimage(zpath, rel.version, STAGING / f"{APP_NAME}-{rel.version}.AppImage")
        zpath.unlink(missing_ok=True)
        return app
    except Cancelled:
        log("descarga cancelada")
        cleanup_staging()
        raise
    except UpdateError as exc:
        log(f"error al preparar la actualización: {exc}")
        cleanup_staging()
        raise


def cleanup_staging() -> None:
    shutil.rmtree(STAGING, ignore_errors=True)


# ------------------------------------------------------------------ instalar y volver atrás
def can_self_update() -> bool:
    """Solo la copia integrada se actualiza sola (es la que abre el menú de aplicaciones)."""
    from .integration import running_installed_copy
    return running_installed_copy()


def previous_version() -> str:
    if not PREVIOUS.exists():
        return ""
    try:
        return str(json.loads(PREVIOUS_INFO.read_text(encoding="utf-8")).get("version") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def _write_previous_info(version: str) -> None:
    tmp = PREVIOUS_INFO.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": version}), encoding="utf-8")
    os.replace(tmp, PREVIOUS_INFO)


def install(new_appimage: Path, new_version: str, running_version: str = VERSION) -> None:
    """Pone el AppImage nuevo en su sitio y guarda el actual como «anterior»."""
    if not is_appimage(new_appimage):
        raise UpdateError("not_appimage")
    had_old = INSTALLED.exists()
    if had_old:
        os.replace(INSTALLED, PREVIOUS)
    try:
        os.replace(new_appimage, INSTALLED)
    except OSError as exc:
        if had_old:
            os.replace(PREVIOUS, INSTALLED)
        raise UpdateError("install", str(exc)) from None
    if had_old:
        _write_previous_info(running_version)
    cleanup_staging()
    log(f"instalada la {new_version} (la {running_version} queda como anterior)")


def rollback(running_version: str = VERSION) -> str:
    """Vuelve a la versión anterior (intercambia los dos AppImage). Devuelve la versión restaurada."""
    prev = previous_version()
    if not prev or not PREVIOUS.exists():
        raise UpdateError("no_previous")
    if prev == running_version:          # hay una versión nueva instalada sin reiniciar aún
        raise UpdateError("pending")
    swap = INSTALLED.with_name(INSTALLED.name + ".swap")
    os.replace(INSTALLED, swap)
    try:
        os.replace(PREVIOUS, INSTALLED)
    except OSError as exc:
        os.replace(swap, INSTALLED)
        raise UpdateError("install", str(exc)) from None
    os.replace(swap, PREVIOUS)
    _write_previous_info(running_version)
    log(f"vuelta a la {prev} (la {running_version} queda como anterior)")
    return prev
