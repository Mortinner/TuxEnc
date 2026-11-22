"""1.3.4: análisis ligero, «no existe» recordado y títulos provisionales en otros idiomas."""
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.media import MEDIA  # noqa: E402
from tuxenc import probe as P  # noqa: E402
from retitler.providers import CachedFetch, JsonCache, NotFound, is_placeholder  # noqa: E402

VIDEOS = sorted(p for p in MEDIA.rglob("*") if p.suffix.lower() in (".mkv", ".mp4", ".avi")
                and not p.name.startswith("."))


@pytest.mark.parametrize("path", VIDEOS, ids=lambda p: p.name)
def test_light_probe_gives_the_same_information(path, monkeypatch):
    light = P.probe(str(path), measure_audio=False)
    monkeypatch.setattr(P, "LIGHT_PROBE_EXTS", set())
    full = P.probe(str(path), measure_audio=False)
    assert asdict(light) == asdict(full)


def test_incomplete_light_probe_falls_back_to_full(monkeypatch):
    calls = []
    real = P._ffprobe

    def spy(path, timeout, light):
        calls.append(light)
        data = real(path, timeout, light)
        if light:                                  # simula un análisis ligero a medias
            for s in data["streams"]:
                if s.get("codec_type") == "audio":
                    s.pop("channels", None)
        return data

    monkeypatch.setattr(P, "_ffprobe", spy)
    info = P.probe(str(MEDIA / "Película de prueba [2024].mkv"), measure_audio=False)
    assert calls == [True, False] and all(a.channels for a in info.audio)


def test_not_found_is_remembered_for_a_while():
    calls = []

    def fetch(url, headers):
        calls.append(url)
        raise NotFound("no")

    now = [0.0]
    cf = CachedFetch(fetch, JsonCache(None), clock=lambda: now[0])
    for _ in range(12):
        with pytest.raises(NotFound):
            cf("https://api.themoviedb.org/3/tv/1/season/9", {})
    assert len(calls) == 1
    now[0] += CachedFetch.NOT_FOUND_TTL + 1
    with pytest.raises(NotFound):
        cf("https://api.themoviedb.org/3/tv/1/season/9", {})
    assert len(calls) == 2


@pytest.mark.parametrize("title", ["1.Bölüm", "1. Bölüm", "Bölüm 3", "4. Folge", "第1話", "第12集", "1화",
                                   "Odcinek 2", "Серия 5", "Capitolo 7", "Tập 9"])
def test_placeholders_in_other_languages(title):
    assert is_placeholder(title)


@pytest.mark.parametrize("title", ["Chapitre 8", "Plan París", "1984", "Pilot", "Episode One", "Capítulo final"])
def test_real_titles_are_not_placeholders(title):
    assert not is_placeholder(title)
