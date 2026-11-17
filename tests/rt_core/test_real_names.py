"""Nombres con el estilo real de los archivos del usuario:
   «Serie SxxEyy[ - Título] 1080p by.grupo, idiomas, códec.ext»"""
import itertools

import pytest

from retitler.parser import MediaKind, parse_filename

SHOWS = ["Better Call Saul", "Breaking Bad", "Chernobyl", "Dark", "Dexter", "Fargo", "Fringe",
         "Game of Thrones", "Lost", "Peaky Blinders", "Prison Break", "Stranger Things",
         "Succession", "The Office", "The Sopranos", "The Wire", "True Detective", "Vikings"]
LANGS = ["spanish AC3 5.1 english", "spanish english+subs", "esp-eng AC3 5.1",
         "español latino + ingles subs", "dual span-eng + subtitulos"]
CODECS = ["H.264", "H.265 x265", "AAC2.0", "AAC5.1", "AC3 5.1", "DTS", "E-AC3 Atmos"]
GROUPS = ["hd_team", "Releaser99", "dj_pepe", "torrentMaster", "el_pirata", "zxmini", "fulanito"]
TITLES = ["", "", "El principio del fin", "Renacer", "Efecto mariposa", "Punto de quiebre", "Piloto"]
EXTS = ["avi", "mp4", "mkv"]


def generated():
    """Combina todas las variantes del formato (unos cientos de nombres)."""
    cyc = itertools.cycle
    langs, codecs, groups, titles, exts = cyc(LANGS), cyc(CODECS), cyc(GROUPS), cyc(TITLES), cyc(EXTS)
    n = 0
    for show in SHOWS:
        for season in range(1, 6):
            for episode in (1, 5, 12):
                n += 1
                title = next(titles)
                name = (f"{show} S{season:02}E{episode:02}{' - ' + title if title else ''} 1080p "
                        f"by.{next(groups)}, {next(langs)}, {next(codecs)}.{next(exts)}")
                yield pytest.param(name, show, season, episode, id=f"{n}")


@pytest.mark.parametrize("name, show, season, episode", list(generated()))
def test_generated_names(name, show, season, episode):
    p = parse_filename(name)
    assert p.kind is MediaKind.EPISODE
    assert (p.title, p.season, p.episodes, p.year) == (show, season, (episode,), None)
    assert p.extension == "." + name.rsplit(".", 1)[1]


LITERAL = [
    ("Better Call Saul S01E04 - El principio del fin 1080p by.hd_team, spanish AC3 5.1 english, H.264.avi", "Better Call Saul", 1, 4, ".avi"),
    ("Better Call Saul S01E06 1080p by.dj_pepe, spanish AC3 5.1 english, AAC2.0.avi", "Better Call Saul", 1, 6, ".avi"),
    ("Better Call Saul S04E01 - El principio del fin 1080p by.el_pirata, dual span-eng + subtitulos, E-AC3 Atmos.mp4", "Better Call Saul", 4, 1, ".mp4"),
    ("Chernobyl S02E06 1080p by.el_pirata, español latino + ingles subs, AAC2.0.mkv", "Chernobyl", 2, 6, ".mkv"),
    ("Game of Thrones S04E07 - La verdad oculta 1080p by.zxmini, spanish english+subs, AAC2.0.mkv", "Game of Thrones", 4, 7, ".mkv"),
    ("Peaky Blinders S05E04 - Punto de quiebre 1080p by.torrentMaster, español latino + ingles subs, H.264.mkv", "Peaky Blinders", 5, 4, ".mkv"),
    ("The Office S05E05 1080p by.torrentMaster, esp-eng AC3 5.1, DTS.mp4", "The Office", 5, 5, ".mp4"),
    ("The Sopranos S01E09 - Colapso 1080p by.el_pirata, spanish english+subs, DTS.avi", "The Sopranos", 1, 9, ".avi"),
    ("True Detective S03E05 1080p by.fulanito, dual span-eng + subtitulos, E-AC3 Atmos.avi", "True Detective", 3, 5, ".avi"),
    ("Vikings S05E05 - Colapso 1080p by.el_pirata, español latino + ingles subs, H.265 x265.mkv", "Vikings", 5, 5, ".mkv"),
]


@pytest.mark.parametrize("name, show, season, episode, ext", LITERAL)
def test_literal_names(name, show, season, episode, ext):
    p = parse_filename(name)
    assert (p.kind, p.title, p.season, p.episodes, p.extension) == (MediaKind.EPISODE, show, season, (episode,), ext)
