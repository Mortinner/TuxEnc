"""Renombrado integrado: identificar, nombre final con resolución, biblioteca, deshacer, post-conversión."""
import os
import shutil
from pathlib import Path

import pytest

from tests.media import FF, M, MEDIA  # noqa: E402,F401
SRC = MEDIA / "lib"
SERIES_T = "{series} ({year})/Season {season:02}/{series} ({year}) - S{season:02}E{episode:02} - {title} - [{resolution}]"
MOVIE_T = "{initial}/{title} ({year}) - [{resolution}]"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TUXENC_FFMPEG_DIR", FF)
    for var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(var, str(tmp_path / var))
    down = tmp_path / "Descargas"
    shutil.copytree(SRC, down)
    from tests.fake_search import FakeSearcher
    from tuxenc.library import Destination, Library
    lib = Library()
    lib.searcher = FakeSearcher()
    lib.settings.series_template, lib.settings.movie_template = SERIES_T, MOVIE_T
    dest = Destination("library", series_root=str(tmp_path / "Multimedia/Series"),
                       movie_root=str(tmp_path / "Multimedia/Peliculas"))
    return lib, dest, down, tmp_path


def test_identify_states_and_companions(env):
    lib, dest, down, _ = env
    st, res, subs = lib.identify(str(down / "Arrow.S01E02.1080p.WEB-DL.mkv"))
    assert st == "ok" and res.chosen.title == "Arrow" and res.titles == ("Honra a tu padre",)
    assert [s.name for s in subs] == ["Arrow.S01E02.1080p.WEB-DL.spa.srt"]
    st, res, _ = lib.identify(str(down / "The.Batman.2022.2160p.mkv"))
    assert st == "ambiguous" and len(res.candidates) == 2
    from tests.fake_search import BATMAN
    st, res = lib.choose(res, BATMAN)
    assert st == "ok" and res.manual


def test_rename_only_into_library_with_real_resolution_and_undo(env):
    lib, dest, down, tmp = env
    items = []
    for f in ("Arrow.S01E02.1080p.WEB-DL.mkv", "Arrow.S01E03.1080p.WEB-DL.mkv", "Babel.2006.BluRay.mkv"):
        st, res, subs = lib.identify(str(down / f))
        items.append((down / f, res, subs))
    plan, moves = lib.rename_batch(items, dest)
    got = sorted(str(d.relative_to(tmp)) for _, d in moves)
    assert got == sorted([
        # el nombre decía 1080p pero el vídeo real es 1280x720: manda el vídeo
        "Multimedia/Series/Arrow (2012)/Season 01/Arrow (2012) - S01E02 - Honra a tu padre - [720p].mkv",
        "Multimedia/Series/Arrow (2012)/Season 01/Arrow (2012) - S01E02 - Honra a tu padre - [720p].spa.srt",
        "Multimedia/Series/Arrow (2012)/Season 01/Arrow (2012) - S01E03 - Pistoleros solitarios - [1080p].mkv",
        "Multimedia/Peliculas/B/Babel (2006) - [1080p].mkv",
        "Multimedia/Peliculas/B/Babel (2006) - [1080p].spa.forced.srt",
    ])
    assert not (down / "Babel.2006.BluRay.mkv").exists()
    assert lib.can_undo()
    lib.undo_last()
    assert (down / "Babel.2006.BluRay.mkv").exists() and (down / "Arrow.S01E02.1080p.WEB-DL.spa.srt").exists()
    assert not (tmp / "Multimedia/Peliculas/B").exists()


def test_log_anota_origen_y_destino_de_cada_archivo(env, caplog):
    """1.3.6: renombrado.log dice de dónde viene y adónde va cada archivo (y al deshacer)."""
    import logging
    caplog.set_level(logging.INFO, logger="retitler")
    lib, dest, down, tmp = env
    f = down / "Babel.2006.BluRay.mkv"
    st, res, subs = lib.identify(str(f))
    _, moves = lib.rename_batch([(f, res, subs)], dest)
    final = tmp / "Multimedia/Peliculas/B/Babel (2006) - [1080p].mkv"
    assert f"Movido: {f} → {final}" in caplog.text
    lib.undo_last()
    assert f"Devuelto: {final} → {f}" in caplog.text


def test_rename_never_overwrites(env):
    lib, dest, down, tmp = env
    target = tmp / "Multimedia/Peliculas/B/Babel (2006) - [1080p].mkv"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"ya estaba")
    st, res, subs = lib.identify(str(down / "Babel.2006.BluRay.mkv"))
    _, moves = lib.rename_batch([(down / "Babel.2006.BluRay.mkv", res, [])], dest)
    assert moves[0][1].name == "Babel (2006) - [1080p] (2).mkv"
    assert target.read_bytes() == b"ya estaba"


def test_finalize_converted_uses_real_resolution(env):
    lib, dest, down, tmp = env
    from tuxenc.engine import Job
    from tuxenc.probe import probe
    src = down / "The.Batman.2022.2160p.mkv"
    st, res, subs = lib.identify(str(src))
    from tests.fake_search import BATMAN
    st, res = lib.choose(res, BATMAN)
    # simulamos que la conversión (máx. 1080p) dejó su resultado con el nombre previsto
    predicted, _ = lib.target(src, res, dest, "1080p", ".mkv")
    predicted.parent.mkdir(parents=True)
    shutil.copy(SRC / "Babel.2006.BluRay.mkv", predicted)   # 1920x804 -> 1080p
    job = Job(input=str(src), info=probe(str(src)), output=str(predicted))
    job.companions = [str(down / "Babel.2006.BluRay.spa.forced.srt")]
    warns = lib.finalize_converted(job, res, dest, "mkv", "keep")
    assert warns == []
    assert job.output.endswith("Multimedia/Peliculas/B/The Batman (2022) - [1080p].mkv")
    assert Path(job.output.replace(".mkv", ".spa.forced.srt")).exists()
    assert src.exists()                       # «dejar el original»
    # si el resultado real fuera 720p, se corrige el nombre
    shutil.copy(SRC / "Arrow.S01E02.1080p.WEB-DL.mkv", job.output)   # 1280x720
    lib.finalize_converted(job, res, dest, "mkv", "keep")
    assert job.output.endswith("The Batman (2022) - [720p].mkv")
    assert not os.path.exists(str(predicted))


def test_metadata_tags(env):
    lib, dest, down, _ = env
    _, res, _ = lib.identify(str(down / "Arrow.S01E02.1080p.WEB-DL.mkv"))
    m = lib.metadata(res)
    assert m["title"] == "Honra a tu padre" and m["show"] == "Arrow" and m["season_number"] == 1
    _, res, _ = lib.identify(str(down / "Babel.2006.BluRay.mkv"))
    assert lib.metadata(res) == {"title": "Babel", "date": 2006}


def test_network_failure_is_an_error_not_no_match(env):
    lib, dest, down, _ = env
    from retitler.search import SearchResponse

    class Down:
        def search_parsed(self, parsed):
            return SearchResponse([], ["TVmaze no respondió (sin conexión)."])
    lib.searcher = Down()
    st, res, _ = lib.identify(str(down / "Arrow.S01E02.1080p.WEB-DL.mkv"))
    assert st == "error"
    assert "no se pudo buscar" in res.new_name(lib.settings)[1]


def test_series_without_episode_needs_episode_then_manual_pick(env):
    lib, dest, down, tmp = env
    f = down / "Arrow EN DIRECTO.mkv"
    shutil.copy(down / "Arrow.S01E03.1080p.WEB-DL.mkv", f)
    st, res, _ = lib.identify(str(f))
    from tests.fake_search import ARROW
    st, res = lib.choose(res, ARROW)
    assert st == "episode"                                   # serie sí, capítulo no: se retiene
    st, res = lib.choose(res, ARROW, 1, (2,))
    assert st == "ok" and res.titles == ("Honra a tu padre",)
    target, _ = lib.target(f, res, dest, "1080p", ".mkv")
    assert target.name == "Arrow (2012) - S01E02 - Honra a tu padre - [1080p].mkv"
    st, res = lib.choose(res, ARROW, 1, (2, 3))               # capítulo doble
    assert res.parsed.episodes == (2, 3) and "S01E02-E03 - Honra a tu padre & Pistoleros solitarios" in lib.relative_name(res, "1080p", ".mkv")[0]


def test_seasons_and_episodes_merge_providers():
    """Una temporada recién estrenada que solo tiene IMDb aparece igualmente."""
    from retitler.providers import EpisodeInfo, ResultKind, SearchResult
    from retitler.search import Searcher

    class P:
        def __init__(self, seasons, eps):
            self.s, self.e = seasons, eps
        def list_seasons(self, ident):
            return self.s
        def get_season(self, ident, season):
            return [e for e in self.e if e.season == season]

    tmdb = P([1, 2, 0], [EpisodeInfo(2, 1, "Uno", source="tmdb"), EpisodeInfo(2, 2, "Episodio 2", source="tmdb", provisional=True)])
    omdb = P([1, 2, 3], [EpisodeInfo(2, 2, "Two", source="omdb"), EpisodeInfo(2, 3, "Three", source="omdb"),
                         EpisodeInfo(3, 1, "Nuevo", source="omdb")])
    s = Searcher.__new__(Searcher)
    s._clients = {"tmdb": tmdb, "omdb": omdb}
    s._linked = lambda r: [("omdb", "tt1")]
    show = SearchResult("tmdb", ResultKind.SERIES, 1, "Show", 2020)
    assert s.seasons(show) == [1, 2, 3, 0]
    eps = s.season_episodes(show, 2)
    assert [(e.number, e.title) for e in eps] == [(1, "Uno"), (2, "Two"), (3, "Three")]


@pytest.fixture
def fake_trash(tmp_path, monkeypatch):
    bin_ = tmp_path / "Papelera"
    bin_.mkdir()
    from tuxenc import library as L

    def to_bin(p):
        p = Path(p)
        if p.exists():
            shutil.move(str(p), bin_ / p.name)
        return True
    monkeypatch.setattr(L, "trash", to_bin)
    return bin_


def _converted_bigger(lib, dest, down, tmp, name="Babel.2006.BluRay.mkv"):
    """Simula una conversión cuyo resultado ocupa MÁS que el original."""
    from tuxenc.engine import Job
    from tuxenc.probe import probe
    src = down / name
    st, res, subs = lib.identify(str(src))
    target, _ = lib.target(src, res, dest, "1080p", ".mkv")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(src.read_bytes() * 3)           # 3 veces más grande
    job = Job(input=str(src), info=probe(str(src)), output=str(target))
    job.companions = [str(s) for s in subs]
    job.rt, job.rename, job.dest = res, True, dest
    return job


def test_bigger_result_never_trashes_original(env, fake_trash):
    lib, dest, down, tmp = env
    job = _converted_bigger(lib, dest, down, tmp)
    warns = lib.finalize_converted(job, job.rt, dest, "mkv", "trash")
    assert warns == [] and job.bigger
    assert Path(job.input).exists() and not any(fake_trash.iterdir())   # el original sigue ahí


def test_smaller_result_trashes_original_when_asked(env, fake_trash):
    lib, dest, down, tmp = env
    job = _converted_bigger(lib, dest, down, tmp)
    Path(job.output).write_bytes(b"pequeno")
    lib.finalize_converted(job, job.rt, dest, "mkv", "trash")
    assert not job.bigger and not Path(job.input).exists()
    assert (fake_trash / "Babel.2006.BluRay.mkv").exists()


def test_use_original_puts_original_in_library(env, fake_trash):
    lib, dest, down, tmp = env
    job = _converted_bigger(lib, dest, down, tmp)
    lib.finalize_converted(job, job.rt, dest, "mkv", "keep")
    converted = Path(job.output)
    assert lib.use_original(job, dest) == []
    assert not converted.exists() or converted == Path(job.output)
    assert Path(job.output) == tmp / "Multimedia/Peliculas/B/Babel (2006) - [1080p].mkv"
    assert Path(job.output).read_bytes() == (SRC / "Babel.2006.BluRay.mkv").read_bytes()   # es el original
    assert (Path(job.output).parent / "Babel (2006) - [1080p].spa.forced.srt").exists()
    assert not (down / "Babel.2006.BluRay.mkv").exists()
    assert (fake_trash / "Babel (2006) - [1080p].mkv").exists()                             # el convertido
    assert (tmp / "Multimedia/Peliculas").is_dir()                                          # raíz intacta


def test_use_original_never_removes_library_root(env, fake_trash):
    lib, dest, down, tmp = env
    job = _converted_bigger(lib, dest, down, tmp)
    job.rename = False                        # p. ej. sin renombrar: no se toca ninguna carpeta
    lib.use_original(job, dest)
    assert job.output == job.input and (tmp / "Multimedia/Peliculas").is_dir()


def test_use_converted_trashes_original_and_subs(env, fake_trash):
    lib, dest, down, tmp = env
    job = _converted_bigger(lib, dest, down, tmp)
    assert lib.use_converted(job) == []
    assert not (down / "Babel.2006.BluRay.mkv").exists()
    assert not (down / "Babel.2006.BluRay.spa.forced.srt").exists()
    assert Path(job.output).exists()


def test_manual_episode_pick_overrides_file_title(env):
    """Caso Foyle's War T9: el usuario elige a mano el capítulo con el título en inglés y debe quedarse."""
    lib, dest, down, tmp = env
    from retitler.providers import EpisodeInfo
    from tests.fake_search import ARROW
    f = down / "Arrow (2012) - S01E02 - Mi titulo.mkv"
    shutil.copy(down / "Arrow.S01E03.1080p.WEB-DL.mkv", f)
    lib.searcher.episode_titles_detailed = lambda r, s, eps: [EpisodeInfo(s, n, f"English {n}", source="tvmaze") for n in eps]
    st, res, _ = lib.identify(str(f))
    assert res.titles == ("Mi titulo",) and res.title_sources == ("archivo",)        # automático: el del archivo
    st, res2 = lib.choose(res, ARROW)                                                  # «misma serie»: sin elegir capítulo
    assert res2.titles == ("Mi titulo",)
    st, res3 = lib.choose(res, ARROW, 1, (2,))                                         # elegido a mano: lo que eligió
    assert res3.titles == ("English 2",) and res3.title_sources == ("tvmaze",)
