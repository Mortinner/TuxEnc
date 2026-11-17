"""Presets incluidos, presets del usuario e importación de presets de HandBrake."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .catalog import ENCODERS_BY_ID, RES_BOX, RESOLUTIONS, EncodeSettings, encoder, norm_lang
from .paths import CONFIG_DIR

USER_PRESETS_FILE = CONFIG_DIR / "presets.json"


@dataclass
class Preset:
    key: str            # builtin:xxx | user:Nombre
    name: str
    settings: EncodeSettings
    builtin: bool = False


def _s(**kw) -> EncodeSettings:
    s = EncodeSettings(**kw)
    s.validate()
    return s


# (clave, nombre ES, nombre EN, ajustes)
_BUILTIN = [
    ("hevc_quality", "H.265 · Alta calidad (MKV)", "H.265 · High quality (MKV)",
     dict(container="mkv", video_encoder="libx265", quality=22, speed_preset="medium",
          bit_depth=10, audio_codec="copy")),
    ("hevc_1080", "H.265 · 1080p (MKV)", "H.265 · 1080p (MKV)",
     dict(container="mkv", video_encoder="libx265", quality=23, speed_preset="medium",
          bit_depth=10, max_height=1080, audio_codec="copy")),
    ("h264_compat", "H.264 · Máxima compatibilidad (MP4)", "H.264 · Maximum compatibility (MP4)",
     dict(container="mp4", video_encoder="libx264", quality=21, speed_preset="medium",
          audio_codec="aac", audio_mixdown="stereo", audio_mode="first", sub_mode="lang_all")),
    ("h264_720", "H.264 · 720p ligero (MP4)", "H.264 · Light 720p (MP4)",
     dict(container="mp4", video_encoder="libx264", quality=23, speed_preset="medium",
          max_height=720, audio_codec="aac", audio_mixdown="stereo", audio_mode="first")),
    ("av1_small", "AV1 · Tamaño reducido (MKV)", "AV1 · Small size (MKV)",
     dict(container="mkv", video_encoder="libsvtav1", quality=32, speed_preset="6",
          bit_depth=10, audio_codec="opus")),
    ("vp9_web", "VP9 · Web (WebM)", "VP9 · Web (WebM)",
     dict(container="webm", video_encoder="libvpx-vp9", quality=32, speed_preset="2",
          audio_codec="opus", audio_mixdown="stereo", audio_mode="first", sub_mode="none")),
    # GPU: solo se muestran si el equipo los tiene
    ("nvenc_hevc", "GPU NVIDIA · H.265 rápido (MKV)", "NVIDIA GPU · Fast H.265 (MKV)",
     dict(container="mkv", video_encoder="hevc_nvenc", quality=25, speed_preset="p5",
          bit_depth=10, audio_codec="copy")),
    ("nvenc_av1", "GPU NVIDIA · AV1 rápido (MKV)", "NVIDIA GPU · Fast AV1 (MKV)",
     dict(container="mkv", video_encoder="av1_nvenc", quality=32, speed_preset="p5",
          bit_depth=10, audio_codec="copy")),
    ("nvenc_h264", "GPU NVIDIA · H.264 rápido (MP4)", "NVIDIA GPU · Fast H.264 (MP4)",
     dict(container="mp4", video_encoder="h264_nvenc", quality=23, speed_preset="p5",
          audio_codec="aac", audio_mixdown="stereo")),
    ("qsv_hevc", "GPU Intel · H.265 rápido (MKV)", "Intel GPU · Fast H.265 (MKV)",
     dict(container="mkv", video_encoder="hevc_qsv", quality=25, audio_codec="copy")),
    ("vaapi_hevc", "GPU AMD/Intel (VAAPI) · H.265 rápido (MKV)",
     "AMD/Intel GPU (VAAPI) · Fast H.265 (MKV)",
     dict(container="mkv", video_encoder="hevc_vaapi", quality=25, audio_codec="copy")),
]


def builtin_presets(lang: str, available: list[str] | None) -> list[Preset]:
    out = []
    for key, es, en, kw in _BUILTIN:
        if available is not None and kw["video_encoder"] not in available:
            continue
        out.append(Preset(f"builtin:{key}", es if lang == "es" else en, _s(**kw), True))
    return out


def load_user_presets() -> list[Preset]:
    try:
        data = json.loads(USER_PRESETS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        name = str(item.get("name", "")).strip()
        if name:
            out.append(Preset(f"user:{name}", name, EncodeSettings.from_dict(item.get("settings"))))
    return out


def save_user_presets(presets: list[Preset]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = [{"name": p.name, "settings": p.settings.to_dict()} for p in presets if not p.builtin]
    tmp = USER_PRESETS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, USER_PRESETS_FILE)


# --------------------------------------------------------------------------- HandBrake

_HB_ENCODERS = {
    "x264": ("libx264", 8), "x264_10bit": ("libx264", 10),
    "x265": ("libx265", 8), "x265_10bit": ("libx265", 10), "x265_12bit": ("libx265", 10),
    "svt_av1": ("libsvtav1", 8), "svt_av1_10bit": ("libsvtav1", 10),
    "vp9": ("libvpx-vp9", 8), "vp9_10bit": ("libvpx-vp9", 10),
    "vp8": ("libvpx-vp9", 8),
    "nvenc_h264": ("h264_nvenc", 8), "nvenc_h265": ("hevc_nvenc", 8),
    "nvenc_h265_10bit": ("hevc_nvenc", 10), "nvenc_av1": ("av1_nvenc", 8),
    "nvenc_av1_10bit": ("av1_nvenc", 10),
    "qsv_h264": ("h264_qsv", 8), "qsv_h265": ("hevc_qsv", 8), "qsv_h265_10bit": ("hevc_qsv", 10),
    "qsv_av1": ("av1_qsv", 8), "qsv_av1_10bit": ("av1_qsv", 10),
    "vce_h264": ("h264_vaapi", 8), "vce_h265": ("hevc_vaapi", 8),
    "vce_h265_10bit": ("hevc_vaapi", 10), "vce_av1": ("av1_vaapi", 8),
    "mf_h264": ("libx264", 8), "mf_h265": ("libx265", 8),
    "vt_h264": ("libx264", 8), "vt_h265": ("libx265", 8), "vt_h265_10bit": ("libx265", 10),
}
_HB_AUDIO = {
    "copy": "copy", "av_aac": "aac", "fdk_aac": "aac", "fdk_haac": "aac", "ca_aac": "aac",
    "ca_haac": "aac", "opus": "opus", "ac3": "ac3", "eac3": "eac3", "flac16": "flac",
    "flac24": "flac", "mp3": "mp3", "vorbis": "opus", "true_hd": "copy",
}
_HB_NVENC_PRESETS = {"fastest": "p1", "faster": "p2", "fast": "p3", "medium": "p4",
                     "slow": "p5", "slower": "p6", "slowest": "p7"}


def _flatten(items) -> list[dict]:
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        # HandBrake 1.8+ pone "ChildrenArray": [] también en los presets normales:
        # solo es carpeta si lo dice "Folder" (o si no tiene ajustes de vídeo).
        is_folder = bool(it.get("Folder")) or (bool(it.get("ChildrenArray"))
                                                and "VideoEncoder" not in it)
        if is_folder:
            out.extend(_flatten(it.get("ChildrenArray")))
        elif "PresetName" in it:
            out.append(it)
    return out


def import_handbrake(path: str) -> list[Preset]:
    """Convierte un archivo de presets exportado desde HandBrake (JSON)."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    raw = data.get("PresetList", data) if isinstance(data, dict) else data
    if isinstance(raw, dict):
        raw = [raw]
    result = []
    for hb in _flatten(raw):
        s = EncodeSettings()
        fmt = str(hb.get("FileFormat", "av_mkv"))
        s.container = {"av_mp4": "mp4", "av_mkv": "mkv", "av_webm": "webm"}.get(fmt, "mkv")
        enc_id, depth = _HB_ENCODERS.get(str(hb.get("VideoEncoder", "x264")), ("libx264", 8))
        s.video_encoder, s.bit_depth = enc_id, depth
        enc = encoder(enc_id)
        qtype = int(hb.get("VideoQualityType", 2) or 2)
        # La calidad se importa siempre (HandBrake la guarda aunque el preset use bitrate)
        try:
            s.quality = int(round(float(hb.get("VideoQualitySlider", enc.q_default))))
        except (TypeError, ValueError):
            s.quality = enc.q_default
        if qtype == 2:
            s.rate_mode = "cq"
        else:
            s.rate_mode = "abr"
            s.bitrate = int(hb.get("VideoAvgBitrate") or 3000)
            s.two_pass = bool(hb.get("VideoMultiPass", hb.get("VideoTwoPass", False)))
        preset = str(hb.get("VideoPreset", "") or "")
        if enc.hw == "nvenc":
            preset = _HB_NVENC_PRESETS.get(preset, preset)
        if preset in enc.presets:
            s.speed_preset = preset
        # imagen
        try:
            w = int(hb.get("PictureWidth") or 0)
            h = int(hb.get("PictureHeight") or 0)
        except (TypeError, ValueError):
            w = h = 0
        if h:
            # El mayor recuadro estándar que cabe en el tamaño máximo del preset
            fits = [r for r in RESOLUTIONS if r and RES_BOX[r][1] <= h
                    and (not w or RES_BOX[r][0] <= w)]
            s.max_height = max(fits) if fits else 0
        s.allow_upscale = bool(hb.get("PictureAllowUpscaling", False))
        fr = str(hb.get("VideoFramerate", "auto"))
        s.framerate = fr if fr not in ("auto", "") else "source"
        deint = str(hb.get("PictureDeinterlaceFilter", "off"))
        s.deinterlace = {"yadif": "yadif", "bwdif": "bwdif", "decomb": "bwdif"}.get(deint, "off")
        dn = str(hb.get("PictureDenoiseFilter", "off"))
        if dn in ("hqdn3d", "nlmeans"):
            p = str(hb.get("PictureDenoisePreset", "medium"))
            s.denoise = {"ultralight": "light", "light": "light", "medium": "medium",
                         "strong": "strong"}.get(p, "medium")
        crop_mode = hb.get("PictureCropMode")
        if crop_mode is not None:
            s.autocrop = int(crop_mode) in (0, 1)
        elif "PictureAutoCrop" in hb:
            s.autocrop = bool(hb.get("PictureAutoCrop"))
        # audio
        # "any" (o lista vacía) = cualquier idioma -> lista vacía en TuxEnc
        langs = [norm_lang(x) for x in hb.get("AudioLanguageList", []) if x != "any"]
        s.audio_langs = langs
        beh = str(hb.get("AudioTrackSelectionBehavior", "first"))
        if beh == "all":
            s.audio_mode = "lang_all" if langs else "all"
        else:
            s.audio_mode = {"first": "first", "language": "lang_all",
                            "none": "none"}.get(beh, "first")
        alist = hb.get("AudioList") or []
        if alist:
            a0 = alist[0]
            aenc = str(a0.get("AudioEncoder", "copy"))
            s.audio_codec = "copy" if aenc.startswith("copy") else _HB_AUDIO.get(aenc, "aac")
            try:
                s.audio_bitrate = int(a0.get("AudioBitrate") or 0)
            except (TypeError, ValueError):
                s.audio_bitrate = 0
            mix = str(a0.get("AudioMixdown", ""))
            s.audio_mixdown = {"stereo": "stereo", "dpl2": "stereo", "dpl1": "stereo",
                               "mono": "stereo", "5point1": "5.1",
                               "6point1": "5.1"}.get(mix, "keep")
        # subtítulos
        slangs = [norm_lang(x) for x in hb.get("SubtitleLanguageList", []) if x != "any"]
        s.sub_langs = slangs
        sbeh = str(hb.get("SubtitleTrackSelectionBehavior", "none"))
        if sbeh == "all":
            s.sub_mode = "lang_all" if slangs else "all"
        else:
            s.sub_mode = {"none": "none", "first": "first"}.get(sbeh, "none")
        burn = str(hb.get("SubtitleBurnBehavior", "none"))
        if burn in ("foreign", "foreign_first"):
            s.sub_burn = "forced"
        elif burn == "first":
            s.sub_burn = "first"
        s.keep_chapters = bool(hb.get("ChapterMarkers", True))
        s.validate()
        name = str(hb.get("PresetName", "HandBrake")).strip() or "HandBrake"
        result.append(Preset(f"user:{name}", name, s))
    return result


def known_encoder(enc_id: str) -> bool:
    return enc_id in ENCODERS_BY_ID
