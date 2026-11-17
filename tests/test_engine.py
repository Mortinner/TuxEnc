import os, sys, time, json, subprocess
sys.path.insert(0, "/home/claude/tuxenc")
os.environ["TUXENC_FFMPEG_DIR"] = "/home/claude/dl/rel-8.1/ffmpeg-n8.1-latest-linux64-gpl-shared-8.1/bin"
os.environ["XDG_CACHE_HOME"] = "/tmp/tuxenc-test-cache"
from tuxenc.probe import probe
from tuxenc.catalog import EncodeSettings
from tuxenc.command import select_audio, select_subtitles, detect_crop, build_plan
from tuxenc.engine import QueueEngine, Job, default_output
from tuxenc.hw import detect_available

M = "/home/claude/testmedia/"
info = probe(M + "Película de prueba [2024].mkv")
print("summary:", info.summary())
print("audio:", [(s.index, s.codec, s.lang, s.channels, s.layout) for s in info.audio])
print("subs:", [(s.index, s.codec, s.lang, s.forced) for s in info.subtitles])
st = EncodeSettings()
print("sel audio lang_all spa,eng:", [s.lang for s in select_audio(info, st)])
st.audio_mode = "first"; print("first:", [s.lang for s in select_audio(info, st)])
st.audio_langs = ["fre"]; print("fallback no match:", [s.lang for s in select_audio(info, st)])
st = EncodeSettings(); st.sub_mode = "forced"; print("forced subs:", [ (s.lang, s.forced) for s in select_subtitles(info, st)[0]])
st = EncodeSettings(); st.sub_burn = "forced"; c, b = select_subtitles(info, st); print("burn forced:", b and (b.index, b.forced), "rest:", [s.index for s in c])
print("crop:", detect_crop(info))
print("available encoders:", detect_available())

out_dir = "/tmp/tuxenc-out"; os.makedirs(out_dir, exist_ok=True)
for f in os.listdir(out_dir): os.remove(os.path.join(out_dir, f))

cases = [
 ("x265-cq-10bit-mkv", dict(video_encoder="libx265", quality=26, speed_preset="ultrafast", bit_depth=10, autocrop=True, audio_codec="copy")),
 ("x264-abr2pass-mp4", dict(video_encoder="libx264", container="mp4", rate_mode="abr", bitrate=1500, two_pass=True, speed_preset="veryfast", audio_codec="copy", sub_mode="lang_all")),
 ("x265-abr2pass", dict(video_encoder="libx265", rate_mode="abr", bitrate=1200, two_pass=True, speed_preset="ultrafast", audio_codec="opus", audio_mixdown="keep")),
 ("x264-cbr-stereo-aac", dict(video_encoder="libx264", rate_mode="cbr", bitrate=2000, speed_preset="ultrafast", audio_codec="aac", audio_mixdown="stereo", audio_mode="all", max_height=480)),
 ("svtav1-cq", dict(video_encoder="libsvtav1", quality=35, speed_preset="12", bit_depth=10, audio_codec="opus", sub_burn="forced")),
 ("svtav1-cbr", dict(video_encoder="libsvtav1", rate_mode="cbr", bitrate=1000, speed_preset="12", audio_codec="opus")),
 ("vp9-webm", dict(video_encoder="libvpx-vp9", container="webm", quality=40, speed_preset="5", audio_codec="copy", framerate="30")),
 ("vp9-abr2pass", dict(video_encoder="libvpx-vp9", container="mkv", rate_mode="abr", bitrate=800, two_pass=True, speed_preset="5", audio_codec="ac3", audio_mode="all")),
 ("x264-burn-text-denoise", dict(video_encoder="libx264", container="mp4", speed_preset="ultrafast", sub_burn="first", denoise="medium", audio_codec="eac3", audio_mode="all", audio_mixdown="5.1")),
 ("x264-mp3-flac", dict(video_encoder="libx264", speed_preset="ultrafast", audio_codec="mp3", audio_mode="all")),
]
results = {}
def on_update(job): pass
done_evt = []
eng = QueueEngine(on_update=on_update, on_queue_done=lambda jobs: done_evt.append(len(jobs)))
eng.set_parallel(3)
cur = {}
eng.settings_provider = lambda: cur["st"]
def resolver(job, st):
    return os.path.join(out_dir, job.tag + {"mkv":".mkv","mp4":".mp4","webm":".webm"}[st.container])
eng.output_resolver = resolver
for name, kw in cases:
    j = Job(input=info.path, info=info)
    j.tag = name
    s = EncodeSettings(); [setattr(s, k, v) for k, v in kw.items()]; s.validate()
    j.settings = s
    eng.add(j)
# entrelazado + yadif
inf2 = probe(M + "entrelazado.mkv")
j = Job(input=inf2.path, info=inf2); j.tag = "deint-bwdif"; s = EncodeSettings(video_encoder="libx264", deinterlace="bwdif", speed_preset="ultrafast"); s.validate(); j.settings = s; eng.add(j)
t0 = time.time(); eng.start()
while eng.active: time.sleep(0.5)
print(f"queue done in {time.time()-t0:.1f}s, cb:", done_evt)
for j in eng.jobs:
    line = f"{j.tag:28s} {j.status:9s} passes={j.pass_total} size={j.out_size}"
    if j.status != "done": line += " ERR: " + j.error
    else:
        o = probe(j.output)
        v = o.main_video
        line += f" -> {v.codec} {v.width}x{v.height} fps={v.fps:.2f} | a=" + ",".join(f"{s.codec}/{s.lang}/{s.channels}" for s in o.audio) + " | s=" + ",".join(f"{s.codec}/{s.lang}{'F' if s.forced else ''}" for s in o.subtitles)
        pf = subprocess.run([os.environ["TUXENC_FFMPEG_DIR"]+"/ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=pix_fmt,codec_tag_string","-of","csv=p=0",j.output],capture_output=True,text=True).stdout.strip()
        line += f" | {pf}"
    print(line)
