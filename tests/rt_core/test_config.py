import json
import os
import stat

import pytest

from retitler.config import KeyStore, Settings


class FakeKeyring:
    def __init__(self, fail=False):
        self.data, self.fail = {}, fail

    def get_password(self, service, account):
        if self.fail:
            raise RuntimeError("locked")
        return self.data.get((service, account))

    def set_password(self, service, account, value):
        if self.fail:
            raise RuntimeError("no backend")
        self.data[(service, account)] = value

    def delete_password(self, service, account):
        self.data.pop((service, account), None)


@pytest.fixture(autouse=True)
def no_env(monkeypatch):
    monkeypatch.delenv("TMDB_API_KEY", raising=False)


def test_settings_roundtrip_and_permissions(tmp_path):
    path = tmp_path / "sub" / "config.json"
    Settings(language="en", series_template="{series} {season}x{episode:02}").save(path)
    loaded = Settings.load(path)
    assert (loaded.language, loaded.series_template) == ("en", "{series} {season}x{episode:02}")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_settings_ignore_invalid_values(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"language": "fr", "series_template": "{nope}", "movie_template": "  "}))
    assert Settings.load(path) == Settings()


@pytest.mark.parametrize("content", ["", "{{{", "[1, 2]", "null"])
def test_settings_survive_garbage(tmp_path, content):
    path = tmp_path / "c.json"
    path.write_text(content)
    assert Settings.load(path) == Settings()
    assert Settings.load(tmp_path / "no-existe.json") == Settings()


def test_key_goes_to_keyring_when_available(tmp_path):
    kr = FakeKeyring()
    ks = KeyStore(tmp_path / "s.json", keyring_backend=kr)
    assert ks.set("  abc  ") == "keyring"
    assert (ks.get(), ks.source()) == ("abc", "keyring")
    assert not (tmp_path / "s.json").exists()


def test_key_falls_back_to_0600_file(tmp_path):
    for backend in (None, FakeKeyring(fail=True)):
        path = tmp_path / "s.json"
        ks = KeyStore(path, keyring_backend=backend)
        assert ks.set("abc") == "file"
        assert (ks.get(), ks.source()) == ("abc", "file")
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        ks.clear()
        assert ks.get() is None and not path.exists()


def test_env_var_has_priority(tmp_path, monkeypatch):
    ks = KeyStore(tmp_path / "s.json", keyring_backend=FakeKeyring())
    ks.set("guardada")
    monkeypatch.setenv("TMDB_API_KEY", "de-entorno")
    assert (ks.get(), ks.source()) == ("de-entorno", "env")


def test_changing_key_replaces_it_and_moving_to_keyring_removes_plain_copy(tmp_path):
    path = tmp_path / "s.json"
    KeyStore(path, keyring_backend=None).set("vieja")
    ks = KeyStore(path, keyring_backend=FakeKeyring())
    ks.set("nueva")
    assert ks.get() == "nueva" and not path.exists()


def test_empty_key_rejected(tmp_path):
    with pytest.raises(ValueError):
        KeyStore(tmp_path / "s.json", keyring_backend=None).set("   ")


def test_keystore_keeps_one_key_per_service(tmp_path, monkeypatch):
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    monkeypatch.delenv("OMDB_API_KEY", raising=False)
    path = tmp_path / "s.json"
    tmdb = KeyStore(path, keyring_backend=None)
    omdb = tmdb.for_service("omdb")
    tmdb.set("tmdb-key")
    omdb.set("omdb-key")
    assert (tmdb.get(), omdb.get()) == ("tmdb-key", "omdb-key")
    omdb.clear()
    assert (tmdb.get(), omdb.get()) == ("tmdb-key", None) and path.exists()
    tmdb.clear()
    assert not path.exists()                                    # sin claves, no queda el archivo


def test_omdb_key_from_environment_and_keyring(tmp_path, monkeypatch):
    monkeypatch.setenv("OMDB_API_KEY", "desde-entorno")
    ks = KeyStore(tmp_path / "s.json", keyring_backend=None).for_service("omdb")
    assert ks.get() == "desde-entorno" and ks.source() == "env"
    monkeypatch.delenv("OMDB_API_KEY")

    class Kr:
        data = {}
        def get_password(self, s, a): return self.data.get((s, a))
        def set_password(self, s, a, v): self.data[(s, a)] = v
        def delete_password(self, s, a): self.data.pop((s, a), None)

    kr = Kr()
    both = KeyStore(tmp_path / "k.json", keyring_backend=kr)
    both.for_service("omdb").set("o")
    assert kr.data == {("tuxenc", "omdb_api_key"): "o"} and both.for_service("omdb").source() == "keyring"
    assert both.get() is None or both.source() is None


def test_keyring_that_silently_drops_falls_back_to_file(tmp_path):
    class Dropping:
        def set_password(self, *a): pass
        def get_password(self, *a): return None
        def delete_password(self, *a): pass
    ks = KeyStore(tmp_path / "s.json", Dropping())
    assert ks.set("abc") == "file" and ks.get() == "abc"
