"""Análisis de archivos de vídeo con ffprobe."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field

from .catalog import BITMAP_SUB_CODECS, norm_lang
from .paths import clean_env, ffprobe_bin

VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".m4v", ".avi", ".mov", ".webm", ".wmv", ".flv", ".ts", ".m2ts",
    ".mts", ".mpg", ".mpeg", ".vob", ".ogv", ".3gp", ".divx", ".asf", ".f4v", ".rmvb",
}


@dataclass
class Stream:
    index: int                  # índice absoluto en el archivo
    kind: str                   # video | audio | subtitle
    codec: str
    lang: str = "und"
    title: str = ""
    channels: int = 0
    layout: str = ""
    width: int = 0
    height: int = 0
    fps: float = 0.0
    sar: float = 1.0               # relación de aspecto del píxel (DVD anamórfico ≠ 1)
    bitrate: int = 0               # kbps (0 = desconocido)
    default: bool = False
    forced: bool = False
    hearing_impaired: bool = False

    @property
    def bitmap(self) -> bool:
        return self.codec in BITMAP_SUB_CODECS


@dataclass
class MediaInfo:
    path: str
    duration: float = 0.0
    size: int = 0
    video: list = field(default_factory=list)
    audio: list = field(default_factory=list)
    subtitles: list = field(default_factory=list)
    has_attachments: bool = False
    bitrate: int = 0                       # kbps del archivo entero (0 = desconocido)

    @property
    def video_kbps(self) -> int:
        """Bitrate del vídeo principal en kbps (0 si no se puede saber).

        MKV no suele indicarlo por pista: se calcula con el total menos el audio."""
        v = self.main_video
        if v and v.bitrate:
            return v.bitrate
        total = self.bitrate or (int(self.size * 8 / self.duration / 1000)
                                 if self.size and self.duration else 0)
        if not total:
            return 0
        audio = sum(a.bitrate or (128 if a.channels <= 2 else 384) for a in self.audio)
        return max(0, total - audio)

    @property
    def main_video(self) -> Stream | None:
        return self.video[0] if self.video else None

    @property
    def std_resolution(self) -> str:
        """Resolución estándar (1080p…) del vídeo principal, según las dimensiones de visualización."""
        from .catalog import resolution_label
        v = self.main_video
        return resolution_label(v.width, v.height, v.sar) if v else ""

    def summary(self) -> str:
        parts = []
        v = self.main_video
        if v:
            parts.append(f"{v.width}×{v.height}")
            parts.append(v.codec.upper())
        if self.duration:
            parts.append(format_duration(self.duration))
        if self.audio:
            parts.append(f"♪{len(self.audio)}")
        if self.subtitles:
            parts.append(f"CC{len(self.subtitles)}")
        return " · ".join(parts)


class ProbeError(Exception):
    pass


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fps(rate: str | None) -> float:
    try:
        num, den = (rate or "0/1").split("/")
        return float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def _kbps(value) -> int:
    try:
        return int(int(str(value).strip()) / 1000)
    except (TypeError, ValueError):
        return 0


# Contenedores que declaran todas sus pistas en la cabecera: basta con leer 1 MB (por defecto
# ffprobe lee hasta 5 MB, y en un NAS con miles de vídeos eso satura la red de 1 Gbps).
LIGHT_PROBE_EXTS = {".mkv", ".mp4", ".m4v", ".mov", ".webm"}
LIGHT_PROBE = ["-probesize", "1000000", "-analyzeduration", "1000000"]


def _ffprobe(path: str, timeout: float, light: bool) -> dict:
    cmd = [ffprobe_bin(), "-v", "error", "-hide_banner", *(LIGHT_PROBE if light else []),
           "-print_format", "json", "-show_format", "-show_streams", path]
    try:
        res = subprocess.run(cmd, env=clean_env(), capture_output=True, text=True,
                             timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProbeError(str(exc)) from exc
    if res.returncode != 0:
        raise ProbeError(res.stderr.strip().splitlines()[-1] if res.stderr.strip() else "ffprobe")
    try:
        return json.loads(res.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ProbeError(str(exc)) from exc


def _complete(data: dict) -> bool:
    """¿Tiene el análisis ligero todo lo que hace falta? Si no, se repite completo."""
    streams = data.get("streams") or []
    try:
        if float((data.get("format") or {}).get("duration") or 0) <= 0:
            return False
    except (TypeError, ValueError):
        return False
    videos = [s for s in streams if s.get("codec_type") == "video"
              and not (s.get("disposition") or {}).get("attached_pic")]
    if not videos:
        return False
    for s in streams:
        kind = s.get("codec_type")
        if kind in ("video", "audio", "subtitle") and not s.get("codec_name"):
            return False
        if kind == "video" and s in videos and not (s.get("width") and s.get("height")):
            return False
        if kind == "audio" and not (s.get("channels") and s.get("sample_rate")):
            return False
    return True


def probe(path: str, timeout: float = 60, measure_audio: bool = True) -> MediaInfo:
    """Analiza un vídeo (solo la cabecera). Con measure_audio=False no mide el bitrate del audio
    que no lo declara: eso lee los 2 primeros minutos del archivo y se deja para cuando se
    vaya a convertir (ensure_audio_measured). Al añadir cientos de vídeos de un NAS, leerlos
    enteros de entrada sobraba, sobre todo si solo se van a renombrar."""
    light = os.path.splitext(path)[1].lower() in LIGHT_PROBE_EXTS
    data = _ffprobe(path, timeout, light)
    if light and not _complete(data):           # algo quedó a medias: análisis completo
        data = _ffprobe(path, timeout, False)

    fmt = data.get("format", {})
    info = MediaInfo(path=path)
    try:
        info.duration = float(fmt.get("duration") or 0)
    except ValueError:
        info.duration = 0.0
    info.bitrate = _kbps(fmt.get("bit_rate"))
    try:
        info.size = int(fmt.get("size") or 0)
    except ValueError:
        info.size = 0

    for st in data.get("streams", []):
        kind = st.get("codec_type")
        tags = {k.lower(): v for k, v in (st.get("tags") or {}).items()}
        disp = st.get("disposition") or {}
        if kind == "attachment":
            info.has_attachments = True
            continue
        if kind == "video" and disp.get("attached_pic"):
            continue  # carátulas
        if kind not in ("video", "audio", "subtitle"):
            continue
        s = Stream(
            index=int(st.get("index", 0)),
            kind=kind,
            codec=(st.get("codec_name") or "unknown"),
            lang=norm_lang(tags.get("language")),
            title=tags.get("title", ""),
            channels=int(st.get("channels") or 0),
            layout=st.get("channel_layout", "") or "",
            width=int(st.get("width") or 0),
            height=int(st.get("height") or 0),
            fps=_fps(st.get("avg_frame_rate")) or _fps(st.get("r_frame_rate")),
            sar=_fps((st.get("sample_aspect_ratio") or "1:1").replace(":", "/")) or 1.0,
            bitrate=_kbps(st.get("bit_rate") or tags.get("bps") or tags.get("bps-eng")),
            default=bool(disp.get("default")),
            forced=bool(disp.get("forced")) or "forced" in tags.get("title", "").lower(),
            hearing_impaired=bool(disp.get("hearing_impaired")),
        )
        if kind == "video":
            info.video.append(s)
            if not info.duration:
                try:
                    info.duration = float(st.get("duration") or 0)
                except ValueError:
                    pass
        elif kind == "audio":
            info.audio.append(s)
        else:
            info.subtitles.append(s)

    if not info.video:
        raise ProbeError("no_video")
    if measure_audio:
        ensure_audio_measured(info)
    return info


def ensure_audio_measured(info: MediaInfo) -> None:
    """Mide (una sola vez) el bitrate de las pistas de audio que no lo declaran."""
    if getattr(info, "_audio_measured", False):
        return
    if any(not a.bitrate for a in info.audio):
        _measure_audio(info)
    try:
        info._audio_measured = True
    except AttributeError:
        pass


def _measure_audio(info: MediaInfo, seconds: int = 120, timeout: float = 20) -> None:
    """Bitrate de las pistas de audio que no lo declaran (MKV sin etiquetas BPS): se suman los
    paquetes de los primeros minutos. Sirve para decidir si copiar el audio (y el vídeo) en vez de
    recomprimir. Si falla, se deja como estaba (desconocido)."""
    missing = {a.index: a for a in info.audio if not a.bitrate}
    cmd = [ffprobe_bin(), "-v", "error", "-read_intervals", f"%+{seconds}", "-select_streams", "a",
           "-show_entries", "packet=stream_index,pts_time,duration_time,size", "-of", "csv=p=0",
           info.path]
    try:
        res = subprocess.run(cmd, env=clean_env(), capture_output=True, text=True,
                             timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return
    if res.returncode != 0:
        return
    size: dict[int, int] = {}
    first: dict[int, float] = {}
    last: dict[int, float] = {}
    for line in res.stdout.splitlines():
        parts = line.split(",")
        if len(parts) < 4:
            continue
        try:
            idx = int(parts[0])
            pts = float(parts[1])
            dur = float(parts[2]) if parts[2] not in ("", "N/A") else 0.0
            n = int(parts[3])
        except ValueError:
            continue
        if idx not in missing:
            continue
        size[idx] = size.get(idx, 0) + n
        first.setdefault(idx, pts)
        last[idx] = pts + dur
    for idx, a in missing.items():
        span = last.get(idx, 0) - first.get(idx, 0)
        if span >= 5 and size.get(idx):
            a.bitrate = int(round(size[idx] * 8 / span / 1000))
