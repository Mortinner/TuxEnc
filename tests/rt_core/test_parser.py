import pytest

from retitler.parser import MediaKind, is_media_file, parse_filename, parse_path, split_extension

E, M, U = MediaKind.EPISODE, MediaKind.MOVIE, MediaKind.UNKNOWN


@pytest.mark.parametrize(
    "name, title, season, episodes, year, ext",
    [
        ("Breaking.Bad.S01E02.720p.HDTV.x264-GRP.mkv", "Breaking Bad", 1, (2,), None, ".mkv"),
        ("The Office (US) - 2x05 - Halloween.avi", "The Office (US)", 2, (5,), None, ".avi"),
        ("Doctor.Who.2005.S01E01.1080p.mkv", "Doctor Who", 1, (1,), 2005, ".mkv"),
        ("Marvels.Agents.of.S.H.I.E.L.D.S05E03.mkv", "Marvels Agents of S.H.I.E.L.D.", 5, (3,), None, ".mkv"),
        ("Serie [HDTV][Cap.102].avi", "Serie", 1, (2,), None, ".avi"),
        ("Serie_Rara_Cap.1005.mp4", "Serie Rara", 10, (5,), None, ".mp4"),
        ("Show.S01E01E02.mkv", "Show", 1, (1, 2), None, ".mkv"),
        ("Show.S01E05-E07.mkv", "Show", 1, (5, 6, 7), None, ".mkv"),
        ("Show S02E03-04.mkv", "Show", 2, (3, 4), None, ".mkv"),
        ("Show.S01E01-720p.mkv", "Show", 1, (1,), None, ".mkv"),
        ("Show Season 3 Episode 7.mkv", "Show", 3, (7,), None, ".mkv"),
        ("Mi Serie Temporada 2 Capitulo 4.mkv", "Mi Serie", 2, (4,), None, ".mkv"),
        ("1883.S01E01.mkv", "1883", 1, (1,), None, ".mkv"),
        ("show.s01e02.mkv", "show", 1, (2,), None, ".mkv"),
        ("Show.1920x1080.S01E01.mkv", "Show 1920x1080", 1, (1,), None, ".mkv"),
    ],
)
def test_episodes(name, title, season, episodes, year, ext):
    p = parse_filename(name)
    assert p.kind is E
    assert (p.title, p.season, p.episodes, p.year, p.extension) == (title, season, episodes, year, ext)


@pytest.mark.parametrize(
    "name, kind, title, year, ext",
    [
        ("Inception (2010).mkv", M, "Inception", 2010, ".mkv"),
        ("Blade.Runner.2049.2017.1080p.BluRay.x264.mkv", M, "Blade Runner 2049", 2017, ".mkv"),
        ("1917.2019.1080p.mkv", M, "1917", 2019, ".mkv"),
        ("1917.1080p.WEB-DL.mkv", M, "1917", None, ".mkv"),
        ("Movie.Name.1080p.BluRay.mkv", M, "Movie Name", None, ".mkv"),
        ("Mi.Pelicula.2020.es.srt", M, "Mi Pelicula", 2020, ".es.srt"),
        ("Spider-Man.No.Way.Home.2021.2160p.UHD.mkv", M, "Spider-Man No Way Home", 2021, ".mkv"),
        ("The.Spanish.Prisoner.1997.mkv", M, "The Spanish Prisoner", 1997, ".mkv"),
        ("Casablanca.mkv", U, "Casablanca", None, ".mkv"),
    ],
)
def test_movies(name, kind, title, year, ext):
    p = parse_filename(name)
    assert (p.kind, p.title, p.year, p.extension) == (kind, title, year, ext)
    assert p.season is None and p.episodes == ()


def test_split_extension():
    assert split_extension("a.b.mkv") == ("a.b", ".mkv")
    assert split_extension("Serie.S01E02") == ("Serie.S01E02", "")  # no es una extensión
    assert split_extension("x.en-US.srt") == ("x", ".en-US.srt")
    assert split_extension("x.forced.srt") == ("x", ".forced.srt")
    assert split_extension(".mkv") == (".mkv", "")


def test_path_season_folder():
    p = parse_path("/series/Breaking Bad (2008)/Season 01/02 - Gray Matter.mkv")
    assert (p.kind, p.title, p.year, p.season, p.episodes) == (E, "Breaking Bad", 2008, 1, (2,))


def test_path_spanish_folder_and_e_prefix():
    p = parse_path("/s/Show/Temporada 2/E05.mkv")
    assert (p.kind, p.title, p.season, p.episodes) == (E, "Show", 2, (5,))


def test_path_title_from_folder():
    p = parse_path("/s/Mi.Serie.S01.1080p.WEB-DL/S01E03.mkv")
    assert (p.title, p.season, p.episodes) == ("Mi Serie", 1, (3,))


def test_path_keeps_filename_title():
    p = parse_path("/s/Otra Carpeta/Show.S01E03.mkv")
    assert p.title == "Show"


def test_windows_separators():
    assert parse_path("C:\\x\\Show\\Season 1\\01.mkv").title == "Show"


@pytest.mark.parametrize("name, expected", [
    ("a.mkv", True), ("A.MP4", True), ("x.es.srt", True), ("/dir/b.avi", True),
    ("notas.txt", False), ("Serie.S01E01", False), ("foto.jpg", False), (".mkv", False), ("a.nfo", False),
])
def test_is_media_file(name, expected):
    assert is_media_file(name) is expected


import pytest as _pytest  # noqa: E402

from retitler.parser import parse_filename as _pf  # noqa: E402


@_pytest.mark.parametrize("name, ext", [
    ("Wednesday S01E01.spa.forced.srt", ".spa.forced.srt"),     # dos etiquetas: idioma + forzado
    ("Wednesday S01E01.en.sdh.srt", ".en.sdh.srt"),
    ("Wednesday S01E01.mkv.srt", ".srt"),                       # el .mkv sobrante no es un idioma
    ("Wednesday S01E01.es.srt", ".es.srt"),
])
def test_subtitle_tags_are_kept(name, ext):
    assert _pf(name).extension == ext and _pf(name).title == "Wednesday"


@_pytest.mark.parametrize("name, title, season, episode", [
    ("La Casa de Papel - Temporada 3 [HDTV][Cap.301][AC3 5.1 Castellano].avi", "La Casa de Papel", 3, 1),
    ("Serie S01 [Cap.105].avi", "Serie", 1, 5),
    ("Mad Men T2 2x03.mkv", "Mad Men", 2, 3),
    ("Seasons S01E01.mkv", "Seasons", 1, 1),
    ("The 100 S01E01.mkv", "The 100", 1, 1),
])
def test_repeated_season_is_not_part_of_the_title(name, title, season, episode):
    r = _pf(name)
    assert (r.title, r.season, r.episodes) == (title, season, (episode,))


import pytest as _pytest


@_pytest.mark.parametrize("name, title, season, ep", [
    ("The chosen EPISODIO 1 TEMPORADA 6 – EN DIR.mp4", "The chosen", 6, 1),
    ("The Chosen - Episodio 3 Temporada 6.mkv", "The Chosen", 6, 3),
    ("Arrow Episode 2 Season 1.mkv", "Arrow", 1, 2),
    ("Arrow Capitulo 5 de la temporada 2.mkv", "Arrow", 2, 5),
    ("The Chosen T6 E1.mp4", "The Chosen", 6, 1),
    ("The Chosen T06E01 HDTV.mkv", "The Chosen", 6, 1),
    ("The Chosen Temporada 6 Episodio 1.mp4", "The Chosen", 6, 1),
])
def test_spanish_and_reversed_episode_markers(name, title, season, ep):
    p = parse_filename(name)
    assert p.kind is MediaKind.EPISODE
    assert (p.title, p.season, p.episodes) == (title, season, (ep,))


def test_t_prefix_does_not_eat_words():
    # «Matrix» o «The Terminator 2» no deben confundirse con «T2 E…»
    assert parse_filename("The Terminator 1984.mkv").kind is MediaKind.MOVIE
    assert parse_filename("Tenet 2020 1080p.mkv").season is None
