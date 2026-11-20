"""Entorno de las pruebas: dónde están FFmpeg, el código y los vídeos de prueba.

Nada depende de rutas de un equipo concreto:

- ``TUXENC_FFMPEG_DIR``: carpeta con ``ffmpeg`` y ``ffprobe`` (si no, los del PATH).
- ``TUXENC_TESTMEDIA``: carpeta de los vídeos de prueba (si no, ``tests/.media``).

Los vídeos de prueba no van en el repositorio: se generan con FFmpeg la primera vez
(``python -m tests.media``, o al importar ``MEDIA`` desde una prueba) con la misma composición
que los originales: códecs, pistas, idiomas, subtítulos forzados, bandas negras, entrelazado…
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _ffmpeg_dir() -> str:
    env = os.environ.get("TUXENC_FFMPEG_DIR", "").strip()
    if env:
        return env
    found = shutil.which("ffprobe")
    if not found:
        raise RuntimeError("No encuentro FFmpeg: instala ffmpeg o define TUXENC_FFMPEG_DIR")
    return str(Path(found).resolve().parent)


FF = _ffmpeg_dir()
os.environ.setdefault("TUXENC_FFMPEG_DIR", FF)
MEDIA_DIR = Path(os.environ.get("TUXENC_TESTMEDIA", "") or REPO / "tests" / ".media")
M = str(MEDIA_DIR) + os.sep            # para las pruebas que construyen rutas como M + "archivo"

SRT = {
    "spa.srt": "1\n00:00:00,500 --> 00:00:05,000\nHola, esto es una prueba\n\n"
               "2\n00:00:06,000 --> 00:00:11,000\nSegundo subtítulo\n",
    "eng.srt": "1\n00:00:00,500 --> 00:00:05,000\nHello, this is a test\n\n"
               "2\n00:00:06,000 --> 00:00:11,000\nSecond subtitle\n",
    "forced.srt": "1\n00:00:02,000 --> 00:00:04,000\n[Cartel en ruso]\n",
    "lib/Arrow.S01E02.1080p.WEB-DL.spa.srt": "1\n00:00:00,500 --> 00:00:01,500\nHola\n",
    "lib/Babel.2006.BluRay.spa.forced.srt": "1\n00:00:00,500 --> 00:00:01,500\nHola\n",
    # Pistas escasas: una con un subtítulo al principio y otro casi al final, otra solo al principio
    "escaso.srt": "1\n00:00:01,000 --> 00:00:02,000\nHola\n\n2\n00:00:55,000 --> 00:00:56,000\nAdios\n",
    "temprano.srt": "1\n00:00:01,000 --> 00:00:02,000\nUno\n",
}


def _video(w: int, h: int, fps: str, secs: float, *, content_h: int | None = None,
           noise: bool = False) -> list[str]:
    """Imagen de prueba; con content_h, imagen más baja centrada con bandas negras (para el recorte)."""
    ch = content_h or h
    graph = [f"testsrc2=size={w}x{ch}:rate={fps}:duration={secs}"]
    if noise:
        graph.append("noise=alls=30:allf=t")
    if ch != h:
        graph.append(f"pad={w}:{h}:0:{(h - ch) // 2}:black")
    return ["-f", "lavfi", "-i", ",".join(graph)]


def _tone(secs: float, layout: str = "mono", freq: int = 440) -> list[str]:
    return ["-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=44100:duration={secs},"
                                 f"aformat=channel_layouts={layout}"]


def _x264(profile: str, extra: list[str] | None = None) -> list[str]:
    return ["-c:v", "libx264", "-profile:v", profile, "-pix_fmt", "yuv420p", "-preset", "veryfast",
            *(extra or [])]


def _specs() -> dict[str, list[str]]:
    """archivo → argumentos de ffmpeg (entradas, mapeo y códecs), sin el archivo de salida."""
    s = MEDIA_DIR
    return {
        # 3 audios (AAC eng, AC-3 spa, FLAC 5.1 jpn) y 3 subtítulos (uno forzado); bandas negras.
        "Película de prueba [2024].mkv": [
            *_video(1280, 720, "25", 12, content_h=544), *_tone(12), *_tone(12, freq=660),
            *_tone(12, "5.1", 330),
            "-i", str(s / "spa.srt"), "-i", str(s / "eng.srt"), "-i", str(s / "forced.srt"),
            "-map", "0:v", "-map", "1:a", "-map", "2:a", "-map", "3:a",
            "-map", "4:s", "-map", "5:s", "-map", "6:s",
            *_x264("baseline", ["-b:v", "5M"]),
            "-c:a:0", "aac", "-c:a:1", "ac3", "-b:a:1", "96k", "-c:a:2", "flac",
            "-c:s", "srt",
            "-metadata:s:a:0", "language=eng", "-metadata:s:a:1", "language=spa",
            "-metadata:s:a:2", "language=jpn",
            "-metadata:s:s:0", "language=spa", "-metadata:s:s:1", "language=eng",
            "-metadata:s:s:2", "language=spa", "-metadata:s:s:2", "title=Forzados",
            "-disposition:v:0", "0", "-disposition:a", "0", "-disposition:s:0", "0",
            "-disposition:s:1", "0", "-disposition:s:2", "forced"],
        # Caso real: ~1 Mbps (menos que el bitrate medio por defecto, 4000 kbps) + AAC estéreo 128k.
        "The chosen Episodio 1 Temporada 6.mp4": [
            *_video(1920, 1080, "24000/1001", 20), *_tone(20, "stereo"),
            *_x264("high", ["-b:v", "1000k", "-maxrate", "1200k", "-bufsize", "2000k"]),
            "-c:a", "aac", "-b:a", "128k"],
        "clip1.mp4": [*_video(1920, 1080, "30", 6, noise=True), *_tone(6),
                      *_x264("baseline", ["-b:v", "15M"]), "-c:a", "aac", "-b:a", "64k"],
        "clip2.mp4": [*_video(1920, 1080, "30", 6, noise=True), *_tone(6, freq=550),
                      *_x264("baseline", ["-b:v", "15M"]), "-c:a", "aac", "-b:a", "64k"],
        "clip3.mp4": [*_video(1920, 1080, "30", 6, noise=True), *_tone(6, freq=660),
                      *_x264("baseline", ["-b:v", "15M"]), "-c:a", "aac", "-b:a", "64k"],
        # PAL entrelazado (campo inferior primero) para el desentrelazado.
        "entrelazado.mkv": [
            *_video(720, 576, "25", 8), *_tone(8),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-flags", "+ildct+ilme", "-x264opts", "bff=1", "-field_order", "bt",
            "-c:a", "aac", "-metadata:s:a:0", "language=spa", "-disposition:0", "0",
            "-disposition:1", "0"],
        "hd720.mkv": [*_video(1280, 720, "24", 3), *_x264("baseline"), "-an"],
        "scope4k.mkv": [*_video(3840, 1608, "24", 3, content_h=1600), *_x264("baseline"), "-an"],
        "xvid.avi": [*_video(720, 400, "25", 5), "-c:v", "mpeg4", "-b:v", "850k", "-an"],
        # Avance con subtítulos escasos (caso «The Chosen», CC3): 1 min, 2 pistas SRT casi vacías.
        "subs-escasos.mkv": [
            *_video(640, 360, "25", 60, noise=True), *_tone(60),
            "-i", str(s / "escaso.srt"), "-i", str(s / "temprano.srt"),
            "-map", "0:v", "-map", "1:a", "-map", "2:s", "-map", "3:s",
            *_x264("baseline", ["-b:v", "1800k"]), "-c:a", "aac", "-c:s", "srt"],
        "lib/Arrow.S01E02.1080p.WEB-DL.mkv": [*_video(1280, 720, "24", 2), *_tone(2),
                                              *_x264("baseline"), "-c:a", "aac"],
        "lib/Arrow.S01E03.1080p.WEB-DL.mkv": [*_video(1920, 1080, "24", 2), *_x264("baseline"), "-an"],
        "lib/Babel.2006.BluRay.mkv": [*_video(1920, 804, "24", 2), *_x264("baseline"), "-an"],
        "lib/The.Batman.2022.2160p.mkv": [*_video(3840, 1608, "24", 2), *_x264("baseline"), "-an"],
    }


def ensure() -> Path:
    """Genera los vídeos de prueba que falten (la primera vez tarda unos segundos)."""
    (MEDIA_DIR / "lib").mkdir(parents=True, exist_ok=True)
    for name, text in SRT.items():
        p = MEDIA_DIR / name
        if not p.exists():
            p.write_text(text, encoding="utf-8")
    ffmpeg = str(Path(FF) / "ffmpeg")
    specs = _specs()
    for name, args in specs.items():
        out = MEDIA_DIR / name
        if out.exists():
            continue
        tmp = out.with_name(".tmp-" + out.name)
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args, str(tmp)]
        subprocess.run(cmd, check=True)
        tmp.replace(out)
    remux = MEDIA_DIR / "chosen-remux.mkv"            # el mismo vídeo en MKV, sin etiquetas BPS
    if not remux.exists():
        tmp = remux.with_name(".tmp-chosen-remux.mkv")
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(MEDIA_DIR / "The chosen Episodio 1 Temporada 6.mp4"),
                        "-map", "0", "-c", "copy", "-map_metadata", "-1", str(tmp)], check=True)
        tmp.replace(remux)
    return MEDIA_DIR


MEDIA = ensure()

if __name__ == "__main__":
    print(MEDIA)
