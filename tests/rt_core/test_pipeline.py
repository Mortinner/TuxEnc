from pathlib import Path

from retitler.config import Settings
from retitler.pipeline import analyze, choose, collect_media, search_for
from retitler.providers import ProviderError, ResultKind, SearchResult, TMDBClient
from retitler.search import Searcher
from tests.rt_core.fakes import FakeFetch

TV = {"results": [{"id": 1396, "name": "Breaking Bad", "first_air_date": "2008-01-20"},
                  {"id": 2, "name": "Breaking Bad: El Camino", "first_air_date": "2019-10-11"}]}
S1 = {"episodes": [{"episode_number": 1, "name": "Piloto"}, {"episode_number": 2, "name": ""}]}


def searcher(routes=None):
    base = {"/3/search/tv": TV, "/3/search/movie": {"results": []}, "/3/tv/1396/season/1": S1}
    return Searcher(TMDBClient("k" * 32, "es", fetch=FakeFetch({**base, **(routes or {})})))


def test_analyze_is_offline_and_pending(tmp_path):
    res = analyze(tmp_path / "Breaking.Bad.S01E01.mkv")
    assert not res.searched and res.parsed.title == "Breaking Bad" and res.chosen is None


def test_search_and_new_name(tmp_path):
    f = tmp_path / "Breaking.Bad.S01E01.720p.mkv"
    res = search_for(analyze(f), searcher())
    assert res.searched and res.chosen.id == 1396 and res.titles == ("Piloto",)
    name, note = res.new_name(Settings())
    assert name == "Breaking Bad - 1x01 - Piloto.mkv" and "Breaking Bad (2008)" in note


def test_templates_can_change_without_searching_again(tmp_path):
    res = search_for(analyze(tmp_path / "Breaking.Bad.S01E01.mkv"), searcher())
    assert res.new_name(Settings(series_template="{series} ({year}) S{season:02}E{episode:02}"))[0] == "Breaking Bad (2008) S01E01.mkv"
    assert res.new_name(Settings(series_template="{nope}"))[0] is None


def test_missing_episode_title_is_flagged(tmp_path):
    res = search_for(analyze(tmp_path / "Breaking.Bad.S01E02.mkv"), searcher())
    name, note = res.new_name(Settings())
    assert name == "Breaking Bad - 1x02.mkv" and "sin título de episodio" in note


def test_manual_choice_overrides_automatic_one(tmp_path):
    s = searcher({"/3/tv/2/season/1": {"episodes": [{"episode_number": 1, "name": "Otro"}]}})
    res = search_for(analyze(tmp_path / "Breaking.Bad.S01E01.mkv"), s)
    other = next(c for c in res.candidates if c.id == 2)
    assert choose(res, other, s).new_name(Settings())[0] == "Breaking Bad - El Camino - 1x01 - Otro.mkv"


def test_no_match_and_network_error(tmp_path):
    none = search_for(analyze(tmp_path / "Zzz.S01E01.mkv"), searcher({"/3/search/tv": {"results": []}}))
    assert none.chosen is None and none.new_name(Settings())[0] is None
    down = search_for(analyze(tmp_path / "Breaking.Bad.S01E01.mkv"), searcher({"/3/tv/1396/season/1": ProviderError("sin red")}))
    name, note = down.new_name(Settings())
    assert name is None and "error de red" in note


def test_non_media_and_folders(tmp_path):
    (tmp_path / "notas.txt").write_text("x")
    assert search_for(analyze(tmp_path / "notas.txt"), searcher()).new_name(Settings())[0] is None
    assert search_for(analyze(tmp_path), searcher()).error == "es una carpeta"


def test_unknown_kind_series_without_season(tmp_path):
    s = searcher({"/3/search/tv": {"results": [{"id": 5, "name": "Casablanca"}]}})
    res = search_for(analyze(tmp_path / "Casablanca.mkv"), s)
    assert res.chosen.kind is ResultKind.SERIES
    assert "no se detectó temporada" in res.new_name(Settings())[1]


def test_memo_avoids_repeated_searches(tmp_path):
    fake = FakeFetch({"/3/search/tv": TV, "/3/search/movie": {"results": []}, "/3/tv/1396/season/1": S1})
    s, memo = Searcher(TMDBClient("k" * 32, fetch=fake)), {}
    for n in (1, 2, 3):
        search_for(analyze(tmp_path / f"Breaking.Bad.S01E0{n}.mkv"), s, memo)
    assert sum("/search/tv" in url for url, _ in fake.calls) == 1


def test_collect_media(tmp_path):
    for name in ("b.mkv", "a.mkv", "x.es.srt", "notas.txt", "sub/c.mp4", "sub/.12345678.retitler-tmp"):
        p = tmp_path / name
        p.parent.mkdir(exist_ok=True)
        p.write_text("x")
    files, ignored = collect_media([tmp_path, tmp_path / "a.mkv", tmp_path / "no-existe.mkv"])
    assert [f.name for f in files] == ["a.mkv", "b.mkv", "c.mp4", "x.es.srt"] and ignored == 3


def test_network_failure_is_not_reported_as_no_match(tmp_path):
    s = searcher({"/3/search/tv": ProviderError("sin red")})
    name, note = search_for(analyze(tmp_path / "Breaking.Bad.S01E01.mkv"), s).new_name(Settings())
    assert name is None and "no se pudo buscar" in note and "TMDB no respondió" in note


def test_companion_subtitles_follow_their_video(tmp_path):
    from retitler.pipeline import companions
    names = ["Serie.S01E01.1080p.mkv", "Serie.S01E01.1080p.es.srt", "Serie S01E01 Spanish.srt",
             "Serie.S01E02.1080p.es.srt", "Otra.S01E01.srt", "notas.txt"]
    for n in names:
        (tmp_path / n).write_text("x")
    video = tmp_path / names[0]
    assert [p.name for p in companions(video)] == ["Serie S01E01 Spanish.srt", "Serie.S01E01.1080p.es.srt"]
    files, ignored = collect_media([video])
    assert [f.name for f in files] == [names[0], "Serie S01E01 Spanish.srt", "Serie.S01E01.1080p.es.srt"] and ignored == 0
    assert [f.name for f in collect_media([video], with_companions=False)[0]] == [names[0]]


def test_companion_gets_the_same_new_name_with_its_language(tmp_path):
    for n in ("Breaking.Bad.S01E01.720p.mkv", "Breaking.Bad.S01E01.720p.spa.forced.srt"):
        (tmp_path / n).write_text("x")
    s = searcher()
    files, _ = collect_media([tmp_path / "Breaking.Bad.S01E01.720p.mkv"])
    names = [search_for(analyze(f), s).new_name(Settings())[0] for f in files]
    assert names == ["Breaking Bad - 1x01 - Piloto.mkv", "Breaking Bad - 1x01 - Piloto.spa.forced.srt"]
