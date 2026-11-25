"""1.3.6: el nombre de una carpeta de descargas no se usa como nombre de serie.

Caso de Marcos: «Telegram/8x03 - El detective Endeavour.mkv» (sin la serie en el nombre) se buscó
como «Telegram» y se dio por buena, sin preguntar, la serie «Techegram» (parecido 0,82).
"""
from retitler.parser import is_generic_folder, parse_path
from retitler.pipeline import analyze, search_for
from retitler.providers import TMDBClient
from retitler.search import Searcher
from tests.rt_core.fakes import FakeFetch


def test_carpetas_genericas():
    for name in ("Telegram", "Telegram Desktop", "Downloads", "Descargas", "Vídeos", "videos", "Nueva carpeta"):
        assert is_generic_folder(name), name
    for name in ("Endeavour (2013)", "Telegram Stories (2020)", "Series de culto", "Colegio Abbott (2021)"):
        assert not is_generic_folder(name), name


def test_telegram_no_es_el_titulo():
    p = parse_path("/home/morti/Downloads/Telegram/8x03 - El detective Endeavour.mkv")
    assert p.title == "" and p.season == 8 and p.episodes == (3,) and not p.title_from_folder
    p = parse_path("/home/morti/Descargas/Season 01/E05.mkv")
    assert p.title == "" and p.season == 1


def test_la_carpeta_de_la_serie_sigue_valiendo():
    p = parse_path("/nas/Series/Endeavour (2013)/Season 08/8x03 - Exeunt.mkv")
    assert p.title == "Endeavour" and p.year == 2013 and p.title_from_folder
    p = parse_path("/nas/Series/Endeavour (2013)/Season 08/Endeavour - 8x03 - Exeunt.mkv")
    assert p.title == "Endeavour" and not p.title_from_folder


def _searcher(results):
    return Searcher(TMDBClient("k" * 32, "es", fetch=FakeFetch({
        "/3/search/tv": {"results": results}, "/3/search/movie": {"results": []},
        "/3/tv/1/season/1": {"episodes": [{"episode_number": 3, "name": "Tres"}]},
    })))


def test_parecido_aproximado_con_la_carpeta_no_se_elige_solo(tmp_path):
    # «Telegrams» no está en la lista de genéricas: se busca, pero un parecido aproximado no basta
    f = tmp_path / "Telegrams" / "1x03 - Algo.mkv"
    f.parent.mkdir()
    f.write_bytes(b"")
    res = search_for(analyze(f), _searcher([{"id": 1, "name": "Techegram", "first_air_date": "2026-01-01"}]))
    assert res.candidates and res.chosen is None


def test_carpeta_que_cuadra_se_elige_sola(tmp_path):
    f = tmp_path / "Techegram (2026)" / "Season 01" / "1x03.mkv"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"")
    res = search_for(analyze(f), _searcher([{"id": 1, "name": "Techegram", "first_air_date": "2026-01-01"}]))
    assert res.chosen is not None and res.chosen.id == 1


def test_titulo_del_archivo_mantiene_el_umbral_normal(tmp_path):
    f = tmp_path / "Telegrams 1x03.mkv"
    f.write_bytes(b"")
    res = search_for(analyze(f), _searcher([{"id": 1, "name": "Techegram", "first_air_date": "2026-01-01"}]))
    assert res.parsed.title == "Telegrams" and not res.parsed.title_from_folder
