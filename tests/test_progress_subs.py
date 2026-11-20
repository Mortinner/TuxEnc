"""El avance no se queda clavado con pistas de subtítulos escasas (caso «The Chosen», CC3).

FFmpeg 8 informa out_time de la pista más atrasada; con un subtítulo solo al principio se queda
en 0:02 aunque el vídeo avance. TuxEnc usa también los fotogramas escritos."""
import os, sys, time, subprocess
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
import tempfile
from tests.media import FF, M, MEDIA  # noqa: E402,F401  (FFmpeg y vídeos de prueba)
os.environ["TUXENC_FFMPEG_DIR"] = FF
from tuxenc.probe import probe
from tuxenc.catalog import EncodeSettings
from tuxenc.engine import QueueEngine, Job, DONE

src = M + "subs-escasos.mkv"
out = os.path.join(tempfile.mkdtemp(prefix="tx-avance-"), "salida.mkv")
info = probe(src)
print("pistas de subtítulos:", len(info.subtitles), "| duración:", round(info.duration), "s | fps:", info.main_video.fps)
samples = []
eng = QueueEngine(on_update=lambda j: samples.append((round(time.monotonic() - t0, 2), round(j.progress * 100, 1))))
st = EncodeSettings(video_encoder="libx264", speed_preset="slow", quality=22)
st.sub_mode = "all"; st.languages = []
st.validate()
j = Job(input=src, info=info); j.settings = st; j.output = out
t0 = time.monotonic()
eng.output_resolver = lambda job, st: out
eng.set_parallel(1); eng.add(j); eng.start()
while j.status != DONE and time.monotonic() - t0 < 120:
    time.sleep(0.2)
eng.shutdown()
mid = [p for _, p in samples if 0 < p < 100]
print("estado:", j.status, "| muestras:", len(samples))
print("avance visto:", sorted(set(mid))[:3], "…", sorted(set(mid))[-3:])
print("distintos valores intermedios:", len(set(mid)), "| nunca retrocede:", all(b >= a for a, b in zip([p for _, p in samples], [p for _, p in samples][1:])))
assert len(set(mid)) >= 5 and max(mid) > 50, "el avance se quedó clavado"
print("OK")
