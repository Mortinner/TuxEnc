"""Claves integradas al compilar: ofuscadas, fuera del código y siempre por debajo de la del usuario."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_roundtrip_and_not_plain():
    from tuxenc.builtin_keys import obfuscate, render_module, reveal
    k = "00000000-1111-2222-3333-444444444444"
    assert reveal(obfuscate(k)) == k
    mod = render_module({"tmdb": "abc123", "tvdb": k, "omdb": ""})
    assert k not in mod and "abc123" not in mod and "omdb" not in mod


def test_user_key_wins_over_builtin(tmp_path, monkeypatch):
    from retitler.config import KeyStore
    monkeypatch.setattr(KeyStore, "BUILTIN", {"tmdb": "integrada"})
    ks = KeyStore(tmp_path / "secrets.json", keyring_backend=None, name="tmdb")
    assert ks.get() == "integrada" and ks.source() == "builtin" and ks.user_key() is None
    ks.set("mia")
    assert ks.get() == "mia" and ks.source() == "file"
    ks.clear()
    assert ks.get() == "integrada"
    assert KeyStore(tmp_path / "s.json", keyring_backend=None, name="omdb").get() is None


def test_no_key_in_sources():
    """Ninguna clave real en el código (las del AppImage oficial viven en packaging/keys.env)."""
    env = ROOT / "packaging" / "keys.env"
    if not env.exists():
        return
    secrets = [l.partition("=")[2].strip() for l in env.read_text().splitlines() if "=" in l and not l.startswith("#")]
    secrets = [s for s in secrets if s]
    for path in list((ROOT / "tuxenc").rglob("*.py")) + list((ROOT / "retitler").rglob("*.py")) + [ROOT / "README.md"]:
        if path.name == "_builtin_keys.py":
            continue
        text = path.read_text(encoding="utf-8")
        for s in secrets:
            assert s not in text, f"clave en {path}"
