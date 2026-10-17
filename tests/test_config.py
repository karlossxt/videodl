"""Pruebas de la carga de cookies (``setup_cookies``).

Cubren los cuatro orígenes posibles y, en particular, el caso de los Secret Files
de Render: en Docker el archivo existe en ``/etc/secrets`` pero puede no ser
legible si el usuario de la app no está en el grupo 1000.
"""

import base64
import logging
from pathlib import Path

import pytest

from videodl import config

COOKIES_OK = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tx\n"
SECRETS_INEXISTENTE = Path("videodl-secrets-que-no-existen")


@pytest.fixture(autouse=True)
def _limpiar_cookies():
    """Deja el estado global de cookies limpio después de cada prueba."""
    yield
    config.cookies.file = None
    config.cookies.error = ""
    config.cookies.source = ""


@pytest.fixture()
def _sin_variables(monkeypatch):
    for var in ("YTDLP_COOKIES_FILE", "YTDLP_COOKIES", "YTDLP_COOKIES_B64"):
        monkeypatch.delenv(var, raising=False)


def test_setup_cookies_desde_secret_file(tmp_path, monkeypatch, _sin_variables):
    """Un ``cookies.txt`` en el directorio de secretos se detecta."""
    archivo = tmp_path / "cookies.txt"
    archivo.write_text(COOKIES_OK, encoding="utf-8")
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path)

    config.setup_cookies()

    assert config.cookies.file == str(archivo)
    assert config.cookies.source == "secret-file"
    assert config.cookies.error == ""


def test_setup_cookies_avisa_si_no_hay_permisos(tmp_path, monkeypatch, caplog, _sin_variables):
    """Si el Secret File existe pero no se puede leer, se avisa (caso Docker)."""
    archivo = tmp_path / "cookies.txt"
    archivo.write_text(COOKIES_OK, encoding="utf-8")
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path)

    stat_real = Path.stat

    def stat_sin_permiso(self, *args, **kwargs):
        if self.name == "cookies.txt":
            raise PermissionError(13, "Permission denied")
        return stat_real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat_sin_permiso)

    with caplog.at_level(logging.WARNING, logger="videodl.config"):
        config.setup_cookies()

    assert config.cookies.file is None
    assert "No se pudo leer" in caplog.text


def test_setup_cookies_desde_base64(monkeypatch, _sin_variables):
    monkeypatch.setattr(config, "SECRETS_DIR", SECRETS_INEXISTENTE)
    monkeypatch.setenv("YTDLP_COOKIES_B64", base64.b64encode(COOKIES_OK.encode()).decode())

    config.setup_cookies()

    assert config.cookies.source == "YTDLP_COOKIES_B64"
    assert config.cookies.file is not None
    # El contenido se guarda sin espacios sobrantes (la app hace .strip()).
    assert Path(config.cookies.file).read_text(encoding="utf-8") == COOKIES_OK.strip()


def test_setup_cookies_descarta_contenido_invalido(monkeypatch, _sin_variables):
    monkeypatch.setattr(config, "SECRETS_DIR", SECRETS_INEXISTENTE)
    monkeypatch.setenv("YTDLP_COOKIES", "esto no es un cookies.txt")

    config.setup_cookies()

    assert config.cookies.file is None
    assert "Netscape" in config.cookies.error


def test_setup_cookies_sin_nada_es_valido(monkeypatch, _sin_variables):
    """Sin cookies la app funciona igual: no es un error de arranque."""
    monkeypatch.setattr(config, "SECRETS_DIR", SECRETS_INEXISTENTE)

    config.setup_cookies()

    assert config.cookies.file is None
    assert config.cookies.source == ""
