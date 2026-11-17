from tuxenc.catalog import resolution_label as R


def test_marcos_examples():
    assert R(1600, 800) == "1080p"       # 1600 a medio camino 1280/1920 -> sube; 800 -> 720
    assert R(1601, 800) == "1080p"
    assert R(1300, 1080) == "1080p"


def test_common_cases():
    cases = {
        (1920, 804): "1080p", (1920, 1080): "1080p", (1904, 1024): "1080p", (1440, 1080): "1080p",
        (3840, 1608): "2160p", (3840, 2160): "2160p", (4096, 1716): "2160p",
        (1280, 720): "720p", (1280, 536): "720p", (960, 720): "720p",
        (854, 480): "480p", (720, 576): "480p", (640, 480): "480p", (720, 480): "480p",
        (1080, 1920): "1080p",   # vertical de móvil
        (2560, 1440): "1080p",   # 1440p no es estándar en la regla: queda en 1080p
    }
    for (w, h), want in cases.items():
        assert R(w, h) == want, (w, h, R(w, h), want)


def test_anamorphic_uses_display_size():
    assert R(720, 480, 32 / 27) == "480p"     # DVD NTSC 16:9 -> 853x480
    assert R(1440, 1080, 4 / 3) == "1080p"    # HDV -> 1920x1080


def test_unknown():
    assert R(0, 0) == ""
