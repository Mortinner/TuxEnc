"""Detección de gráficas: solo se prueban los codificadores que aplican y se elige el nodo correcto."""
import os

from tuxenc import gpus as G
from tuxenc import hw


def fake_sys(tmp_path, cards):
    """cards: [(vendor_id, n)] -> /sys/class/drm con cardN y renderD(128+N) apuntando al mismo PCI."""
    sysd, dev = tmp_path / "drm", tmp_path / "dri"
    sysd.mkdir()
    dev.mkdir()
    for vendor, n in cards:
        pci = tmp_path / f"pci{n}"
        pci.mkdir()
        (pci / "vendor").write_text(vendor + "\n")
        for name in (f"card{n}", f"renderD{128 + n}", f"card{n}-HDMI-A-1"):
            (sysd / name).mkdir()
            os.symlink(pci, sysd / name / "device")
        (dev / f"renderD{128 + n}").write_text("")
    return str(sysd), str(dev)


def test_nvidia_only_like_marcos(tmp_path):
    g = G.detect(*fake_sys(tmp_path, [("0x10de", 0)]))
    assert [x.vendor for x in g] == ["nvidia"]
    assert G.applicable("nvenc", g) and not G.applicable("qsv", g) and not G.applicable("vaapi", g)


def test_hybrid_laptop_picks_intel_node_not_nvidia(tmp_path):
    sysd, dev = fake_sys(tmp_path, [("0x10de", 0), ("0x8086", 1)])   # NVIDIA va primero
    g = G.detect(sysd, dev)
    assert sorted(x.vendor for x in g) == ["intel", "nvidia"]
    assert G.render_node("vaapi", g).endswith("renderD129")
    assert G.render_node("qsv", g).endswith("renderD129")
    assert all(G.applicable(h, g) for h in ("nvenc", "qsv", "vaapi"))


def test_amd_only(tmp_path):
    g = G.detect(*fake_sys(tmp_path, [("0x1002", 0)]))
    assert G.applicable("vaapi", g) and not G.applicable("qsv", g) and not G.applicable("nvenc", g)


def test_unknown_system_tests_everything(tmp_path):
    assert G.detect(str(tmp_path / "no-existe")) is None
    assert all(G.applicable(h, None) for h in ("nvenc", "qsv", "vaapi"))


def test_detect_available_skips_and_explains(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(hw, "LOG_DIR", tmp_path / "logs")
    tested = []
    monkeypatch.setattr(hw, "_test_hw", lambda enc, kind: (tested.append(enc) or (True, "")))
    monkeypatch.setattr(hw, "_nvidia_info", lambda: ["driver: prueba"])
    monkeypatch.setattr(hw, "ffmpeg_encoders", lambda: {e.id for e in hw.VIDEO_ENCODERS})
    from tuxenc import i18n
    i18n.set_language("es")
    avail = hw.detect_available([G.Gpu("nvidia", "/dev/dri/renderD128")])
    assert sorted(tested) == ["av1_nvenc", "h264_nvenc", "hevc_nvenc"]
    assert "hevc_nvenc" in avail and "hevc_qsv" not in avail and "hevc_vaapi" not in avail
    log = (tmp_path / "logs" / "gpu-detect.log").read_text()
    assert "hevc_qsv     —   no aplica (no hay gráfica Intel)" in log
    assert "hevc_vaapi   —   no aplica (no hay gráfica AMD / Intel)" in log
    assert "Device creation failed" not in log
    assert hw.REASONS["hevc_qsv"] == "este equipo no tiene gráfica Intel"
