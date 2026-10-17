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


def test_rate_limit():
    assert "limitó" in clean_ytdlp_error("ERROR: HTTP Error 429: Too Many Requests")


def test_bot_check_indica_como_solucionarlo():
    msg = clean_ytdlp_error(
        "ERROR: Sign in to confirm you're not a bot. Use --cookies for the authentication."
    )
    assert "cookies" in msg.lower()
