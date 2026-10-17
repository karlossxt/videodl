import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture()
def client():
    return TestClient(app)


def test_health_ok_without_sensitive_data(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    # No debe filtrar configuración sensible.
    for leaked in ("cookies_source", "cookies_error", "env_b64_len", "env_raw_len"):
        assert leaked not in body


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
    assert client.get("/api/clips/nope").status_code == 404
