"""Procedencia de la compilación («Acerca de»): oficial (GitHub Actions), local o desde el código."""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tuxenc import VERSION, build_info  # noqa: E402


def _install(monkeypatch, source: str | None):
    if source is None:
        monkeypatch.setitem(sys.modules, "tuxenc._build_info", None)    # import falla
        return
    mod = types.ModuleType("tuxenc._build_info")
    exec(source, mod.__dict__)
    monkeypatch.setitem(sys.modules, "tuxenc._build_info", mod)


def test_official_build_from_github_actions(monkeypatch):
    env = {"GITHUB_ACTIONS": "true", "GITHUB_SHA": "a" * 40, "GITHUB_REPOSITORY": "Mortinner/TuxEnc",
           "GITHUB_RUN_ID": "123", "GITHUB_SERVER_URL": "https://github.com", "TUXENC_KEY_TMDB": "secreto"}
    src = build_info.render_module(env, "2026-11-21 10:00 UTC")
    assert "secreto" not in src                       # solo los datos del CI, nada más del entorno
    _install(monkeypatch, src)
    info = build_info.load()
    assert info["kind"] == "official"
    assert info["commit_url"] == "https://github.com/Mortinner/TuxEnc/commit/" + "a" * 40
    assert info["run_url"] == "https://github.com/Mortinner/TuxEnc/actions/runs/123"
    assert info["release_url"] == f"https://github.com/Mortinner/TuxEnc/releases/tag/v{VERSION}"


def test_local_build(monkeypatch):
    _install(monkeypatch, build_info.render_module({"HOME": "/home/x"}, "2026-11-21 10:00 UTC"))
    assert build_info.load() == {"kind": "local", "built": "2026-11-21 10:00 UTC"}


def test_running_from_source(monkeypatch):
    _install(monkeypatch, None)
    assert build_info.load() == {"kind": "source"}
