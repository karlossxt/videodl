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
# Exportado con la sesión cerrada: válido, pero no identifica a nadie.
COOKIES_ANONIMAS = (
    "# Netscape HTTP Cookie File\n"
    ".youtube.com\tTRUE\t/\tFALSE\t0\tVISITOR_INFO1_LIVE\tabc\n"
    ".youtube.com\tTRUE\t/\tFALSE\t0\tPREF\tf6=400\n"
)
# Las cookies de sesión van con #HttpOnly_ delante del dominio.
COOKIES_CON_SESION = (
    "# Netscape HTTP Cookie File\n"
    "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t0\t__Secure-1PSID\tsecreto\n"
    ".youtube.com\tTRUE\t/\tFALSE\t0\tPREF\tf6=400\n"
)
SECRETS_INEXISTENTE = Path("videodl-secrets-que-no-existen")

# Un tarro por plataforma: Reddit cerró su API a los anónimos, así que necesita
# su propia sesión, independiente de la de YouTube.
COOKIES_REDDIT = (
    "# Netscape HTTP Cookie File\n"
    "#HttpOnly_.reddit.com\tTRUE\t/\tTRUE\t0\treddit_session\tsecreto\n"
    ".reddit.com\tTRUE\t/\tFALSE\t0\tloid\tabc\n"
)


@pytest.fixture(autouse=True)
def _limpiar_cookies():
    """Deja el estado global de cookies limpio después de cada prueba."""
    yield
    config.cookies.file = None
    config.cookies.error = ""
    config.cookies.source = ""
    config.cookies.session = False
    config.cookies.count = 0
    config.cookies.origin = None
    config.cookies.raw = None
    config.cookies.extras = []
    from videodl import errors

    errors.olvidar_cookies_rotadas()


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

    assert config.cookies.file is not None
    # Nunca se usa el original: yt-dlp reescribe el fichero al cerrar y el
    # Secret File de Render es de solo lectura.
    assert config.cookies.file != str(archivo)
    assert Path(config.cookies.file).read_text(encoding="utf-8") == COOKIES_OK
    assert config.cookies.source == "secret-file"
    assert config.cookies.error == ""


def test_prefiere_el_secret_file_canonico(tmp_path, monkeypatch, _sin_variables):
    """Con varios ficheros gana ``cookies.txt``, no el que caiga por orden alfabético."""
    (tmp_path / "aaa-cookies-viejas.txt").write_text(COOKIES_ANONIMAS, encoding="utf-8")
    (tmp_path / "cookies.txt").write_text(COOKIES_CON_SESION, encoding="utf-8")
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path)

    config.setup_cookies()

    assert config.cookies.origin is not None
    assert Path(config.cookies.origin).name == "cookies.txt"
    assert config.cookies.session is True


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


def test_cookies_sin_sesion_lo_avisan(tmp_path, monkeypatch, caplog, _sin_variables):
    """Un cookies.txt exportado con la sesión cerrada no aporta nada.

    Es el fallo que más se cuela: el fichero es válido y la app lo carga, pero
    yt-dlp navega como anónimo y YouTube sigue pidiendo verificación desde la
    nube. Desde fuera parece que «las cookies no funcionan».
    """
    archivo = tmp_path / "cookies.txt"
    archivo.write_text(COOKIES_ANONIMAS, encoding="utf-8")
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path)

    with caplog.at_level(logging.WARNING, logger="videodl.config"):
        config.setup_cookies()

    assert config.cookies.file is not None
    assert config.cookies.session is False
    assert config.cookies.count == 2
    assert "no incluyen ninguna cookie de sesión" in caplog.text


def test_cookies_con_sesion_se_detectan(tmp_path, monkeypatch, _sin_variables):
    """Las cookies de sesión son HttpOnly: hay que mirar tras el ``#HttpOnly_``."""
    archivo = tmp_path / "cookies.txt"
    archivo.write_text(COOKIES_CON_SESION, encoding="utf-8")
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path)

    config.setup_cookies()

    assert config.cookies.session is True
    assert config.cookies.count == 2


def test_cookies_de_solo_lectura_se_copian_a_un_fichero_escribible(
    tmp_path, monkeypatch, _sin_variables
):
    """yt-dlp reescribe el ``cookiefile`` al cerrar cada descarga.

    Con un fichero de solo lectura (el Secret File de Render) la descarga se
    completaba y se perdía al final con un ``PermissionError``.
    """
    original = tmp_path / "cookies.txt"
    original.write_text(COOKIES_OK, encoding="utf-8")
    original.chmod(0o400)
    monkeypatch.setenv("YTDLP_COOKIES_FILE", str(original))

    config.setup_cookies()

    assert config.cookies.file is not None
    assert config.cookies.file != str(original)
    copia = Path(config.cookies.file)
    assert copia.read_text(encoding="utf-8") == COOKIES_OK
    # La copia sí se puede reescribir: es justo lo que hará yt-dlp.
    copia.write_text(COOKIES_OK, encoding="utf-8")
    assert config.cookies.source == "YTDLP_COOKIES_FILE"


def test_yt_dlp_cierra_sin_error_con_cookies_de_solo_lectura(
    tmp_path, monkeypatch, _sin_variables
):
    """Regresión del fallo real: cerrar yt-dlp no debe lanzar ``PermissionError``.

    Reproduce el caso de producción: cookies en un fichero de solo lectura,
    descarga completa y, al salir del ``with``, yt-dlp intenta guardarlas.
    """
    import yt_dlp

    original = tmp_path / "cookies.txt"
    original.write_text(COOKIES_OK, encoding="utf-8")
    original.chmod(0o400)
    monkeypatch.setenv("YTDLP_COOKIES_FILE", str(original))
    config.setup_cookies()

    with yt_dlp.YoutubeDL({"quiet": True, "cookiefile": config.cookies.file}):
        pass


def test_recargar_las_cookies_olvida_el_aviso_de_rotacion(_sin_variables):
    """Si se cambia el fichero de cookies, el aviso anterior deja de aplicar."""
    from videodl import errors

    errors.aviso_cookies_rotadas(
        "[youtube] The provided YouTube account cookies are no longer valid."
    )
    assert errors.cookies_rotadas() is True

    config.setup_cookies()

    assert errors.cookies_rotadas() is False


def test_refrescar_cookies_recupera_el_original(tmp_path, monkeypatch, _sin_variables):
    """yt-dlp reescribe la copia al cerrar: hay que rehacerla antes de cada uso.

    Regresión: si YouTube rota la sesión, yt-dlp guarda el tarro ya sin las
    cookies de sesión. Sin refrescar, la primera extracción tras el arranque
    usaba tus cookies y **todas las siguientes** iban como anónimas.
    """
    original = tmp_path / "cookies.txt"
    original.write_text(COOKIES_CON_SESION, encoding="utf-8")
    monkeypatch.setenv("YTDLP_COOKIES_FILE", str(original))
    config.setup_cookies()

    copia = Path(config.cookies.file)
    assert copia.read_text(encoding="utf-8") == COOKIES_CON_SESION

    # Lo que hace yt-dlp al cerrar: guarda el tarro, que ya perdió la sesión.
    copia.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

    assert config.refresh_cookies() is True
    assert copia.read_text(encoding="utf-8") == COOKIES_CON_SESION


def test_refrescar_cookies_desde_variable_de_entorno(monkeypatch, _sin_variables):
    """El origen también puede ser una variable: se recuerda su contenido."""
    monkeypatch.setenv("YTDLP_COOKIES", COOKIES_CON_SESION)
    config.setup_cookies()

    copia = Path(config.cookies.file)
    copia.write_text("", encoding="utf-8")

    assert config.refresh_cookies() is True
    # El contenido de la variable se normaliza al cargarlo (sin espacios sobrantes).
    assert copia.read_text(encoding="utf-8") == COOKIES_CON_SESION.strip()


def test_refrescar_cookies_sin_cookies_no_falla(_sin_variables):
    config.setup_cookies()

    assert config.cookies.file is None
    assert config.refresh_cookies() is False


def test_refrescar_cookies_olvida_el_aviso_de_rotacion(tmp_path, monkeypatch, _sin_variables):
    from videodl import errors

    original = tmp_path / "cookies.txt"
    original.write_text(COOKIES_CON_SESION, encoding="utf-8")
    monkeypatch.setenv("YTDLP_COOKIES_FILE", str(original))
    config.setup_cookies()

    errors.aviso_cookies_rotadas(
        "[youtube] The provided YouTube account cookies are no longer valid."
    )
    config.refresh_cookies()

    assert errors.cookies_rotadas() is False


def test_une_varios_secret_files_de_cookies(tmp_path, monkeypatch, _sin_variables):
    """Un Secret File por plataforma: YouTube y Reddit conviven en la copia.

    Las cookies van por dominio, así que no se estorban: cada web recibe solo las
    suyas. Es lo que permite tener YouTube y Reddit a la vez en Render.
    """
    (tmp_path / "cookies.txt").write_text(COOKIES_CON_SESION, encoding="utf-8")
    (tmp_path / "reddit.txt").write_text(COOKIES_REDDIT, encoding="utf-8")
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path)

    config.setup_cookies()

    assert config.cookies.source == "secret-file"
    assert Path(config.cookies.origin).name == "cookies.txt"
    assert [Path(extra).name for extra in config.cookies.extras] == ["reddit.txt"]

    contenido = Path(config.cookies.file).read_text(encoding="utf-8")
    assert ".youtube.com" in contenido
    assert ".reddit.com" in contenido
    # Una sola cabecera: la del principal.
    assert contenido.count("# Netscape HTTP Cookie File") == 1
    # La sesión de YouTube sigue contando: los extras no la tapan.
    assert config.cookies.session is True
    assert config.cookies.count == 4


def test_los_extras_no_pisan_al_fichero_principal(tmp_path, monkeypatch, _sin_variables):
    """Ante una cookie repetida gana la del principal: añadir tarros solo suma."""
    (tmp_path / "cookies.txt").write_text(
        "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tFALSE\t0\tPREF\tBUENA\n",
        encoding="utf-8",
    )
    (tmp_path / "viejo.txt").write_text(
        "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tFALSE\t0\tPREF\tMALA\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path)

    config.setup_cookies()

    contenido = Path(config.cookies.file).read_text(encoding="utf-8")
    assert "BUENA" in contenido
    assert "MALA" not in contenido


def test_ignora_los_secret_files_que_no_son_cookies(tmp_path, monkeypatch, _sin_variables):
    """Se detectan por contenido: una clave o un JSON no se mezclan."""
    (tmp_path / "cookies.txt").write_text(COOKIES_OK, encoding="utf-8")
    (tmp_path / "credenciales.json").write_text('{"token": "abc"}', encoding="utf-8")
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path)

    config.setup_cookies()

    assert config.cookies.extras == []
    contenido = Path(config.cookies.file).read_text(encoding="utf-8")
    assert "token" not in contenido


def test_refrescar_cookies_vuelve_a_unir_principal_y_extras(
    tmp_path, monkeypatch, _sin_variables
):
    """El refresco previo a cada extracción también reúne los dos tarros."""
    (tmp_path / "cookies.txt").write_text(COOKIES_CON_SESION, encoding="utf-8")
    (tmp_path / "reddit.txt").write_text(COOKIES_REDDIT, encoding="utf-8")
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path)
    config.setup_cookies()

    # Lo que hace yt-dlp al cerrar: reescribe la copia con lo que le queda.
    Path(config.cookies.file).write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

    assert config.refresh_cookies() is True
    contenido = Path(config.cookies.file).read_text(encoding="utf-8")
    assert ".youtube.com" in contenido
    assert ".reddit.com" in contenido


def test_cookie_file_names_lista_los_nombres_nunca_rutas(
    tmp_path, monkeypatch, _sin_variables
):
    (tmp_path / "cookies.txt").write_text(COOKIES_CON_SESION, encoding="utf-8")
    (tmp_path / "reddit.txt").write_text(COOKIES_REDDIT, encoding="utf-8")
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path)
    config.setup_cookies()

    etiqueta = config.cookie_file_names()

    assert etiqueta == "cookies.txt, reddit.txt"
    assert "/" not in etiqueta and "\\" not in etiqueta


# ---------------------------------------------------------------------------
# cookie_status: qué hay de cada web en la copia de trabajo
# ---------------------------------------------------------------------------


def test_cookie_status_cuenta_cada_web_por_separado(tmp_path, monkeypatch, _sin_variables):
    """YouTube y Reddit tienen tarros distintos: cada uno ve solo las suyas."""
    (tmp_path / "cookies.txt").write_text(COOKIES_CON_SESION, encoding="utf-8")
    (tmp_path / "reddit.txt").write_text(COOKIES_REDDIT, encoding="utf-8")
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path)
    config.setup_cookies()

    assert config.cookie_status("https://www.reddit.com/comments/1x9yenj/") == (2, True)
    assert config.cookie_status("https://www.youtube.com/watch?v=x") == (2, True)
    assert config.cookie_status("https://vimeo.com/1") == (0, False)


def test_cookie_status_ve_que_falta_la_sesion(tmp_path, monkeypatch, _sin_variables):
    """Un tarro exportado sin cuenta tiene cookies, pero ninguna de sesión."""
    archivo = tmp_path / "cookies.txt"
    archivo.write_text(COOKIES_ANONIMAS, encoding="utf-8")
    monkeypatch.setenv("YTDLP_COOKIES_FILE", str(archivo))
    config.setup_cookies()

    assert config.cookie_status("https://www.youtube.com/watch?v=x") == (2, False)


def test_cookie_status_sin_cookies_cargadas(_sin_variables):
    config.setup_cookies()

    assert config.cookies.file is None
    assert config.cookie_status("https://www.reddit.com/x") == (0, False)
