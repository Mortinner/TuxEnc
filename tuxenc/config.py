"""Configuración persistente (~/.config/tuxenc/config.json)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .catalog import EncodeSettings
from .paths import CONFIG_DIR

CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class Config:
    ui_lang: str = "auto"               # auto | es | en
    output_mode: str = "source"         # source | folder | library
    convert_on: bool = True             # paso «Convertir»
    rename_on: bool = False             # paso «Renombrar» (identificar con TMDB/TVmaze/IMDb)
    series_root: str = ""               # biblioteca: carpeta raíz de las series
    movie_root: str = ""                # biblioteca: carpeta raíz de las películas
    original_after: str = "keep"        # keep | trash  (tras convertir y renombrar)
    retitler_import_offered: bool = False
    output_folder: str = ""
    parallel: int = 0                   # 0 = automático
    low_priority: bool = True           # nice 10 para no acaparar el equipo
    end_action: str = "notify"          # nothing | notify | quit | suspend | shutdown
    last_preset: str = "builtin:hevc_quality"
    settings: dict = field(default_factory=dict)
    integration_prompted: bool = False
    engines_notice_shown: bool = False   # aviso «buscadores listos» del primer arranque
    last_dir: str = ""
    advanced_open: bool = False
    geometry: str = ""
    update_check: bool = True           # buscar versiones nuevas al arrancar (como mucho una vez al día)
    update_last_check: float = 0.0      # última comprobación correcta (epoch)
    update_skip: str = ""               # versión que el usuario pidió saltar

    def encode_settings(self) -> EncodeSettings:
        return EncodeSettings.from_dict(self.settings) if self.settings else EncodeSettings()

    def save(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            tmp = CONFIG_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.__dict__, indent=2, ensure_ascii=False),
                           encoding="utf-8")
            os.replace(tmp, CONFIG_FILE)
        except OSError:
            pass

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cfg
        for k, v in data.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg
