"""Catálogo de códecs, contenedores e idiomas que entiende TuxEnc."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VideoEncoder:
    id: str                 # nombre del encoder en ffmpeg
    label: str              # nombre visible
    codec: str              # h264 | hevc | av1 | vp9
    hw: str = ""            # "" (CPU) | nvenc | vaapi | qsv
    q_min: int = 0
    q_max: int = 51
    q_default: int = 22
    q_label: str = "RF"
    presets: tuple = ()
    preset_default: str = ""
    supports_10bit: bool = True
    supports_2pass: bool = True
    containers: tuple = ("mkv", "mp4", "webm")


_X26X_PRESETS = ("ultrafast", "superfast", "veryfast", "faster", "fast",
                 "medium", "slow", "slower", "veryslow")
_NV_PRESETS = ("p1", "p2", "p3", "p4", "p5", "p6", "p7")
_QSV_PRESETS = ("veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow")
_SVT_PRESETS = tuple(str(i) for i in range(13, -1, -1))   # 13 = más rápido
_VP9_PRESETS = ("5", "4", "3", "2", "1", "0")             # cpu-used, 5 = más rápido

VIDEO_ENCODERS: tuple[VideoEncoder, ...] = (
    VideoEncoder("libx264", "H.264 (x264)", "h264", q_default=21, presets=_X26X_PRESETS,
                 preset_default="medium", containers=("mkv", "mp4")),
    VideoEncoder("libx265", "H.265 / HEVC (x265)", "hevc", q_default=22, presets=_X26X_PRESETS,
                 preset_default="medium", containers=("mkv", "mp4")),
    VideoEncoder("libsvtav1", "AV1 (SVT-AV1)", "av1", q_max=63, q_default=30, q_label="CRF",
                 presets=_SVT_PRESETS, preset_default="6", supports_2pass=False),
    VideoEncoder("libvpx-vp9", "VP9 (libvpx)", "vp9", q_max=63, q_default=31, q_label="CRF",
                 presets=_VP9_PRESETS, preset_default="2", containers=("mkv", "mp4", "webm")),
    # NVIDIA
    VideoEncoder("h264_nvenc", "H.264 (NVIDIA NVENC)", "h264", "nvenc", q_default=23, q_label="CQ",
                 presets=_NV_PRESETS, preset_default="p5", supports_10bit=False,
                 containers=("mkv", "mp4")),
    VideoEncoder("hevc_nvenc", "H.265 / HEVC (NVIDIA NVENC)", "hevc", "nvenc", q_default=25,
                 q_label="CQ", presets=_NV_PRESETS, preset_default="p5", containers=("mkv", "mp4")),
    VideoEncoder("av1_nvenc", "AV1 (NVIDIA NVENC)", "av1", "nvenc", q_max=63, q_default=32,
                 q_label="CQ", presets=_NV_PRESETS, preset_default="p5"),
    # Intel Quick Sync
    VideoEncoder("h264_qsv", "H.264 (Intel QSV)", "h264", "qsv", q_min=1, q_default=23,
                 q_label="ICQ", presets=_QSV_PRESETS, preset_default="medium",
                 supports_10bit=False, supports_2pass=False, containers=("mkv", "mp4")),
    VideoEncoder("hevc_qsv", "H.265 / HEVC (Intel QSV)", "hevc", "qsv", q_min=1, q_default=25,
                 q_label="ICQ", presets=_QSV_PRESETS, preset_default="medium",
                 supports_2pass=False, containers=("mkv", "mp4")),
    VideoEncoder("av1_qsv", "AV1 (Intel QSV)", "av1", "qsv", q_min=1, q_max=51, q_default=28,
                 q_label="ICQ", presets=_QSV_PRESETS, preset_default="medium",
                 supports_2pass=False),
    # VAAPI (AMD / Intel)
    VideoEncoder("h264_vaapi", "H.264 (VAAPI · AMD/Intel)", "h264", "vaapi", q_min=1,
                 q_default=23, q_label="QP", supports_10bit=False, supports_2pass=False,
                 containers=("mkv", "mp4")),
    VideoEncoder("hevc_vaapi", "H.265 / HEVC (VAAPI · AMD/Intel)", "hevc", "vaapi", q_min=1,
                 q_default=25, q_label="QP", supports_2pass=False, containers=("mkv", "mp4")),
    VideoEncoder("av1_vaapi", "AV1 (VAAPI · AMD/Intel)", "av1", "vaapi", q_min=1, q_max=255,
                 q_default=120, q_label="QP", supports_2pass=False),
)

ENCODERS_BY_ID = {e.id: e for e in VIDEO_ENCODERS}


def encoder(enc_id: str) -> VideoEncoder:
    return ENCODERS_BY_ID.get(enc_id, ENCODERS_BY_ID["libx264"])


CONTAINERS = {
    "mkv": {"label": "MKV", "ext": ".mkv", "format": "matroska"},
    "mp4": {"label": "MP4", "ext": ".mp4", "format": "mp4"},
    "webm": {"label": "WebM", "ext": ".webm", "format": "webm"},
}

# Códecs de audio (id interno -> datos)
AUDIO_CODECS = {
    "copy": {"label": "audio_copy", "ffmpeg": "copy", "containers": ("mkv", "mp4", "webm")},
    "aac": {"label": "AAC", "ffmpeg": "aac", "containers": ("mkv", "mp4")},
    "opus": {"label": "Opus", "ffmpeg": "libopus", "containers": ("mkv", "mp4", "webm")},
    "ac3": {"label": "AC-3 (Dolby Digital)", "ffmpeg": "ac3", "containers": ("mkv", "mp4")},
    "eac3": {"label": "E-AC-3 (Dolby Digital Plus)", "ffmpeg": "eac3", "containers": ("mkv", "mp4")},
    "flac": {"label": "FLAC", "ffmpeg": "flac", "containers": ("mkv", "mp4")},
    "mp3": {"label": "MP3", "ffmpeg": "libmp3lame", "containers": ("mkv", "mp4")},
}

AUDIO_BITRATES = (64, 96, 128, 160, 192, 224, 256, 320, 384, 448, 512, 640)

# Qué códecs de origen se pueden copiar tal cual en cada contenedor
AUDIO_COPY_OK = {
    "mkv": None,  # todos
    "mp4": {"aac", "ac3", "eac3", "mp3", "opus", "flac", "alac"},
    "webm": {"opus", "vorbis"},
}
AUDIO_FALLBACK = {"mkv": "aac", "mp4": "aac", "webm": "opus"}

TEXT_SUB_CODECS = {"subrip", "srt", "ass", "ssa", "mov_text", "webvtt", "text", "tx3g"}
BITMAP_SUB_CODECS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"}

# Idiomas (ISO 639-2/B) con nombre en español e inglés
LANGUAGES = (
    ("spa", "Español", "Spanish"), ("eng", "Inglés", "English"),
    ("fre", "Francés", "French"), ("ger", "Alemán", "German"),
    ("ita", "Italiano", "Italian"), ("por", "Portugués", "Portuguese"),
    ("cat", "Catalán", "Catalan"), ("baq", "Euskera", "Basque"),
    ("glg", "Gallego", "Galician"), ("jpn", "Japonés", "Japanese"),
    ("kor", "Coreano", "Korean"), ("chi", "Chino", "Chinese"),
    ("rus", "Ruso", "Russian"), ("ara", "Árabe", "Arabic"),
    ("hin", "Hindi", "Hindi"), ("dut", "Neerlandés", "Dutch"),
    ("swe", "Sueco", "Swedish"), ("nor", "Noruego", "Norwegian"),
    ("dan", "Danés", "Danish"), ("fin", "Finés", "Finnish"),
    ("pol", "Polaco", "Polish"), ("tur", "Turco", "Turkish"),
    ("gre", "Griego", "Greek"), ("heb", "Hebreo", "Hebrew"),
    ("cze", "Checo", "Czech"), ("hun", "Húngaro", "Hungarian"),
    ("rum", "Rumano", "Romanian"), ("ukr", "Ucraniano", "Ukrainian"),
    ("tha", "Tailandés", "Thai"), ("vie", "Vietnamita", "Vietnamese"),
)

# Alias de códigos de idioma que aparecen en archivos reales -> código canónico
_LANG_ALIASES = {
    "es": "spa", "esp": "spa", "spa": "spa", "es-es": "spa", "es-419": "spa", "es-mx": "spa",
    "en": "eng", "eng": "eng", "en-us": "eng", "en-gb": "eng",
    "fr": "fre", "fra": "fre", "fre": "fre", "de": "ger", "deu": "ger", "ger": "ger",
    "it": "ita", "ita": "ita", "pt": "por", "por": "por", "pt-br": "por",
    "ca": "cat", "cat": "cat", "eu": "baq", "eus": "baq", "baq": "baq",
    "gl": "glg", "glg": "glg", "ja": "jpn", "jpn": "jpn", "ko": "kor", "kor": "kor",
    "zh": "chi", "zho": "chi", "chi": "chi", "ru": "rus", "rus": "rus",
    "ar": "ara", "ara": "ara", "hi": "hin", "hin": "hin", "nl": "dut", "nld": "dut",
    "dut": "dut", "sv": "swe", "swe": "swe", "no": "nor", "nor": "nor", "nob": "nor",
    "da": "dan", "dan": "dan", "fi": "fin", "fin": "fin", "pl": "pol", "pol": "pol",
    "tr": "tur", "tur": "tur", "el": "gre", "ell": "gre", "gre": "gre",
    "he": "heb", "heb": "heb", "cs": "cze", "ces": "cze", "cze": "cze",
    "hu": "hun", "hun": "hun", "ro": "rum", "ron": "rum", "rum": "rum",
    "uk": "ukr", "ukr": "ukr", "th": "tha", "tha": "tha", "vi": "vie", "vie": "vie",
}


def norm_lang(code: str | None) -> str:
    if not code:
        return "und"
    return _LANG_ALIASES.get(code.strip().lower(), code.strip().lower())


def lang_name(code: str, ui_lang: str = "es") -> str:
    code = norm_lang(code)
    for c, es, en in LANGUAGES:
        if c == code:
            return es if ui_lang == "es" else en
    return code


RESOLUTIONS = (0, 2160, 1440, 1080, 720, 576, 480)   # 0 = original
# Recuadro (ancho, alto) de cada resolución máxima, como en HandBrake
RES_BOX = {2160: (3840, 2160), 1440: (2560, 1440), 1080: (1920, 1080), 720: (1280, 720),
           576: (1024, 576), 480: (854, 480)}


def fit_size(w: int, h: int, max_height: int, upscale: bool = False) -> tuple[int, int] | None:
    """Tamaño de salida para que (w, h) quepa en el recuadro manteniendo la proporción.

    Devuelve None si no hay que escalar. Sin `upscale`, nunca se agranda.
    """
    if not max_height or not w or not h or max_height not in RES_BOX:
        return None
    bw, bh = RES_BOX[max_height]
    f = min(bw / w, bh / h)
    if not upscale:
        f = min(f, 1.0)
    if abs(f - 1.0) < 1e-6:
        return None
    nw = max(2, int(round(w * f / 2)) * 2)
    nh = max(2, int(round(h * f / 2)) * 2)
    if (nw, nh) == (w, h):
        return None
    return nw, nh


# --------------------------------------------------------------------------- resolución estándar
# Regla de Marcos: cada lado se compara con su escalera (lado largo con anchos, lado corto con
# altos); gana la clase MÁS ALTA de las dos y, a medio camino, se redondea hacia arriba.
# La tele escala hasta llenar un lado, así que basta con que uno esté cerca de un estándar alto.
STD_CLASSES = (  # (etiqueta, lado largo, lado corto)
    ("480p", 854, 480),
    ("720p", 1280, 720),
    ("1080p", 1920, 1080),
    ("2160p", 3840, 2160),
)


def _nearest_class(value: float, axis: int) -> int:
    best, best_d = 0, None
    for i, cls in enumerate(STD_CLASSES):
        d = abs(value - cls[axis])
        if best_d is None or d < best_d or d == best_d:   # empate -> la más alta (va después)
            best, best_d = i, d
    return best


def resolution_label(width: int, height: int, sar: float = 1.0) -> str:
    """Resolución estándar ("2160p", "1080p", "720p", "480p") según las dimensiones de visualización."""
    if not width or not height:
        return ""
    disp_w = width * (sar if sar and sar > 0 else 1.0)
    long_side, short_side = max(disp_w, height), min(disp_w, height)
    return STD_CLASSES[max(_nearest_class(long_side, 1), _nearest_class(short_side, 2))][0]


# Explicación de algunos valores de velocidad (clave de traducción)
SPEED_HINTS = {
    "x26x": {"ultrafast": "sp_fastest", "veryfast": "sp_fast", "medium": "sp_recommended",
             "slow": "sp_better", "veryslow": "sp_best"},
    "nvenc": {"p1": "sp_fastest", "p3": "sp_fast", "p4": "sp_balanced", "p5": "sp_recommended",
              "p6": "sp_better", "p7": "sp_best"},
    "qsv": {"veryfast": "sp_fastest", "fast": "sp_fast", "medium": "sp_recommended",
            "slow": "sp_better", "veryslow": "sp_best"},
    "svt": {"13": "sp_fastest", "10": "sp_fast", "8": "sp_balanced", "6": "sp_recommended",
            "4": "sp_better", "0": "sp_best"},
    "vp9": {"5": "sp_fastest", "4": "sp_fast", "2": "sp_recommended", "1": "sp_better",
            "0": "sp_best"},
}


def speed_family(enc_id: str) -> str:
    e = encoder(enc_id)
    if e.id in ("libx264", "libx265"):
        return "x26x"
    if e.id == "libsvtav1":
        return "svt"
    if e.id == "libvpx-vp9":
        return "vp9"
    return e.hw
FRAMERATES = ("source", "23.976", "24", "25", "29.97", "30", "50", "59.94", "60")


@dataclass
class EncodeSettings:
    """Todos los ajustes de una transcodificación. Se guarda como JSON en los presets."""

    container: str = "mkv"
    # Vídeo
    video_encoder: str = "libx265"
    rate_mode: str = "cq"           # cq | abr | cbr
    quality: int = 22
    bitrate: int = 4000             # kbps (abr / cbr)
    two_pass: bool = False
    copy_if_lower: bool = True      # bitrate medio/constante: si el original ya tiene menos, copiar el vídeo
    speed_preset: str = "medium"
    bit_depth: int = 8              # 8 | 10
    # Imagen y filtros
    max_height: int = 0             # 0 = original (recuadro ancho×alto, ver RES_BOX)
    allow_upscale: bool = False     # ampliar vídeos más pequeños que el recuadro
    framerate: str = "source"
    deinterlace: str = "off"        # off | yadif | bwdif
    denoise: str = "off"            # off | light | medium | strong
    autocrop: bool = False
    # Audio
    audio_mode: str = "lang_all"    # first | lang_all | all | none
    audio_langs: list = field(default_factory=lambda: ["spa", "eng"])
    audio_codec: str = "copy"
    audio_bitrate: int = 0          # 0 = automático
    audio_mixdown: str = "keep"     # keep | stereo | 5.1
    audio_copy_if_lower: bool = True  # pista ya en ese códec, mismos canales y ≤ bitrate: copiarla
    # Subtítulos
    sub_mode: str = "lang_all"      # none | forced | first | lang_all | all
    sub_langs: list = field(default_factory=lambda: ["spa", "eng"])
    sub_burn: str = "none"          # none | forced | first
    # Metadatos
    keep_chapters: bool = True

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data: dict) -> "EncodeSettings":
        s = cls()
        for k, v in (data or {}).items():
            if hasattr(s, k):
                setattr(s, k, v)
        s.validate()
        return s

    def copy(self) -> "EncodeSettings":
        return EncodeSettings.from_dict(self.to_dict())

    def validate(self) -> None:
        enc = encoder(self.video_encoder)
        self.video_encoder = enc.id
        if self.container not in CONTAINERS:
            self.container = "mkv"
        if self.container not in enc.containers:
            self.container = "mkv"
        if self.rate_mode not in ("cq", "abr", "cbr"):
            self.rate_mode = "cq"
        self.quality = max(enc.q_min, min(enc.q_max, int(self.quality)))
        self.bitrate = max(100, int(self.bitrate))
        if enc.presets and self.speed_preset not in enc.presets:
            self.speed_preset = enc.preset_default
        if not enc.supports_10bit:
            self.bit_depth = 8
        if self.bit_depth not in (8, 10):
            self.bit_depth = 8
        if not enc.supports_2pass or self.rate_mode == "cq":
            self.two_pass = False
        if self.audio_codec not in AUDIO_CODECS:
            self.audio_codec = "copy"
        if self.container not in AUDIO_CODECS[self.audio_codec]["containers"]:
            self.audio_codec = AUDIO_FALLBACK[self.container]
        self.audio_langs = [norm_lang(x) for x in (self.audio_langs or [])]
        self.sub_langs = [norm_lang(x) for x in (self.sub_langs or [])]
