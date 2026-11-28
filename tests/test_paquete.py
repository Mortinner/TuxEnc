"""Detección de TuxEnc instalado como paquete del sistema (tuxenc-bin)."""
from pathlib import Path

from tuxenc import integration


def test_variable_del_lanzador(monkeypatch):
    monkeypatch.setenv("TUXENC_PACKAGED", "pacman")
    assert integration.packaged() == "pacman"


def test_sin_variable_ni_ruta_del_sistema(monkeypatch):
    monkeypatch.delenv("TUXENC_PACKAGED", raising=False)
    monkeypatch.delenv("APPIMAGE", raising=False)
    assert integration.packaged() == ""          # desde el código (no está en /opt ni /usr)


def test_extraido_en_opt_sin_variable(monkeypatch):
    monkeypatch.delenv("TUXENC_PACKAGED", raising=False)
    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.setattr(integration, "PKG_DIR", Path("/opt/tuxenc/usr/app/tuxenc"))
    assert integration.packaged() == "system"


def test_el_appimage_suelto_no_es_paquete(monkeypatch):
    monkeypatch.delenv("TUXENC_PACKAGED", raising=False)
    monkeypatch.setenv("APPIMAGE", "/home/u/Descargas/TuxEnc.AppImage")
    monkeypatch.setattr(integration, "PKG_DIR", Path("/tmp/.mount_TuxEnc/usr/app/tuxenc"))
    assert integration.packaged() == ""


def test_quitar_copia_deja_otro_acceso_directo(tmp_path, monkeypatch):
    # Todo en carpetas temporales: nunca tocar la copia de verdad de quien lanza las pruebas
    data = tmp_path / "data"
    data.mkdir()
    for name, value in (("DATA_DIR", data), ("MANIFEST", data / "manifest.json"),
                        ("INSTALLED_APPIMAGE", data / "TuxEnc.AppImage"),
                        ("APPS_DIR", tmp_path / "apps"), ("ICONS_DIR", tmp_path / "icons")):
        monkeypatch.setattr(integration, name, value)
    monkeypatch.setattr(integration, "_refresh_caches", lambda: None)
    desk = tmp_path / "Escritorio"
    desk.mkdir()
    monkeypatch.setattr(integration, "desktop_dir", lambda: desk)
    mine = desk / "tuxenc.desktop"
    mine.write_text("[Desktop Entry]\nExec=/usr/bin/tuxenc %F\n")   # acceso directo del paquete
    (data / "TuxEnc.AppImage").write_bytes(b"x")
    integration.remove_appimage_copy()
    assert mine.exists() and not (data / "TuxEnc.AppImage").exists()
    mine.write_text(f"[Desktop Entry]\nExec={data / 'TuxEnc.AppImage'} %F\n")   # el de la copia AppImage
    integration.remove_appimage_copy()
    assert not mine.exists()
