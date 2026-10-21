from videodl.errors import clean_ytdlp_error


def test_removes_error_prefix_and_extra_lines():
    assert clean_ytdlp_error("ERROR: algo\nsegunda linea") == "No se pudo procesar la URL: algo"


def test_unsupported_url():
    assert "compatible" in clean_ytdlp_error("ERROR: Unsupported URL: xyz")


def test_private_video():
    assert "privado" in clean_ytdlp_error("ERROR: Private video")


def test_age_restriction():
    msg = clean_ytdlp_error("ERROR: Sign in to confirm your age")
    assert "edad" in msg or "iniciar sesión" in msg


def test_age_restriction_con_guion():
    assert "edad" in clean_ytdlp_error("ERROR: This video is age-restricted")


def test_error_generico_no_se_confunde_con_restriccion_de_edad():
    """El aviso de yt-dlp contiene «webpage» (lleva «age») y «Confirm», así que
    antes cualquier fallo genérico se traducía como restricción de edad."""
    msg = clean_ytdlp_error(
        "ERROR: [TikTok] 123: Unexpected response from webpage request; please report "
        "this issue on https://github.com/yt-dlp/yt-dlp/issues?q= , filling out the "
        "appropriate issue template. Confirm you are on the latest version using yt-dlp -U"
    )
    assert "edad" not in msg
    assert "No se pudo procesar la URL" in msg


def test_rate_limit():
    assert "limitó" in clean_ytdlp_error("ERROR: HTTP Error 429: Too Many Requests")


def test_bot_check_indica_como_solucionarlo():
    msg = clean_ytdlp_error(
        "ERROR: Sign in to confirm you're not a bot. Use --cookies for the authentication."
    )
    assert "cookies" in msg.lower()


AVISO_COOKIES_ROTADAS = (
    "[youtube] The provided YouTube account cookies are no longer valid. They have "
    "likely been rotated in the browser as a security measure."
)


def test_reconoce_el_aviso_de_cookies_rotadas():
    from videodl import errors

    errors.olvidar_cookies_rotadas()
    try:
        assert errors.cookies_rotadas() is False
        assert errors.aviso_cookies_rotadas("otra cosa") is False
        assert errors.cookies_rotadas() is False

        assert errors.aviso_cookies_rotadas(AVISO_COOKIES_ROTADAS) is True
        assert errors.cookies_rotadas() is True
    finally:
        errors.olvidar_cookies_rotadas()


def test_anti_bot_con_cookies_rotadas_lo_explica():
    """El anti-bot con cookies rotadas no es «configura cookies»: hay que renovarlas."""
    from videodl import errors

    errors.olvidar_cookies_rotadas()
    errors.aviso_cookies_rotadas(AVISO_COOKIES_ROTADAS)
    try:
        msg = clean_ytdlp_error("ERROR: Sign in to confirm you're not a bot.")
        assert "rot" in msg.lower() or "inválid" in msg.lower() or "invalid" in msg.lower()
        assert "exportar" in msg.lower()
    finally:
        errors.olvidar_cookies_rotadas()


def test_anti_bot_sin_aviso_de_rotacion_mantiene_el_mensaje_general():
    from videodl import errors

    errors.olvidar_cookies_rotadas()
    msg = clean_ytdlp_error("ERROR: Sign in to confirm you're not a bot.")
    assert "proxy" in msg.lower()


REDDIT_SIN_SESION = (
    "ERROR: [Reddit] 1x9yenj: Account authentication is required. Use "
    "--cookies-from-browser or --cookies for the authentication. See "
    "https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp "
    "for how to manually pass cookies"
)


def test_reddit_pide_sesion_lo_explica_en_espanol():
    msg = clean_ytdlp_error(REDDIT_SIN_SESION)

    assert "cookies" in msg.lower()
    assert "sesión" in msg.lower()
    # Nada del inglés de yt-dlp ni de sus enlaces.
    assert "yt-dlp" not in msg
    assert "authentication" not in msg.lower()


def test_el_anti_bot_de_youtube_no_se_confunde_con_reddit():
    """El aviso de YouTube también trae «--cookies-from-browser»: manda su rama."""
    from videodl import errors

    errors.olvidar_cookies_rotadas()
    msg = clean_ytdlp_error(
        "ERROR: [youtube] x: Sign in to confirm you're not a bot. Use "
        "--cookies-from-browser or --cookies for the authentication."
    )

    assert "Reddit" not in msg
    assert "proxy" in msg.lower()


def test_reddit_bloqueando_la_ip_menciona_el_proxy():
    msg = clean_ytdlp_error(
        "ERROR: [Reddit] x: Your IP address is unable to access the Reddit API"
    )

    assert "proxy" in msg.lower()


# ---------------------------------------------------------------------------
# Pista de cookies: «añade cookies» no dice si el tarro llegó ni qué trae
# ---------------------------------------------------------------------------

REDDIT_URL = "https://www.reddit.com/comments/1x9yenj/"
JAR_REDDIT_ANONIMO = "# Netscape HTTP Cookie File\n.reddit.com\tTRUE\t/\tFALSE\t0\tloid\tabc\n"
JAR_REDDIT_CON_SESION = (
    "# Netscape HTTP Cookie File\n"
    "#HttpOnly_.reddit.com\tTRUE\t/\tTRUE\t0\treddit_session\tsecreto\n"
    ".reddit.com\tTRUE\t/\tFALSE\t0\tloid\tabc\n"
)


def _usar_tarro(monkeypatch, tmp_path, contenido):
    from videodl import config

    if contenido is None:
        monkeypatch.setattr(config.cookies, "file", None)
        return
    archivo = tmp_path / "reddit.txt"
    archivo.write_text(contenido, encoding="utf-8")
    monkeypatch.setattr(config.cookies, "file", str(archivo))


def test_la_pista_avisa_de_que_no_hay_cookies_de_esa_web(tmp_path, monkeypatch):
    _usar_tarro(monkeypatch, tmp_path, None)

    msg = clean_ytdlp_error(REDDIT_SIN_SESION, REDDIT_URL)

    assert "no hay ninguna cookie de esta web" in msg.lower()


def test_la_pista_avisa_de_que_el_tarro_no_trae_sesion(tmp_path, monkeypatch):
    """El error típico: el fichero está, pero se exportó sin la cuenta abierta."""
    _usar_tarro(monkeypatch, tmp_path, JAR_REDDIT_ANONIMO)

    msg = clean_ytdlp_error(REDDIT_SIN_SESION, REDDIT_URL)

    assert "ninguna es de sesión" in msg.lower()


def test_la_pista_avisa_de_que_la_sesion_caduco(tmp_path, monkeypatch):
    """La cookie está, pero caducada: parece configurada y no autentica nada."""
    _usar_tarro(
        monkeypatch,
        tmp_path,
        "# Netscape HTTP Cookie File\n"
        "#HttpOnly_.reddit.com\tTRUE\t/\tTRUE\t1000000000\treddit_session\tvieja\n",
    )

    msg = clean_ytdlp_error(REDDIT_SIN_SESION, REDDIT_URL)

    assert "caducada" in msg.lower()


def test_la_pista_cuenta_las_cookies_con_sesion(tmp_path, monkeypatch):
    _usar_tarro(monkeypatch, tmp_path, JAR_REDDIT_CON_SESION)

    msg = clean_ytdlp_error(REDDIT_SIN_SESION, REDDIT_URL)

    assert "2 cookies de esta web con sesión vigente" in msg


def test_la_pista_no_se_añade_a_errores_que_no_son_de_sesion(tmp_path, monkeypatch):
    _usar_tarro(monkeypatch, tmp_path, JAR_REDDIT_CON_SESION)

    msg = clean_ytdlp_error("ERROR: Unsupported URL: xyz", REDDIT_URL)

    assert msg == "Esta URL no es compatible con ninguna plataforma soportada."


def test_la_pista_no_tapa_el_aviso_de_cookies_rotadas(tmp_path, monkeypatch):
    """Con cookies rotadas ya se explica el motivo: sobra hablar del tarro."""
    from videodl import errors

    _usar_tarro(monkeypatch, tmp_path, JAR_REDDIT_CON_SESION)
    errors.olvidar_cookies_rotadas()
    errors.aviso_cookies_rotadas(AVISO_COOKIES_ROTADAS)
    try:
        msg = clean_ytdlp_error("ERROR: Sign in to confirm you're not a bot.", REDDIT_URL)
    finally:
        errors.olvidar_cookies_rotadas()

    assert "rot" in msg.lower()
    assert "de esta web" not in msg

def test_formatos_vacios_avisa_de_fallo_puntual():
    msg = clean_ytdlp_error(
        "ERROR: [dailymotion] xat53s6: No video formats found!; please report this "
        "issue on https://github.com/yt-dlp/yt-dlp/issues"
    )
    assert "vuelve a intentarlo" in msg
