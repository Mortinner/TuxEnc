"""Detección de los codificadores disponibles (CPU y GPU) en este equipo."""

from __future__ import annotations

import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor

from .catalog import VIDEO_ENCODERS
from . import gpus as gpu_mod
from .command import qsv_device_args, render_node
from .paths import LOG_DIR, clean_env, ffmpeg_bin, run_quiet

# Motivo del último fallo de cada encoder de GPU (para mostrarlo en la interfaz)
REASONS: dict[str, str] = {}


def ffmpeg_encoders() -> set[str]:
    try:
        res = subprocess.run([ffmpeg_bin(), "-hide_banner", "-encoders"], env=clean_env(),
                             capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return set()
    names = set()
    for line in res.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "VAS":
            names.add(parts[1])
    return names


def _test_hw(enc_id: str, hw: str) -> tuple[bool, str]:
    """Codifica unos pocos fotogramas negros para comprobar que la GPU responde de verdad."""
    pre: list[str] = []
    vf = "format=nv12"
    if hw == "vaapi":
        node = render_node("vaapi")
        if not os.path.exists(node):
            return False, f"no existe {node}"
        pre = ["-vaapi_device", node]
        vf = "format=nv12,hwupload"
    elif hw == "qsv":
        if not os.path.exists("/dev/dri"):
            return False, "no existe /dev/dri"
        pre = qsv_device_args()
        vf = "format=nv12,hwupload=extra_hw_frames=64"
    # NVENC: no se comprueba /dev/nvidiactl antes; en algunos sistemas el nodo se crea al
    # primer uso de CUDA, así que se deja que FFmpeg lo intente directamente.
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-loglevel", "error"] + pre + [
        "-f", "lavfi", "-i", "color=c=black:s=640x360:r=25:d=0.4", "-vf", vf,
        "-c:v", enc_id, "-f", "null", "-"]
    try:
        res = subprocess.run(cmd, env=clean_env(), capture_output=True, text=True,
                             timeout=20, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    err = (res.stderr or "").strip()
    return res.returncode == 0, err[:1200] if err else f"ffmpeg rc={res.returncode}"


def _friendly(err: str, fallback: str) -> str:
    """Explica en lenguaje claro los fallos más habituales."""
    from .i18n import tr
    m = re.search(r"minimum required Nvidia driver for nvenc is ([\d.]+)", err)
    if m:
        return tr("nv_driver_old", need=m.group(1).split(".")[0])
    if "Cannot load libcuda" in err or "Cannot load libnvidia-encode" in err:
        return tr("nv_no_driver")
    return fallback


def _nvidia_info() -> list[str]:
    lines = []
    try:
        with open("/proc/driver/nvidia/version", encoding="utf-8") as fh:
            lines.append("driver: " + fh.readline().strip())
    except OSError:
        lines.append("driver: /proc/driver/nvidia/version no existe (¿módulo nvidia no cargado?)")
    devs = sorted(d for d in os.listdir("/dev") if d.startswith("nvidia")) if os.path.isdir("/dev") else []
    lines.append("dispositivos: " + (", ".join(devs) or "ninguno"))
    res = run_quiet(["ldconfig", "-p"])
    libs = res.stdout if res else ""
    for lib in ("libcuda.so.1", "libnvidia-encode.so.1"):
        lines.append(f"{lib}: {'sí' if lib in libs else 'NO encontrada'}")
    return lines


def detect_available(gpus: list | None | bool = False) -> list[str]:
    """IDs de encoders utilizables, en el orden del catálogo.

    Solo se prueban los codificadores de las gráficas que hay en el equipo: en un equipo
    solo NVIDIA no se intentan QSV ni VAAPI (darían errores que no son fallos reales).
    """
    from .i18n import tr
    if gpus is False:
        gpus = gpu_mod.cached()
    present = ffmpeg_encoders()
    soft = [e.id for e in VIDEO_ENCODERS if not e.hw and e.id in present]
    hw_all = [e for e in VIDEO_ENCODERS if e.hw and e.id in present]
    hw = [e for e in hw_all if gpu_mod.applicable(e.hw, gpus)]
    ok: dict[str, bool] = {}
    report = [f"ffmpeg: {ffmpeg_bin()}", f"encoders CPU: {', '.join(soft)}",
              f"gráficas: {gpu_mod.describe(gpus)}"]
    if gpu_mod.applicable("nvenc", gpus):
        report += _nvidia_info()
    report.append("")
    results = []
    if hw:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda e: _test_hw(e.id, e.hw), hw))
    tested = dict(zip((e.id for e in hw), results))
    for e in hw_all:
        if e.id not in tested:
            need = " / ".join(gpu_mod.NAMES[v] for v in gpu_mod.HW_VENDORS[e.hw])
            REASONS[e.id] = tr("gpu_not_present", vendor=need)
            report.append(f"{e.id:12s} —   no aplica (no hay gráfica {need})")
            continue
        res, err = tested[e.id]
        if not res and e.hw == "nvenc":
            # Segundo intento en solitario (la primera inicialización de CUDA puede fallar)
            res, err = _test_hw(e.id, e.hw)
        ok[e.id] = res
        first = err.splitlines()[0] if err else ""
        REASONS[e.id] = "" if res else _friendly(err, re.sub(r"^(\[[^\]]*\]\s*)+", "", first))
        report.append(f"{e.id:12s} {'OK' if res else 'NO'}")
        if not res:
            report += ["    " + ln for ln in err.splitlines()[:4]]
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        (LOG_DIR / "gpu-detect.log").write_text("\n".join(report) + "\n", encoding="utf-8")
    except OSError:
        pass
    return [e.id for e in VIDEO_ENCODERS if e.id in soft or ok.get(e.id)]
