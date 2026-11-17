"""Configuración persistente y almacén de las claves de API (TMDB y OMDb).

* Ajustes (idioma, plantillas):  ~/.config/tuxenc/renombrado/config.json
* Claves (TMDB y OMDb), por orden de prioridad:
    1. variable de entorno TMDB_API_KEY / OMDB_API_KEY
    2. llavero del sistema (KWallet / Secret Service) vía ``keyring``, si está disponible
    3. ~/.config/tuxenc/renombrado/secrets.json con permisos 600 (sin cifrar, solo legible por tu usuario)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .formatter import DEFAULT_MOVIE_TEMPLATE, DEFAULT_SERIES_TEMPLATE, validate_template

__all__ = ["KeyStore", "LANGUAGES", "Settings", "cache_dir", "config_dir", "ensure_dirs", "state_dir"]

# Dentro de TuxEnc: ~/.config/tuxenc/renombrado, ~/.cache/tuxenc/renombrado, ~/.local/state/tuxenc/renombrado
APP = "tuxenc/renombrado"
LANGUAGES = ("es", "en")


def _xdg(env: str, default: str) -> Path:
    base = os.environ.get(env)
    return (Path(base) if base else Path.home() / default) / APP


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config")


def cache_dir() -> Path:
    return _xdg("XDG_CACHE_HOME", ".cache")


def state_dir() -> Path:
    return _xdg("XDG_STATE_HOME", ".local/state")


def ensure_dirs() -> list[Path]:
    """Primer arranque: crea las carpetas y el archivo de ajustes que falten (en los siguientes no hace nada).

    Devuelve lo que ha creado. Si no se puede escribir (disco de solo lectura...), el programa sigue
    funcionando: todo lo que se guarda es opcional.
    """
    created: list[Path] = []
    for directory in (config_dir(), cache_dir() / "http", state_dir()):
        if not directory.is_dir():
            try:
                directory.mkdir(parents=True, exist_ok=True)
                created.append(directory)
            except OSError:
                pass
    settings_file = Settings.default_path()
    if not settings_file.exists():
        try:
            Settings().save(settings_file)
            created.append(settings_file)
        except OSError:
            pass
    return created


def _atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


@dataclass
class Settings:
    language: str = "es"
    series_template: str = DEFAULT_SERIES_TEMPLATE
    movie_template: str = DEFAULT_MOVIE_TEMPLATE
    skip_articles: bool = True          # {initial}: «The Batman» -> B, «El Padrino» -> P
    keep_file_title: bool = True        # si el capítulo solo tiene título en inglés, usar el del archivo

    @staticmethod
    def default_path() -> Path:
        return config_dir() / "config.json"

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Settings":
        """Lee los ajustes; si falta el archivo o un valor no es válido, usa el valor por defecto."""
        settings = cls()
        try:
            data = json.loads(Path(path or cls.default_path()).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return settings
        if not isinstance(data, dict):
            return settings
        if data.get("language") in LANGUAGES:
            settings.language = data["language"]
        for name in ("series_template", "movie_template"):
            value = data.get(name)
            if isinstance(value, str) and value.strip() and validate_template(value) is None:
                setattr(settings, name, value)
        if isinstance(data.get("skip_articles"), bool):
            settings.skip_articles = data["skip_articles"]
        if isinstance(data.get("keep_file_title"), bool):
            settings.keep_file_title = data["keep_file_title"]
        return settings

    def save(self, path: str | Path | None = None) -> None:
        data = {
            "language": self.language if self.language in LANGUAGES else "es",
            "series_template": self.series_template,
            "movie_template": self.movie_template,
            "skip_articles": self.skip_articles,
            "keep_file_title": self.keep_file_title,
        }
        _atomic_write(Path(path or self.default_path()), json.dumps(data, ensure_ascii=False, indent=2) + "\n")


_UNSET = object()


def _load_keyring():
    try:
        import keyring  # type: ignore[import-not-found]
    except Exception:
        return None
    return keyring


class KeyStore:
    """Guarda la clave de un servicio (TMDB u OMDb) de forma permanente hasta que el usuario la cambie.

    Las claves de todos los servicios comparten ``secrets.json`` (una entrada por servicio) y el
    llavero (una cuenta por servicio). ``for_service("omdb")`` devuelve el almacén de otro servicio.
    """

    SERVICE = "tuxenc"

    def __init__(self, secrets_path: str | Path | None = None, keyring_backend: object = _UNSET,
                 name: str = "tmdb") -> None:
        self._path = Path(secrets_path) if secrets_path else config_dir() / "secrets.json"
        self._kr = _load_keyring() if keyring_backend is _UNSET else keyring_backend
        self.name = name
        self.ACCOUNT = f"{name}_api_key"
        self.ENV = f"{name.upper()}_API_KEY"

    def for_service(self, name: str) -> "KeyStore":
        return KeyStore(self._path, self._kr, name)

    # -- archivo ---------------------------------------------------------- #
    def _read_file(self) -> dict:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_file(self, data: dict) -> None:
        if data:
            _atomic_write(self._path, json.dumps(data) + "\n")
        else:
            self._path.unlink(missing_ok=True)

    # -- lectura ---------------------------------------------------------- #
    def _keyring_get(self) -> str | None:
        if not self._kr:
            return None
        try:
            return (self._kr.get_password(self.SERVICE, self.ACCOUNT) or "").strip() or None
        except Exception:
            return None

    def _file_get(self) -> str | None:
        return str(self._read_file().get(self.ACCOUNT, "")).strip() or None

    def get(self) -> str | None:
        env = os.environ.get(self.ENV, "").strip()
        return env or self._keyring_get() or self._file_get()

    def source(self) -> str | None:
        """De dónde sale la clave ahora mismo: 'env', 'keyring', 'file' o None."""
        if os.environ.get(self.ENV, "").strip():
            return "env"
        if self._keyring_get():
            return "keyring"
        if self._file_get():
            return "file"
        return None

    # -- escritura -------------------------------------------------------- #
    def set(self, key: str) -> str:
        """Guarda la clave. Devuelve dónde quedó: 'keyring' o 'file'."""
        key = key.strip()
        if not key:
            raise ValueError("La clave está vacía")
        data = self._read_file()
        if self._kr:
            try:
                self._kr.set_password(self.SERVICE, self.ACCOUNT, key)
                stored = self._keyring_get() == key     # algunos llaveros aceptan y no guardan
            except Exception:
                stored = False
            if stored:
                if self.ACCOUNT in data:           # que no quede una copia antigua en claro
                    del data[self.ACCOUNT]
                    self._write_file(data)
                return "keyring"
        data[self.ACCOUNT] = key
        _atomic_write(self._path, json.dumps(data) + "\n")
        return "file"

    def clear(self) -> None:
        if self._kr:
            try:
                self._kr.delete_password(self.SERVICE, self.ACCOUNT)
            except Exception:
                pass
        data = self._read_file()
        if self.ACCOUNT in data:
            del data[self.ACCOUNT]
            self._write_file(data)


def legacy_retitler_keys() -> dict[str, str]:
    """Claves guardadas por Retitler independiente (para ofrecer importarlas)."""
    found: dict[str, str] = {}
    legacy_file = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "retitler" / "secrets.json"
    try:
        data = json.loads(legacy_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    kr = _load_keyring()
    for name in ("tmdb", "omdb"):
        value = ""
        if kr:
            try:
                value = (kr.get_password("retitler", f"{name}_api_key") or "").strip()
            except Exception:
                value = ""
        if not value and isinstance(data, dict):
            value = str(data.get(f"{name}_api_key", "")).strip()
        if value:
            found[name] = value
    return found
