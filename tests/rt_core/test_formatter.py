import pytest

from retitler.formatter import (
    DEFAULT_MOVIE_TEMPLATE, DEFAULT_SERIES_TEMPLATE, NameContext, TemplateError,
    render, sanitize_component, validate_template,
)
from retitler.parser import parse_filename


def test_default_series():
    ctx = NameContext("Breaking Bad", 1, (1,), "Piloto")
    assert render(DEFAULT_SERIES_TEMPLATE, ctx, ".mkv") == "Breaking Bad - 1x01 - Piloto.mkv"


def test_year_in_series_template():
    tpl = "{series} ({year}) - {season}x{episode:02} - {title}"
    assert render(tpl, NameContext("Breaking Bad", 1, (1,), "Piloto", 2008), ".mkv") == "Breaking Bad (2008) - 1x01 - Piloto.mkv"
    # sin año no quedan paréntesis vacíos
    assert render(tpl, NameContext("Breaking Bad", 1, (1,), "Piloto"), ".mkv") == "Breaking Bad - 1x01 - Piloto.mkv"


def test_sanitization_windows_safe():
    ctx = NameContext("Star Trek: Voyager", 1, (1,), 'What If? "Yes" <3>')
    assert render(DEFAULT_SERIES_TEMPLATE, ctx, ".mkv") == "Star Trek - Voyager - 1x01 - What If 'Yes' 3.mkv"


def test_sanitization_linux_only():
    assert sanitize_component("A: B?", windows_safe=False) == "A: B?"
    assert sanitize_component("AC/DC", windows_safe=False) == "AC-DC"


def test_multi_episode_and_titles():
    ctx = NameContext("Show", 1, (1, 2), ["Uno", "Dos"])
    # Tras una «E» se repite la letra (S01E01-E02), que es lo que leen Jellyfin, Plex y Kodi (1.3.6)
    assert render("{series} S{season:02}E{episode:02} - {title}", ctx, ".mkv") == "Show S01E01-E02 - Uno & Dos.mkv"
    assert render("{series} s{season:02}e{episode:02}", ctx, ".mkv") == "Show s01e01-e02.mkv"
    assert render("{series} - {season}x{episode:02}", ctx, ".mkv") == "Show - 1x01-02.mkv"


def test_movie_and_missing_year():
    assert render(DEFAULT_MOVIE_TEMPLATE, NameContext(title="Inception", year=2010), ".mkv") == "Inception (2010).mkv"
    assert render(DEFAULT_MOVIE_TEMPLATE, NameContext(title="Inception"), ".mkv") == "Inception.mkv"


def test_missing_episode_title_leaves_no_dangling_separator():
    ctx = NameContext("Show", 1, (3,), "")
    assert render(DEFAULT_SERIES_TEMPLATE, ctx, ".mkv") == "Show - 1x03.mkv"


def test_empty_middle_field():
    ctx = NameContext("Show", 1, (3,), "", 2019)
    assert render("{series} - {title} - {year}", ctx) == "Show - 2019"


def test_folders_in_template():
    ctx = NameContext("Show", 1, (1,), "Pilot")
    out = render("{series}/Temporada {season:02}/{series} - {season}x{episode:02}", ctx, ".mkv")
    assert out == "Show/Temporada 01/Show - 1x01.mkv"


def test_value_slash_does_not_create_folder():
    ctx = NameContext("AC/DC", 1, (1,), "x")
    assert "/" not in render("{series} {episode:02}", ctx)


def test_case_insensitive_fields_and_escaped_braces():
    ctx = NameContext("Show", 2, (5,), "T", 2020)
    assert render("{Series} {season}x{episode:02} {{{year}}}", ctx) == "Show 2x05 {2020}"


def test_trailing_dots_removed():
    ctx = NameContext("Show", 1, (1,), "Wait...")
    assert render(DEFAULT_SERIES_TEMPLATE, ctx, ".mkv") == "Show - 1x01 - Wait.mkv"


def test_length_limit_keeps_extension():
    ctx = NameContext("Show", 1, (1,), "ñ" * 300)
    out = render(DEFAULT_SERIES_TEMPLATE, ctx, ".es.srt")
    assert len(out.encode()) <= 255 and out.endswith(".es.srt")


@pytest.mark.parametrize(
    "bad",
    ["{foo}", "{series", "series}", "{series!r}", "{season:abc}", "{}", "///", "{serie}", "{año}", "{titulo}"],
)
def test_invalid_templates(bad):
    assert validate_template(bad) is not None
    with pytest.raises(TemplateError):
        render(bad, NameContext("S", 1, (1,), "t"))


def test_valid_template():
    assert validate_template(DEFAULT_SERIES_TEMPLATE) is None
    assert validate_template("{series} S{season:02}E{episode:02}") is None


def test_from_parsed():
    p = parse_filename("Breaking.Bad.S01E02.720p.mkv")
    ctx = NameContext.from_parsed(p, title="Gray Matter")
    assert render(DEFAULT_SERIES_TEMPLATE, ctx, p.extension) == "Breaking Bad - 1x02 - Gray Matter.mkv"
    m = parse_filename("Inception.2010.1080p.mkv")
    assert render(DEFAULT_MOVIE_TEMPLATE, NameContext.from_parsed(m), m.extension) == "Inception (2010).mkv"
