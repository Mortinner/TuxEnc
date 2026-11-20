"""Capítulos numerados solo con un número: «Dinosaucers 01.mp4» (1.3.0)."""
from dataclasses import replace

import pytest

from retitler import pipeline
from retitler.parser import MediaKind, numbered_episode, trailing_number
from retitler.providers import EpisodeInfo, ResultKind, SearchResult


@pytest.mark.parametrize("name,expected", [
    ("Dinosaucers 01.mp4", ("Dinosaucers", "01")),
    ("Serie - 12.mkv", ("Serie", "12")),
    ("Serie_EP05.mkv", ("Serie", "05")),
    ("Serie Ep05 [1080p].mkv", ("Serie", "05")),
    ("La serie Cap 07.avi", ("La serie", "07")),
    ("Dinosaucers 01 720p WEB-DL.mkv", ("Dinosaucers", "01")),
    ("2012.mkv", None),                       # un año no es un capítulo
    ("Blade Runner 2049.mkv", None),
    ("Room101.mkv", None),                    # número pegado al título
    ("Cosmos 2014.mkv", None),
])
def test_trailing_number(name, expected):
    assert trailing_number(name) == expected


DINO = [f"Dinosaucers {i:02}.mp4" for i in range(1, 72)]


def test_series_folder_numbers_are_episodes():
    p = numbered_episode("/tv/Dinosaucers 37.mp4", DINO)
    assert (p.kind, p.title, p.season, p.episodes, p.absolute) == (MediaKind.EPISODE, "Dinosaucers", 1, (37,), True)


def test_folder_named_like_the_show_is_enough():
    p = numbered_episode("/tv/Dinosaucers/Dinosaucers 05.mp4", [])
    assert p is not None and p.episodes == (5,)


def test_unpadded_run_that_reaches_two_digits():
    p = numbered_episode("/x/Serie 3.mkv", [f"Serie {i}.mkv" for i in range(1, 13)])
    assert p is not None and p.episodes == (3,)


def test_three_digits_are_season_and_episode_when_the_group_fits():
    p = numbered_episode("/x/Serie 205.mkv", ["Serie 101.mkv", "Serie 102.mkv", "Serie 205.mkv"])
    assert (p.season, p.episodes, p.absolute) == (2, (5,), False)
    q = numbered_episode("/x/Anime 100.mkv", ["Anime 099.mkv", "Anime 100.mkv"])
    assert (q.season, q.episodes, q.absolute) == (1, (100,), True)


@pytest.mark.parametrize("path,siblings", [
    ("/pelis/Rocky 2.mkv", ["Rocky.mkv", "Rocky 2.mkv", "Rocky 3.mkv", "Rocky 4.mkv", "Rocky 5.mkv"]),
    ("/pelis/Rocky/Rocky 2.mkv", ["Rocky 2.mkv", "Rocky 3.mkv"]),
    ("/pelis/Ocean's 11.mkv", ["Ocean's 11.mkv", "Ocean's 12.mkv", "Ocean's 13.mkv"]),
    ("/pelis/Ocean's 11.mkv", ["Ocean's 11.mkv"]),
    ("/pelis/Serie 01.mkv", ["Serie 01.mkv"]),             # uno solo y la carpeta no dice nada
    ("/pelis/Serie 01.mkv", ["Serie 01.srt", "Serie 02.srt"]),   # solo cuentan los vídeos
])
def test_numbered_movies_stay_movies(path, siblings):
    assert numbered_episode(path, siblings) is None


def test_analyze_uses_the_folder_listing(tmp_path):
    for n in DINO[:5]:
        (tmp_path / n).write_bytes(b"x")
    (tmp_path / "Rocky 2.mkv").write_bytes(b"x")
    pipeline._NAMES_CACHE.clear()
    res = pipeline.analyze(tmp_path / "Dinosaucers 03.mp4")
    assert res.parsed.kind is MediaKind.EPISODE and res.parsed.episodes == (3,)
    assert pipeline.analyze(tmp_path / "Rocky 2.mkv").parsed.kind is not MediaKind.EPISODE


class Seasons:
    """Buscador de mentira: T1 con 65 capítulos y T2 con 6 (como una serie de dos temporadas)."""

    def __init__(self, counts=None):
        self.counts = counts or {1: 65, 2: 6}
        self.calls = 0

    def seasons(self, result):
        self.calls += 1
        return list(self.counts) + [0]

    def season_episodes(self, result, season):
        self.calls += 1
        return [EpisodeInfo(season, i, f"Capítulo {i}") for i in range(1, self.counts.get(season, 0) + 1)]


SHOW = SearchResult("tmdb", ResultKind.SERIES, 1, "Dinosaucers", 1987)


@pytest.mark.parametrize("n,expected", [(1, (1, 1)), (65, (1, 65)), (66, (2, 1)), (71, (2, 6)), (90, (1, 90))])
def test_absolute_number_becomes_season_and_episode(n, expected):
    res = pipeline.Resolution(pipeline.Path(f"Dinosaucers {n:02}.mp4"),
                              numbered_episode(f"/tv/Dinosaucers {n:02}.mp4", DINO + [f"Dinosaucers {n:02}.mp4"]))
    out = pipeline._absolute_to_season(replace(res, chosen=SHOW), Seasons(), {})
    assert (out.parsed.season, out.parsed.episodes[0]) == expected


def test_absolute_conversion_is_memoized_per_show():
    memo, fake = {}, Seasons()
    for n in (10, 20, 66, 70):
        res = pipeline.Resolution(pipeline.Path("x.mp4"), numbered_episode(f"/tv/Dinosaucers {n:02}.mp4", DINO))
        pipeline._absolute_to_season(replace(res, chosen=SHOW), fake, memo)
    assert fake.calls == 3            # temporadas + T1 + T2, una sola vez
