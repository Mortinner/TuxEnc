"""Variables añadidas al integrar Retitler en TuxEnc: {resolution} e {initial}."""
from pathlib import Path

from retitler.config import Settings
from retitler.formatter import NameContext, initial_of, render, validate_template
from retitler.parser import parse_path
from retitler.pipeline import Resolution
from retitler.providers import ResultKind, SearchResult

SERIES = ("{series} ({year})/Season {season:02}/{series} ({year}) - S{season:02}E{episode:02} - {title} - [{resolution}]")
MOVIE = "{initial}/{title} ({year}) - [{resolution}]"


def test_initial_rules():
    assert initial_of("Babel") == "B"
    assert initial_of("The Batman") == "B"
    assert initial_of("The Batman", skip_articles=False) == "T"
    assert initial_of("El Padrino") == "P"
    assert initial_of("Ágora") == "A"
    assert initial_of("Ñu") == "N"
    assert initial_of("300") == "0-9"
    assert initial_of("L'Odyssée") == "O"
    assert initial_of("The") == "T"          # un artículo solo no se salta
    assert initial_of("") == "#"


def test_templates_with_new_fields_validate():
    assert validate_template(SERIES) is None
    assert validate_template(MOVIE) is None


def test_render_marcos_formats():
    ep = NameContext("Arrow", 1, (2,), "Honra a tu padre", 2012, "1080p", "A")
    assert render(SERIES, ep, ".mkv") == "Arrow (2012)/Season 01/Arrow (2012) - S01E02 - Honra a tu padre - [1080p].mkv"
    mv = NameContext(title="Babel", year=2006, resolution="1080p", initial="B")
    assert render(MOVIE, mv, ".mkv") == "B/Babel (2006) - [1080p].mkv"


def test_unknown_resolution_disappears_cleanly():
    mv = NameContext(title="Babel", year=2006, initial="B")
    assert render(MOVIE, mv, ".mkv") == "B/Babel (2006).mkv"


def test_resolution_new_name_extension_and_initial():
    s = Settings(series_template=SERIES, movie_template=MOVIE)
    movie = SearchResult("tmdb", ResultKind.MOVIE, 1, "The Batman", 2022)
    res = Resolution(Path("/x/the.batman.2022.mkv"), parse_path("/x/the.batman.2022.mkv"), True, (movie,), movie)
    name, _ = res.new_name(s, resolution="2160p", extension=".mp4")
    assert name == "B/The Batman (2022) - [2160p].mp4"
    s.skip_articles = False
    assert res.new_name(s, resolution="2160p")[0] == "T/The Batman (2022) - [2160p].mkv"


def test_settings_roundtrip_skip_articles(tmp_path):
    p = tmp_path / "c.json"
    Settings(skip_articles=False).save(p)
    assert Settings.load(p).skip_articles is False
