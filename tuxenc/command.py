"""Selección de pistas y construcción de los comandos de FFmpeg."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field

from .catalog import (AUDIO_CODECS, AUDIO_COPY_OK, AUDIO_FALLBACK, CONTAINERS, TEXT_SUB_CODECS,
                      EncodeSettings, encoder, fit_size)
from .paths import clean_env, ffmpeg_bin
from .probe import MediaInfo, Stream


# --------------------------------------------------------------------------- pistas

def _match_langs(streams: list[Stream], langs: list[str]) -> list[Stream]:
    """Pistas cuyo idioma está en la lista, ordenadas según la preferencia.

    Lista vacía = cualquier idioma (todas las pistas, en su orden original)."""
    if not langs:
        return list(streams)
    out = []
    for lang in langs:
        out.extend(s for s in streams if s.lang == lang and s not in out)
    return out


def select_audio(info: MediaInfo, st: EncodeSettings) -> list[Stream]:
    tracks = info.audio
    if not tracks or st.audio_mode == "none":
        return []
    if st.audio_mode == "all":
        return list(tracks)
    matched = _match_langs(tracks, st.audio_langs)
    if not matched:
        # Ningún idioma preferido: la pista por defecto o la primera
        default = [s for s in tracks if s.default]
        return [default[0] if default else tracks[0]]
    if st.audio_mode == "first":
        return [matched[0]]
    return matched  # lang_all


def _sub_fits_container(s: Stream, container: str) -> bool:
    if container == "mkv":
        return True
    return s.codec in TEXT_SUB_CODECS  # mp4 / webm solo admiten texto


def select_subtitles(info: MediaInfo, st: EncodeSettings) -> tuple[list[Stream], Stream | None]:
    """Devuelve (pistas a incluir como subtítulos, pista a incrustar en la imagen)."""
    subs = info.subtitles
    burn = None
    if subs and st.sub_burn != "none":
        pool = _match_langs(subs, st.sub_langs)
        if st.sub_burn == "forced":
            forced = [s for s in pool if s.forced] or [s for s in subs if s.forced]
            burn = forced[0] if forced else None
        elif pool:
            burn = pool[0]

    if not subs or st.sub_mode == "none":
        chosen = []
    elif st.sub_mode == "all":
        chosen = list(subs)
    else:
        matched = _match_langs(subs, st.sub_langs)
        if st.sub_mode == "forced":
            chosen = [s for s in matched if s.forced]
        elif st.sub_mode == "first":
            chosen = matched[:1]
        else:
            chosen = matched
    chosen = [s for s in chosen if s is not burn and _sub_fits_container(s, st.container)]
    return chosen, burn


# --------------------------------------------------------------------------- recorte

_CROP_RE = re.compile(r"crop=(\d+):(\d+):(\d+):(\d+)")


def detect_crop(info: MediaInfo, timeout: float = 120) -> str | None:
    """Detecta bandas negras muestreando varios puntos del vídeo. Devuelve 'w:h:x:y'."""
    v = info.main_video
    if not v or not v.width or not v.height:
        return None
    dur = info.duration or 0
    points = [dur * p for p in (0.1, 0.25, 0.4, 0.55, 0.7, 0.85)] if dur > 20 else [0]
    boxes = []
    for t in points:
        cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-ss", f"{t:.2f}", "-i", info.path,
               "-map", f"0:{v.index}", "-vf", "cropdetect=limit=24:round=2:reset=0",
               "-frames:v", "24", "-an", "-sn", "-f", "null", "-"]
        try:
            res = subprocess.run(cmd, env=clean_env(), capture_output=True, text=True,
                                 timeout=timeout, check=False)
        except (OSError, subprocess.SubprocessError):
            continue
        found = _CROP_RE.findall(res.stderr or "")
        if found:
            boxes.append(tuple(int(x) for x in found[-1]))
    if not boxes:
        return None
    # Unión de todas las cajas: así una escena oscura no recorta de más
    x1 = min(b[2] for b in boxes)
    y1 = min(b[3] for b in boxes)
    x2 = max(b[2] + b[0] for b in boxes)
    y2 = max(b[3] + b[1] for b in boxes)
    w, h = x2 - x1, y2 - y1
    w -= w % 2
    h -= h % 2
    if w <= 0 or h <= 0 or w * h < 0.5 * v.width * v.height:
        return None
    if w >= v.width - 4 and h >= v.height - 4:
        return None
    return f"{w}:{h}:{x1}:{y1}"


# --------------------------------------------------------------------------- comando

_DENOISE = {"light": "hqdn3d=2:1:3:3", "medium": "hqdn3d=3:2:4:4", "strong": "hqdn3d=7:7:5:5"}


def render_node(hw: str = "vaapi") -> str:
    from .gpus import render_node as _rn
    return _rn(hw)


def qsv_device_args() -> list[str]:
    """Inicializa QSV sobre la gráfica Intel (y no sobre otra que pueda ir primero)."""
    return ["-init_hw_device", f"qsv=hw:hw,child_device={render_node('qsv')}",
            "-filter_hw_device", "hw"]


def _safe_path_for_filter(path: str, link_dir: str, job_id: int) -> str:
    """Los filtros de FFmpeg son quisquillosos con ':' ',' '[' etc. Usamos un enlace con nombre seguro."""
    if re.fullmatch(r"[A-Za-z0-9_./-]+", path):
        return path
    for base in (link_dir, f"/tmp/tuxenc-{os.getuid()}"):
        if re.fullmatch(r"[A-Za-z0-9_./-]+", base):
            os.makedirs(base, exist_ok=True)
            ext = os.path.splitext(path)[1] if re.fullmatch(r"\.[A-Za-z0-9]+",
                                                            os.path.splitext(path)[1]) else ".mkv"
            link = os.path.join(base, f"sub-{job_id}{ext}")
            try:
                if os.path.lexists(link):
                    os.remove(link)
                os.symlink(path, link)
                return link
            except OSError:
                continue
    return path


@dataclass
class Plan:
    """Lo que se va a hacer con un archivo."""

    passes: list = field(default_factory=list)   # lista de listas de argumentos
    audio: list = field(default_factory=list)
    subtitles: list = field(default_factory=list)
    burn: Stream | None = None
    crop: str | None = None
    video_copied: bool = False      # el vídeo se copia sin recomprimir
    src_kbps: int = 0               # bitrate del vídeo original (si se conoce)


def _audio_args(i: int, s: Stream, st: EncodeSettings) -> list[str]:
    container = st.container
    codec = st.audio_codec
    if codec == "copy":
        allowed = AUDIO_COPY_OK[container]
        if allowed is None or s.codec in allowed:
            return [f"-c:a:{i}", "copy"]
        codec = AUDIO_FALLBACK[container]
    enc = AUDIO_CODECS[codec]["ffmpeg"]
    src_ch = s.channels or 2
    if st.audio_mixdown == "stereo":
        ch = min(2, src_ch)
    elif st.audio_mixdown == "5.1":
        ch = 6 if src_ch >= 6 else src_ch
    else:
        ch = src_ch
    if codec in ("ac3", "eac3"):
        ch = min(ch, 6)
    if codec == "mp3":
        ch = min(ch, 2)
    ch = min(ch, 8)
    args = [f"-c:a:{i}", enc]
    if ch != src_ch:
        args += [f"-ac:a:{i}", str(ch)]
    if codec == "opus":
        args += [f"-filter:a:{i}", "aformat=channel_layouts=7.1|5.1|stereo|mono"]
    if codec != "flac":
        br = st.audio_bitrate
        if not br:
            table = {
                "aac": {1: 96, 2: 160, 6: 384, 8: 512},
                "opus": {1: 64, 2: 128, 6: 256, 8: 384},
                "ac3": {1: 96, 2: 224, 6: 448},
                "eac3": {1: 96, 2: 224, 6: 448},
                "mp3": {1: 128, 2: 192},
            }[codec]
            br = table.get(ch) or table[min(table, key=lambda k: abs(k - ch))]
        if codec in ("ac3", "eac3"):
            br = min(br, 640)
        if codec == "mp3":
            br = min(br, 320)
        args += [f"-b:a:{i}", f"{br}k"]
    return args


def _sub_codec(s: Stream, container: str) -> str:
    if container == "mp4":
        return "mov_text"
    if container == "webm":
        return "webvtt"
    if s.codec in ("mov_text", "tx3g"):
        return "srt"
    return "copy"


def _video_rate_args(st: EncodeSettings, threads: int) -> tuple[list[str], list[str]]:
    """Argumentos del codificador de vídeo y parámetros extra para x265."""
    enc = encoder(st.video_encoder)
    a: list[str] = ["-c:v", enc.id]
    x265 = ["log-level=error", f"pools={threads}"]
    q, br = st.quality, st.bitrate
    mode = st.rate_mode

    if enc.id in ("libx264", "libx265"):
        a += ["-preset", st.speed_preset]
        if mode == "cq":
            a += ["-crf", str(q)]
        elif mode == "abr":
            a += ["-b:v", f"{br}k"]
        else:
            a += ["-b:v", f"{br}k", "-maxrate", f"{br}k", "-bufsize", f"{br * 2}k"]
            if enc.id == "libx264":
                a += ["-x264-params", "nal-hrd=cbr"]
    elif enc.id == "libsvtav1":
        a += ["-preset", st.speed_preset]
        if mode == "cq":
            a += ["-crf", str(q)]
        elif mode == "abr":
            a += ["-b:v", f"{br}k"]
        else:
            a += ["-b:v", f"{br}k"]
        # SVT-AV1 solo admite CBR en modo de baja latencia
        a += ["-svtav1-params", "rc=2:pred-struct=1" if mode == "cbr" else "tune=0"]
    elif enc.id == "libvpx-vp9":
        a += ["-deadline", "good", "-cpu-used", st.speed_preset, "-row-mt", "1"]
        if mode == "cq":
            a += ["-crf", str(q), "-b:v", "0"]
        elif mode == "abr":
            a += ["-b:v", f"{br}k"]
        else:
            a += ["-b:v", f"{br}k", "-minrate", f"{br}k", "-maxrate", f"{br}k"]
    elif enc.hw == "nvenc":
        a += ["-preset", st.speed_preset, "-tune", "hq"]
        if mode == "cq":
            a += ["-rc", "vbr", "-cq", str(q), "-b:v", "0"]
        elif mode == "abr":
            a += ["-rc", "vbr", "-b:v", f"{br}k", "-maxrate", f"{br * 2}k"]
        else:
            a += ["-rc", "cbr", "-b:v", f"{br}k"]
        if st.two_pass and mode != "cq":
            a += ["-multipass", "fullres"]
    elif enc.hw == "qsv":
        a += ["-preset", st.speed_preset]
        if mode == "cq":
            a += ["-global_quality", str(q)]
        elif mode == "abr":
            a += ["-b:v", f"{br}k"]
        else:
            a += ["-b:v", f"{br}k", "-maxrate", f"{br}k"]
    elif enc.hw == "vaapi":
        if mode == "cq":
            a += ["-rc_mode", "CQP", "-qp", str(q)]
        elif mode == "abr":
            a += ["-rc_mode", "VBR", "-b:v", f"{br}k", "-maxrate", f"{br * 2}k"]
        else:
            a += ["-rc_mode", "CBR", "-b:v", f"{br}k", "-maxrate", f"{br}k"]

    if not enc.hw:
        a += ["-threads", str(threads)]
        if st.bit_depth == 10:
            a += ["-pix_fmt", "yuv420p10le"]
        else:
            a += ["-pix_fmt", "yuv420p"]
    elif enc.hw == "nvenc":
        a += ["-pix_fmt", "p010le" if st.bit_depth == 10 else "yuv420p"]
    return a, x265


# Códecs modernos que se pueden copiar tal cual en cada contenedor
COPYABLE = {"mkv": {"h264", "hevc", "av1", "vp9"}, "mp4": {"h264", "hevc", "av1", "vp9"},
            "webm": {"vp9", "av1"}}


def video_copy_check(info: MediaInfo, st: EncodeSettings, crop: str | None = None,
                     burn: Stream | None = None) -> tuple[bool, int]:
    """¿Se puede copiar el vídeo en vez de recomprimirlo? (sí/no, kbps del original).

    Solo con bitrate medio o constante, si el original ya tiene MENOS bitrate que el pedido
    (recomprimirlo lo haría crecer y perder calidad), y si no hay que tocar la imagen.
    """
    v = info.main_video
    src = info.video_kbps
    if not (st.copy_if_lower and st.rate_mode in ("abr", "cbr") and v and src):
        return False, src
    if src > st.bitrate or v.codec not in COPYABLE.get(st.container, set()):
        return False, src
    w, h = (int(x) for x in crop.split(":")[:2]) if crop else (v.width, v.height)
    touches_picture = (crop or burn is not None or st.deinterlace in ("yadif", "bwdif")
                       or st.denoise in _DENOISE or st.framerate != "source"
                       or fit_size(w, h, st.max_height, st.allow_upscale) is not None)
    return (not touches_picture), src


def build_plan(info: MediaInfo, st: EncodeSettings, output: str, *, threads: int = 4,
               crop: str | None = None, job_id: int = 0, work_dir: str = "/tmp",
               audio_override: list[int] | None = None,
               sub_override: list[int] | None = None,
               burn_override: int | None = None,
               metadata: dict | None = None) -> Plan:
    """Construye las pasadas de FFmpeg. Los *_override (índices absolutos) sustituyen a las reglas."""
    st = st.copy()
    enc = encoder(st.video_encoder)
    v = info.main_video
    plan = Plan(crop=crop)

    # ---- pistas
    if audio_override is not None:
        plan.audio = [s for s in info.audio if s.index in audio_override]
    else:
        plan.audio = select_audio(info, st)
    subs, burn = select_subtitles(info, st)
    if sub_override is not None:
        subs = [s for s in info.subtitles if s.index in sub_override
                and _sub_fits_container(s, st.container)]
    if burn_override is not None:
        burn = next((s for s in info.subtitles if s.index == burn_override), None)
        subs = [s for s in subs if s is not burn]
    plan.subtitles, plan.burn = subs, burn

    copy_video, plan.src_kbps = video_copy_check(info, st, crop, burn)
    plan.video_copied = copy_video

    # ---- dispositivos hardware
    pre: list[str] = []
    if copy_video:
        pass
    elif enc.hw == "vaapi":
        pre += ["-vaapi_device", render_node("vaapi")]
    elif enc.hw == "qsv":
        pre += qsv_device_args()

    # ---- filtros de vídeo
    chain: list[str] = []
    if st.deinterlace in ("yadif", "bwdif"):
        chain.append(f"{st.deinterlace}=mode=send_frame:deint=interlaced")
    pre_crop_overlay = burn is not None and burn.bitmap
    if crop:
        chain.append(f"crop={crop}")
    if burn is not None and not burn.bitmap:
        rel = info.subtitles.index(burn)
        src = _safe_path_for_filter(info.path, work_dir, job_id)
        chain.append(f"subtitles=filename={src}:si={rel}")
    if st.denoise in _DENOISE:
        chain.append(_DENOISE[st.denoise])
    if crop:
        cur_w, cur_h = (int(x) for x in crop.split(":")[:2])
    else:
        cur_w, cur_h = (v.width, v.height) if v else (0, 0)
    size = fit_size(cur_w, cur_h, st.max_height, st.allow_upscale)
    if size:
        chain.append(f"scale={size[0]}:{size[1]}:flags=lanczos")
    if st.framerate != "source":
        chain.append(f"fps={st.framerate}")
    pix = "p010" if st.bit_depth == 10 else "nv12"
    if enc.hw == "vaapi":
        chain.append(f"format={pix},hwupload")
    elif enc.hw == "qsv":
        chain.append(f"format={pix},hwupload=extra_hw_frames=64")

    video_map: list[str]
    filter_args: list[str]
    if copy_video:
        filter_args, video_map = [], ["-map", f"0:{v.index}"]
    elif pre_crop_overlay:
        graph = f"[0:{v.index}][0:{burn.index}]overlay"
        if chain:
            graph += "," + ",".join(chain)
        graph += "[vout]"
        filter_args = ["-filter_complex", graph]
        video_map = ["-map", "[vout]"]
    else:
        filter_args = ["-vf", ",".join(chain)] if chain else []
        video_map = ["-map", f"0:{v.index}"]

    vargs, x265 = _video_rate_args(st, threads)
    cont = CONTAINERS[st.container]
    passlog = os.path.join(work_dir, f"pass-{job_id}")
    base = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", "-loglevel", "warning",
            "-nostats", "-progress", "pipe:1"]
    head = base + pre + ["-threads", str(threads), "-i", info.path]

    two_pass = (st.two_pass and st.rate_mode != "cq" and not enc.hw and enc.supports_2pass
                and not copy_video)

    def video_part(pass_no: int | None) -> list[str]:
        if copy_video:
            args = ["-c:v", "copy"]
            if v.codec == "hevc" and st.container == "mp4":
                args += ["-tag:v", "hvc1"]
            return args
        args = list(vargs)
        xp = list(x265)
        if pass_no:
            if enc.id == "libx265":
                xp += [f"pass={pass_no}", f"stats={passlog}.log"]
            else:
                args += ["-pass:v", str(pass_no), "-passlogfile:v", passlog]
        if enc.id == "libx265":
            args += ["-x265-params", ":".join(xp)]
        if enc.codec == "hevc" and st.container == "mp4":
            args += ["-tag:v", "hvc1"]
        return args

    # ---- pasada final (o única)
    final = head + filter_args + video_map
    for s in plan.audio:
        final += ["-map", f"0:{s.index}"]
    for s in plan.subtitles:
        final += ["-map", f"0:{s.index}"]
    if st.container == "mkv" and info.has_attachments:
        final += ["-map", "0:t?", "-c:t", "copy"]
    final += video_part(2 if two_pass else None)
    for i, s in enumerate(plan.audio):
        final += _audio_args(i, s, st)
        final += [f"-disposition:a:{i}", "default" if i == 0 else "0"]
    for j, s in enumerate(plan.subtitles):
        final += [f"-c:s:{j}", _sub_codec(s, st.container)]
        disp = "0"
        if s.forced:
            disp = "default+forced" if st.sub_mode == "forced" else "forced"
        final += [f"-disposition:s:{j}", disp]
    final += ["-map_metadata", "0", "-map_chapters", "0" if st.keep_chapters else "-1"]
    for key, value in (metadata or {}).items():
        if value not in (None, ""):
            final += ["-metadata", f"{key}={value}"]
    if st.container == "mp4":
        final += ["-movflags", "+faststart"]
    final += ["-f", cont["format"], output]

    if two_pass:
        first = head + filter_args + video_map + video_part(1) + ["-an", "-sn", "-f", "null",
                                                                  os.devnull]
        plan.passes = [first, final]
    else:
        plan.passes = [final]
    return plan
