def test_health_ok_without_sensitive_data(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    # No debe filtrar datos sensibles: ni rutas, ni errores, ni longitudes del
    # contenido de las cookies. El *origen* sí se publica: es una etiqueta fija
    # («secret-file», «YTDLP_COOKIES_B64»…) y evita el lío de tener dos fuentes
    # configuradas y actualizar precisamente la que no se usa.
    for leaked in ("cookies_error", "cookies_origin", "env_b64_len", "env_raw_len"):
        assert leaked not in body
    # El diagnóstico de cookies es un booleano, un recuento y etiquetas.
    assert body["cookies_session"] in (True, False)
    assert isinstance(body["cookies_count"], int)
    assert body["cookies_source"] in (
        "",
        "YTDLP_COOKIES_FILE",
        "secret-file",
        "YTDLP_COOKIES",
        "YTDLP_COOKIES_B64",
    )
    # Solo el nombre del fichero, nunca una ruta.
    assert "/" not in body["cookies_file"] and "\\" not in body["cookies_file"]
    assert body["cookies_rotated"] in (True, False)


def test_health_alias(client):
    assert client.get("/health").status_code == 200


def test_compress_presets(client):
    res = client.get("/api/compress/presets")
    assert res.status_code == 200
    body = res.json()
    assert "whatsapp" in body["presets"]
    assert body["max_upload_mb"] >= 1


def test_clip_options(client):
    res = client.get("/api/clips/options")
    assert res.status_code == 200
    body = res.json()
    assert set(body["aspects"]) == {"vertical", "vertical-blur", "square", "original"}


def test_info_rejects_private_url(client):
    res = client.post("/api/info", json={"url": "http://192.168.0.1/video"})
    assert res.status_code == 400


def test_info_rejects_bad_scheme(client):
    res = client.post("/api/info", json={"url": "ftp://example.com/video"})
    assert res.status_code == 400


def test_jobs_rejects_invalid_mode(client):
    # 8.8.8.8 es una IP pública: pasa el filtro SSRF y falla por el modo.
    res = client.post("/api/jobs", json={"url": "https://8.8.8.8/v", "mode": "zzz"})
    assert res.status_code == 400


def test_thumbnail_rejects_private_url(client):
    res = client.get("/api/thumbnail", params={"url": "http://127.0.0.1/secret.png"})
    assert res.status_code == 400


def test_compress_requires_file(client):
    res = client.post("/api/compress", data={"target_mb": "16"})
    assert res.status_code == 422


def test_clip_rejects_bad_aspect(client):
    res = client.post(
        "/api/clips",
        json={"url": "https://8.8.8.8/v", "start": 0, "end": 10, "aspect": "raro"},
    )
    assert res.status_code == 400


def test_security_headers_present(client):
    res = client.get("/")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in res.headers


def test_unknown_job_returns_404(client):
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.get("/api/compress/nope").status_code == 404


def test_analysis_sends_configured_cookies(client, monkeypatch):
    """El análisis tiene que mandar las cookies, no solo la descarga.

    Era la causa del aviso anti-bot al pulsar «Analizar» en el servidor: el
    endpoint iba sin ``cookiefile`` aunque hubiera cookies configuradas.
    """
    from videodl import downloader
    from videodl.config import cookies

    captured: dict = {}

    class FakeYDL:
        def __init__(self, opts):
            captured.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            return {"title": "prueba", "formats": [], "subtitles": {}}

    monkeypatch.setattr(downloader, "ensure_public_url", lambda url: None)
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(cookies, "file", "C:/privado/cookies.txt")

    res = client.post("/api/info", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})

    assert res.status_code == 200
    assert captured["cookiefile"] == "C:/privado/cookies.txt"
    assert captured["skip_download"] is True
    assert client.get("/api/clips/nope").status_code == 404
