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
