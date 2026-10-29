"""Pruebas de los endpoints HTTP y de las rutas retiradas."""

import pytest


def test_health_ok_without_sensitive_data(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    # Solo capacidades activas y límites públicos.
    assert set(body) == {
        "status",
        "version",
        "ffmpeg",
        "ffprobe",
        "compressor",
        "clips",
        "whatsapp",
        "qr",
        "transcribe",
        "transcribe_model",
        "transcribe_max_seconds",
        "transcribe_max_mb",
        "clip_max_seconds",
        "max_upload_mb",
        "max_target_mb",
    }
    for leaked in (
        "cookies",
        "cookies_file",
        "cookies_source",
        "impersonation",
        "disabled_platforms",
        "proxy",
        "paths",
    ):
        assert leaked not in body
    # Nunca se publican rutas del sistema.
    serialized = str(body)
    assert ":\\" not in serialized and "\\\\" not in serialized


def test_health_alias(client):
    assert client.get("/health").status_code == 200


def test_ads_txt_is_served_from_project_root(client):
    res = client.get("/ads.txt")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    assert res.text.strip() == "google.com, pub-6317177060588245, DIRECT, f08c47fec0942fa0"


def test_home_no_ofrece_descargas(client):
    res = client.get("/")
    assert res.status_code == 200
    # La portada sigue existiendo, pero ya no incluye el formulario de descargas.
    assert "/api/info" not in res.text
    assert "/api/download" not in res.text
    assert "app.js" not in res.text
    assert "Descargar vídeos" not in res.text
    # Sí enlaza a las herramientas que quedan.
    assert 'href="/comprimir-video-whatsapp"' in res.text
    assert 'href="/recortar-clip-vertical"' in res.text
    assert 'href="/link-whatsapp"' in res.text


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/info"),
        ("post", "/api/download"),
        ("post", "/api/jobs"),
        ("post", "/api/subtitles"),
        ("post", "/api/clips"),
        ("get", "/api/thumbnail"),
        ("get", "/api/jobs/abc"),
        ("get", "/api/jobs/abc/file"),
        ("post", "/api/jobs/abc/cancel"),
    ],
)
def test_rutas_del_descargador_devuelven_410(client, method, path):
    """Las rutas antiguas no deben ofrecer descargas ni quedar huérfanas."""
    res = getattr(client, method)(path)
    assert res.status_code == 410
    assert "retirado" in res.json()["detail"]


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
    assert body["max_seconds"] >= 1
    assert body["max_upload_mb"] >= 1


def test_compress_requires_file(client):
    res = client.post("/api/compress", data={"target_mb": "16"})
    assert res.status_code == 422


def test_clip_upload_requires_file(client):
    res = client.post("/api/clips/upload", data={"start": "0", "end": "10"})
    assert res.status_code == 422


def test_clip_rejects_bad_aspect(client, monkeypatch):
    from videodl import clips

    monkeypatch.setattr(clips, "FFMPEG_AVAILABLE", True)
    monkeypatch.setattr(clips, "FFPROBE_AVAILABLE", True)

    res = client.post(
        "/api/clips/upload",
        files={"file": ("video.mp4", b"datos", "video/mp4")},
        data={"start": "0", "end": "10", "aspect": "raro", "quality": "media"},
    )
    assert res.status_code == 400
    assert "Formato" in res.json()["detail"]


def test_clip_rejects_bad_extension(client, monkeypatch):
    from videodl import clips

    monkeypatch.setattr(clips, "FFMPEG_AVAILABLE", True)
    monkeypatch.setattr(clips, "FFPROBE_AVAILABLE", True)

    res = client.post(
        "/api/clips/upload",
        files={"file": ("notas.txt", b"hola", "text/plain")},
        data={"start": "0", "end": "10", "aspect": "vertical", "quality": "media"},
    )
    assert res.status_code == 400
    assert "Formato" in res.json()["detail"]


def test_clip_rejects_too_large_upload(client, monkeypatch):
    from videodl import clips, uploads

    monkeypatch.setattr(clips, "FFMPEG_AVAILABLE", True)
    monkeypatch.setattr(clips, "FFPROBE_AVAILABLE", True)
    monkeypatch.setattr(uploads, "MAX_UPLOAD_MB", 0)

    res = client.post(
        "/api/clips/upload",
        files={"file": ("video.mp4", b"demasiado", "video/mp4")},
        data={"start": "0", "end": "10", "aspect": "vertical", "quality": "media"},
    )
    assert res.status_code == 413


def test_privacy_page(client):
    """Una nota breve de privacidad, sin datos fiscales ni términos de descarga."""
    res = client.get("/privacidad")

    assert res.status_code == 200
    for texto in (
        "Privacidad",
        "Archivos y datos",
        "Datos técnicos",
        "Cookies y almacenamiento local",
        "Servicios externos",
    ):
        assert texto in res.text
    assert "legal-todo" not in res.text
    assert "Aviso legal" not in res.text
    assert "Términos de uso" not in res.text
    assert "no descarga vídeos de plataformas externas" not in res.text


def test_todas_las_paginas_enlazan_la_privacidad(client):
    for path in (
        "/",
        "/comprimir-video-whatsapp",
        "/recortar-clip-vertical",
        "/link-whatsapp",
        "/herramientas",
    ):
        res = client.get(path)
        assert res.status_code == 200
        assert 'href="/privacidad"' in res.text
        assert 'href="/legal' not in res.text


def test_security_headers_present(client):
    res = client.get("/")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in res.headers


def test_unknown_job_returns_404(client):
    assert client.get("/api/compress/nope").status_code == 404
    assert client.get("/api/clips/nope").status_code == 404


def test_unknown_job_file_returns_404(client):
    assert client.get("/api/compress/nope/file").status_code == 404
    assert client.get("/api/clips/nope/file").status_code == 404


def test_cancelar_trabajo_inexistente_devuelve_404(client):
    assert client.post("/api/compress/nope/cancel").status_code == 404
    assert client.post("/api/clips/nope/cancel").status_code == 404
