"""Copiar el vídeo sin recomprimir cuando el original ya tiene menos bitrate que el pedido."""
import os
import shutil
import time

import pytest

FF = "/home/claude/dl/rel-8.1/ffmpeg-n8.1-latest-linux64-gpl-shared-8.1/bin"
M = "/home/claude/testmedia/"


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("TUXENC_FFMPEG_DIR", FF)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


def S(**kw):
    from tuxenc.catalog import EncodeSettings
    base = dict(video_encoder="libx265", rate_mode="abr", bitrate=2000, audio_codec="aac",
                audio_bitrate=160, audio_mixdown="stereo")
    s = EncodeSettings(**{**base, **kw})
    s.validate()
    return s


def test_bitrate_detection_mp4_and_mkv():
    from tuxenc.probe import probe
    mp4 = probe(M + "The chosen Episodio 1 Temporada 6.mp4")
    mkv = probe(M + "chosen-remux.mkv")
    assert 800 <= mp4.video_kbps <= 1200, mp4.video_kbps          # dato de la pista
    assert mkv.main_video.bitrate == 0                              # MKV no lo dice por pista
    assert 800 <= mkv.video_kbps <= 1300, mkv.video_kbps           # se deduce: total - audio


@pytest.mark.parametrize("src, kw, copies", [
    ("The chosen Episodio 1 Temporada 6.mp4", {}, True),                     # como el caso real
    ("chosen-remux.mkv", {}, True),
    ("The chosen Episodio 1 Temporada 6.mp4", {"bitrate": 800}, False),      # pide menos: recomprime
    ("The chosen Episodio 1 Temporada 6.mp4", {"rate_mode": "cq"}, False),   # calidad constante
    ("The chosen Episodio 1 Temporada 6.mp4", {"max_height": 720}, False),   # hay que escalar
    ("The chosen Episodio 1 Temporada 6.mp4", {"denoise": "light"}, False),  # filtro
    ("The chosen Episodio 1 Temporada 6.mp4", {"copy_if_lower": False}, False),
    ("The chosen Episodio 1 Temporada 6.mp4", {"container": "webm", "video_encoder": "libvpx-vp9",
                                               "audio_codec": "opus"}, False),  # H.264 no cabe en WebM
    ("xvid.avi", {}, False),                                                 # códec antiguo
])
def test_copy_decision(src, kw, copies):
    from tuxenc.command import build_plan
    from tuxenc.probe import probe
    plan = build_plan(probe(M + src), S(**kw), "/tmp/x.mkv")
    args = plan.passes[-1]
    assert plan.video_copied is copies
    assert (args[args.index("-c:v") + 1] == "copy") is copies
    if copies:
        assert "-vf" not in args and len(plan.passes) == 1


def test_real_run_copies_video_reencodes_audio_and_does_not_ask(tmp_path):
    from tuxenc.engine import Job, QueueEngine
    from tuxenc.probe import probe
    src = tmp_path / "The chosen Episodio 1 Temporada 6.mp4"
    shutil.copy(M + src.name, src)
    eng = QueueEngine()
    eng.output_resolver = lambda j, s: str(tmp_path / "out.mkv")
    job = Job(input=str(src), info=probe(str(src)))
    job.settings = S(two_pass=True)
    eng.add(job)
    t0 = time.time()
    eng.start()
    while eng.active:
        time.sleep(0.1)
    assert job.status == "done", job.error
    out = probe(job.output)
    assert out.main_video.codec == "h264" and (out.main_video.width, out.main_video.height) == (1920, 1080)
    assert out.audio[0].codec == "aac" and abs(out.duration - job.info.duration) < 0.5
    assert job.plan.video_copied and not job.bigger and time.time() - t0 < 15


# ---- Audio: copiar la pista si ya está en el códec pedido con menos bitrate (caso «The Chosen» al 103 %)

def _a(codec="aac", ch=2, kbps=128):
    from tuxenc.probe import Stream
    return Stream(index=1, kind="audio", codec=codec, channels=ch, bitrate=kbps)


@pytest.mark.parametrize("stream, kw, copies", [
    (_a(), {}, True),                                          # AAC 128 → pedido AAC 160: se copia
    (_a(kbps=160), {}, True),                                  # igual: se copia
    (_a(kbps=192), {}, False),                                 # tiene más: se recomprime
    (_a(kbps=0), {}, False),                                   # bitrate desconocido: no se arriesga
    (_a(ch=6, kbps=384), {}, False),                           # 5.1 → estéreo: hay que mezclar
    (_a(ch=6, kbps=384), {"audio_mixdown": "keep", "audio_bitrate": 0}, True),  # 5.1 384 ≤ auto 384
    (_a(codec="ac3", kbps=128), {}, False),                    # otro códec
    (_a(), {"audio_copy_if_lower": False}, False),             # opción desactivada
    (_a(codec="flac", kbps=900), {"audio_codec": "flac", "audio_mixdown": "keep"}, True),  # sin pérdida
    (_a(codec="opus", kbps=96), {"audio_codec": "opus", "container": "webm", "video_encoder": "libvpx-vp9",
                                 "audio_bitrate": 128}, True),
])
def test_audio_copy_rules(stream, kw, copies):
    from tuxenc.command import _audio_args
    args = _audio_args(0, stream, S(**kw))
    assert (args == ["-c:a:0", "copy"]) is copies, args


def test_audio_bitrate_measured_in_mkv_without_tags():
    from tuxenc.probe import probe
    mkv = probe(M + "chosen-remux.mkv")
    assert 115 <= mkv.audio[0].bitrate <= 140, mkv.audio[0].bitrate   # medido de los paquetes


def test_plan_copies_audio_for_chosen_mkv():
    from tuxenc.probe import probe
    from tuxenc.command import build_plan
    info = probe(M + "chosen-remux.mkv")
    plan = build_plan(info, S(bitrate=800), "/tmp/x.mkv")     # pide menos vídeo: recomprime el vídeo…
    args = plan.passes[-1]
    assert "-c:a:0" in args and args[args.index("-c:a:0") + 1] == "copy"   # …pero el audio se copia
    assert not plan.video_copied
