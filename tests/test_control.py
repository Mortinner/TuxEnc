import os, sys, time, subprocess
sys.path.insert(0, "/home/claude/tuxenc")
os.environ["TUXENC_FFMPEG_DIR"] = "/home/claude/dl/rel-8.1/ffmpeg-n8.1-latest-linux64-gpl-shared-8.1/bin"
os.environ["XDG_CACHE_HOME"] = "/tmp/tuxenc-test-cache2"
from tuxenc.probe import probe
from tuxenc.catalog import EncodeSettings
from tuxenc.engine import QueueEngine, Job, default_output
M = "/home/claude/testmedia/"
eng = QueueEngine()
eng.set_parallel(2)
st = EncodeSettings(video_encoder="libx265", speed_preset="medium", audio_codec="aac"); st.validate()
eng.settings_provider = lambda: st
outdir = "/tmp/tuxenc-out2"; os.makedirs(outdir, exist_ok=True)
for f in os.listdir(outdir): os.remove(os.path.join(outdir, f))
eng.output_resolver = lambda j, s: default_output(j, s, outdir, eng.reserved_outputs(j.id))
for i in (1,2,3):
    eng.add(Job(input=M+f"clip{i}.mp4", info=probe(M+f"clip{i}.mp4")))
eng.start(); time.sleep(4)
def states(): return [(j.name, j.status, round(j.progress,2)) for j in eng.jobs]
print("running:", states())
ps = lambda: subprocess.run("ps -o stat=,comm= -C ffmpeg", shell=True, capture_output=True, text=True).stdout.split()
print("ffmpeg procs:", ps())
eng.pause(); time.sleep(1.5)
p1 = [j.progress for j in eng.jobs]; time.sleep(2); p2 = [j.progress for j in eng.jobs]
print("paused:", states(), "frozen:", p1 == p2, "ps:", ps())
eng.resume(); time.sleep(2)
print("resumed:", states())
eng.cancel_job(eng.jobs[0].id); time.sleep(1.5)
print("after cancel #1:", states())
while eng.active: time.sleep(0.5)
print("final:", states())
print("outputs:", sorted(os.listdir(outdir)))
# nombre: no pisar si ya existe
j = Job(input=M+"clip2.mp4", info=probe(M+"clip2.mp4")); print("next name:", os.path.basename(default_output(j, st, outdir)))
j = Job(input=M+"clip2.mp4", info=probe(M+"clip2.mp4")); s4 = EncodeSettings(container="mp4"); print("same-folder mp4 name:", os.path.basename(default_output(j, s4)))
