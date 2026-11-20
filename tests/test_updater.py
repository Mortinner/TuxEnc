"""Actualizador: comprobar versiones, descargar, verificar (SHA-256, AppImage) e instalar/volver atrás.

Usa un servidor HTTP local que imita la API de Releases de GitHub y sus descargas.
"""
import hashlib
import io
import json
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tuxenc import updater  # noqa: E402

FAKE_APPIMAGE = b"\x7fELF\x02\x01\x01\x00AI\x02" + b"\x00" * 4000


def make_zip(version: str, payload: bytes = FAKE_APPIMAGE, member: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        base = f"TuxEnc-{version}"
        z.writestr(member or f"{base}/{base}-x86_64.AppImage", payload)
        z.writestr(f"{base}/README.md", "léeme")
    return buf.getvalue()


class Server:
    """Imita api.github.com/repos/…/releases y las descargas de los assets."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.releases: list[dict] = []
        self.slow = 0.0                  # segundos entre trozos de 64 KB (para ver la barra de progreso)
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):  # noqa: N802
                if self.path.startswith("/api/releases"):
                    body = json.dumps(outer.releases).encode()
                elif self.path in outer.files:
                    body = outer.files[self.path]
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if not outer.slow:
                    self.wfile.write(body)
                    return
                import time
                for i in range(0, len(body), 65536):
                    self.wfile.write(body[i:i + 65536])
                    time.sleep(outer.slow)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def publish(self, version: str, zip_bytes: bytes | None = None, sums: str | None = None,
                notes: str = "", prerelease=False, draft=False, assets=True) -> None:
        zname = f"TuxEnc-{version}-linux-x86_64.zip"
        zb = make_zip(version) if zip_bytes is None else zip_bytes
        self.files[f"/dl/{version}/{zname}"] = zb
        if sums is None:
            sums = f"{hashlib.sha256(zb).hexdigest()}  {zname}\n"
        self.files[f"/dl/{version}/SHA256SUMS"] = sums.encode()
        rel = {"tag_name": f"v{version}", "html_url": f"{self.base}/rel/{version}", "body": notes,
               "draft": draft, "prerelease": prerelease, "published_at": "2026-11-21T10:00:00Z",
               "assets": []}
        if assets:
            rel["assets"] = [
                {"name": zname, "size": len(zb), "browser_download_url": f"{self.base}/dl/{version}/{zname}"},
                {"name": "SHA256SUMS", "size": len(sums), "browser_download_url": f"{self.base}/dl/{version}/SHA256SUMS"},
            ]
        self.releases.append(rel)

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def env(tmp_path, monkeypatch):
    srv = Server()
    monkeypatch.setenv(updater.API_OVERRIDE_ENV, srv.base + "/api/releases")
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(updater, "INSTALLED", data / "TuxEnc.AppImage")
    monkeypatch.setattr(updater, "PREVIOUS", data / "TuxEnc-anterior.AppImage")
    monkeypatch.setattr(updater, "PREVIOUS_INFO", data / "anterior.json")
    monkeypatch.setattr(updater, "STAGING", data / ".actualizacion")
    monkeypatch.setattr(updater, "LOG_FILE", tmp_path / "actualizaciones.log")
    (data / "TuxEnc.AppImage").write_bytes(FAKE_APPIMAGE + b"OLD")
    yield srv, data
    srv.close()


NOTES = ("\n### Corregido\n- Arreglo en español.\n\n### English\n- Fix in English.\n\n---\n"
         "**Descarga:** el archivo adjunto. Comprueba la descarga con `sha256sum -c SHA256SUMS`.\n")


def test_check_lists_only_newer_published_versions(env):
    srv, _ = env
    for v in ("1.2.6", "1.2.7", "1.3.0"):
        srv.publish(v, notes=NOTES)
    srv.publish("1.4.0", prerelease=True)
    srv.publish("1.5.0", draft=True)
    srv.releases.append({"tag_name": "nightly", "assets": []})
    info = updater.check("1.2.6")
    assert [r.version for r in info.newer] == ["1.3.0", "1.2.7"]
    assert info.latest.installable and info.latest.zip_size > 0
    assert updater.check("1.3.0") is None
    assert updater.check("1.3.0-dev.2").latest.version == "1.3.0"     # una dev va antes que su versión


def test_notes_follow_interface_language_without_download_footer(env):
    srv, _ = env
    srv.publish("1.2.7", notes=NOTES)
    rel = updater.check("1.2.6").latest
    assert updater.release_notes(rel, "es") == "### Corregido\n- Arreglo en español."
    assert updater.release_notes(rel, "en") == "- Fix in English."
    md = updater.notes_markdown(updater.check("1.2.6"), "es")
    assert md.startswith("## TuxEnc 1.2.7 · 2026-11-21") and "Descarga" not in md


def test_network_error_is_reported(monkeypatch):
    monkeypatch.setenv(updater.API_OVERRIDE_ENV, "http://127.0.0.1:9/api/releases")
    with pytest.raises(updater.UpdateError) as e:
        updater.check("1.2.6")
    assert e.value.code == "network"


def test_only_github_over_https_is_trusted(monkeypatch):
    monkeypatch.delenv(updater.API_OVERRIDE_ENV, raising=False)
    ok = ["https://api.github.com/repos/Mortinner/TuxEnc/releases",
          "https://github.com/Mortinner/TuxEnc/releases/download/v1.2.7/x.zip",
          "https://objects.githubusercontent.com/github-production-release-asset/abc",
          "https://release-assets.githubusercontent.com/abc"]
    bad = ["http://github.com/x", "https://github.com.evil.com/x", "https://evilgithub.com/x",
           "https://example.com/TuxEnc.zip", "file:///etc/passwd"]
    assert all(updater._trusted(u) for u in ok)
    assert not any(updater._trusted(u) for u in bad)


def test_update_installs_and_keeps_previous(env):
    srv, data = env
    srv.publish("1.2.7")
    rel = updater.check("1.2.6").latest
    seen = []
    app = updater.prepare(rel, progress=lambda d, t: seen.append((d, t)))
    assert updater.is_appimage(app)
    updater.install(app, "1.2.7", running_version="1.2.6")
    assert (data / "TuxEnc.AppImage").read_bytes() == FAKE_APPIMAGE
    assert (data / "TuxEnc-anterior.AppImage").read_bytes().endswith(b"OLD")
    assert updater.previous_version() == "1.2.6"
    assert not (data / ".actualizacion").exists()
    assert seen and seen[-1][0] == seen[-1][1]


@pytest.mark.parametrize("case,code", [
    ("checksum", "checksum"), ("no_line", "no_checksum"), ("no_member", "bad_zip"),
    ("not_appimage", "not_appimage"), ("not_zip", "bad_zip"), ("no_assets", "no_assets"),
])
def test_bad_downloads_install_nothing(env, case, code):
    srv, data = env
    if case == "checksum":
        srv.publish("1.2.7", sums="0" * 64 + "  TuxEnc-1.2.7-linux-x86_64.zip\n")
    elif case == "no_line":
        srv.publish("1.2.7", sums="0" * 64 + "  otra-cosa.zip\n")
    elif case == "no_member":
        srv.publish("1.2.7", zip_bytes=make_zip("1.2.7", member="TuxEnc-1.2.7/otro.AppImage"))
    elif case == "not_appimage":
        srv.publish("1.2.7", zip_bytes=make_zip("1.2.7", payload=b"#!/bin/sh\nrm -rf ~\n"))
    elif case == "not_zip":
        srv.publish("1.2.7", zip_bytes=b"esto no es un zip")
    elif case == "no_assets":
        srv.publish("1.2.7", assets=False)
    before = (data / "TuxEnc.AppImage").read_bytes()
    rel = updater.check("1.2.6").latest
    with pytest.raises(updater.UpdateError) as e:
        updater.prepare(rel)
    assert e.value.code == code
    assert (data / "TuxEnc.AppImage").read_bytes() == before
    assert not (data / "TuxEnc-anterior.AppImage").exists()
    assert not (data / ".actualizacion").exists()


def test_download_from_untrusted_host_is_refused(env):
    srv, data = env
    srv.publish("1.2.7")
    rel = updater.check("1.2.6").latest
    rel.zip_url = rel.zip_url.replace("127.0.0.1", "localhost")      # otro origen que el de la API
    with pytest.raises(updater.UpdateError) as e:
        updater.prepare(rel)
    assert e.value.code == "untrusted"


def test_cancel_leaves_everything_as_it_was(env):
    srv, data = env
    srv.publish("1.2.7", zip_bytes=make_zip("1.2.7", payload=FAKE_APPIMAGE + b"x" * 3_000_000))
    rel = updater.check("1.2.6").latest
    cancel = threading.Event()
    with pytest.raises(updater.Cancelled):
        updater.prepare(rel, progress=lambda d, t: cancel.set(), cancel=cancel)
    assert (data / "TuxEnc.AppImage").read_bytes().endswith(b"OLD")
    assert not (data / ".actualizacion").exists()


def test_rollback_swaps_versions_and_refuses_while_pending(env):
    srv, data = env
    srv.publish("1.2.7")
    app = updater.prepare(updater.check("1.2.6").latest)
    updater.install(app, "1.2.7", running_version="1.2.6")
    # Recién instalada, sin reiniciar: el que corre sigue siendo la 1.2.6 → no se puede «volver»
    with pytest.raises(updater.UpdateError) as e:
        updater.rollback(running_version="1.2.6")
    assert e.value.code == "pending"
    # Ya reiniciado en la 1.2.7: vuelve a la 1.2.6 y la 1.2.7 queda guardada
    assert updater.rollback(running_version="1.2.7") == "1.2.6"
    assert (data / "TuxEnc.AppImage").read_bytes().endswith(b"OLD")
    assert (data / "TuxEnc-anterior.AppImage").read_bytes() == FAKE_APPIMAGE
    assert updater.previous_version() == "1.2.7"
    assert not (data / "TuxEnc.AppImage.swap").exists()


def test_no_space_is_checked_before_downloading(env, monkeypatch):
    srv, _ = env
    srv.publish("1.2.7")
    monkeypatch.setattr(updater, "free_bytes", lambda p: 10 * 1024 * 1024)
    with pytest.raises(updater.UpdateError) as e:
        updater.prepare(updater.check("1.2.6").latest)
    assert e.value.code == "no_space"
