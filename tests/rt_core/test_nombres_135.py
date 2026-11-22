"""1.3.5: capítulos con «S001E01» o «S01E01x02», y nada dentro de «Season NN» es una película.

En la prueba de Marcos con unos 13 000 vídeos, 124 capítulos de cuatro series acabaron en la
biblioteca de películas: TuxEnc no reconocía esas formas de escribir el capítulo y, como el
nombre traía un año, los tomaba por películas.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from retitler.parser import MediaKind, is_season_folder, parse_filename, parse_path  # noqa: E402
from retitler.pipeline import analyze  # noqa: E402

S = "/nas/Series"


@pytest.mark.parametrize("path, title, season, episodes, ep_title", [
    (f"{S}/SeaQuest DSV (1993)/Season 01/SeaQuest DSV (1993) - S001E01 - La ventana del diablo.mkv",
     "SeaQuest DSV", 1, (1,), "La ventana del diablo"),
    (f"{S}/SeaQuest DSV (1993)/Season 02/SeaQuest DSV (1993) - S002E13 - Algo.mkv",
     "SeaQuest DSV", 2, (13,), "Algo"),
    (f"{S}/Star Trek - Discovery (2017)/Season 01/Star Trek Discovery (2017) - S01E01x01 - El saludo vulcano.mkv",
     "Star Trek Discovery", 1, (1,), "El saludo vulcano"),
    (f"{S}/Star Trek - Discovery (2017)/Season 05/Star Trek Discovery (2017) - S05E10x10 - Como la vida misma.mkv",
     "Star Trek Discovery", 5, (10,), "Como la vida misma"),
    (f"{S}/Prison Break (2005)/Season 04/Prison Break (2005) - S04E01x02 - Scylla, el libro negro.mkv",
     "Prison Break", 4, (1, 2), "Scylla, el libro negro"),
    (f"{S}/Jack el Destripador (1988)/Season 01/Jack el Destripador (1988) - S01E01x02 - Capitulo 1 y 2.mkv",
     "Jack el Destripador", 1, (1, 2), "Capitulo 1 y 2"),
])
def test_series_de_la_prueba(path, title, season, episodes, ep_title):
    p = parse_path(path)
    assert (p.kind, p.title, p.season, p.episodes, p.episode_title) == \
        (MediaKind.EPISODE, title, season, episodes, ep_title)


def test_formas_de_siempre_sin_cambios():
    assert parse_filename("Arrow.S01E02.1080p.mkv").episodes == (2,)
    assert parse_filename("Arrow.S01E02E03.mkv").episodes == (2, 3)
    assert parse_filename("Arrow.S01E02-04.mkv").episodes == (2, 3, 4)
    assert parse_filename("Arrow - 1x02.mkv").episodes == (2,)
    # Una temporada de tres cifras sin cero delante no es una temporada
    assert parse_filename("Show - S100E01.mkv").kind is not MediaKind.EPISODE


@pytest.mark.parametrize("name", ["Season 01", "Temporada 2", "S03", "Season 001", "season.4", "Specials", "Especiales"])
def test_carpetas_de_temporada(name):
    assert is_season_folder(name)


@pytest.mark.parametrize("name", ["Peliculas", "Arrow (2012)", "Extras", "Season of the Witch (2011)"])
def test_no_son_carpetas_de_temporada(name):
    assert not is_season_folder(name)


def test_dentro_de_una_temporada_nunca_es_pelicula():
    p = parse_path(f"{S}/Foo (2001)/Season 02/Foo (2001) - nombre raro [1080p].mkv")
    assert p.kind is MediaKind.EPISODE
    assert (p.title, p.year, p.season, p.episodes) == ("Foo", 2001, 2, ())


def test_fuera_de_una_temporada_las_peliculas_siguen_siendo_peliculas():
    for path in ("/nas/Peliculas/O/Ocean's 11 (2001) - [1080p].mkv", "/nas/Peliculas/R/Rocky 2 (1979).mkv",
                 "/descargas/2012 (2009) 1080p.mkv"):
        assert parse_path(path).kind is MediaKind.MOVIE, path


def test_numerados_dentro_de_una_temporada(tmp_path):
    d = tmp_path / "Dinosaucers" / "Season 01"
    d.mkdir(parents=True)
    for n in (1, 2, 3):
        (d / f"Dinosaucers {n:02}.mp4").touch()
    res = analyze(d / "Dinosaucers 02.mp4")
    assert res.parsed.kind is MediaKind.EPISODE and res.parsed.episodes == (2,)


# ----------------------------------------------------------------------------- 1.3.6
def test_especiales_en_specials_son_temporada_0():
    p = parse_path(f"{S}/Dragon Ball Z (1989)/Specials/Dragon Ball Z (1989) - S00E05x06 - Dragon Ball Z Gaiden "
                   "El plan para destruir a los Superguerreros (Parte 1) (OVA).mkv")
    assert (p.kind, p.title, p.season, p.episodes) == (MediaKind.EPISODE, "Dragon Ball Z", 0, (5, 6))
    # Sin número reconocible, en «Specials» tampoco es una película: temporada 0 sin capítulo
    p = parse_path(f"{S}/Dragon Ball Z (1989)/Specials/Dragon Ball Z Especial 3 (1993).mkv")
    assert (p.kind, p.season, p.episodes) == (MediaKind.EPISODE, 0, ())
