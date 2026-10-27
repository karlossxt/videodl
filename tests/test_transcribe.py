"""Pruebas de la transcripción de audio a texto."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from videodl import transcribe
from videodl.stores import transcriptions

# ---------------------------------------------------------------------------
# Página y capacidades
# ---------------------------------------------------------------------------


def test_transcribe_page_ok(client):
    res = client.get("/transcribir-audio")
    assert res.status_code == 200
    assert "Transcribir audio a texto" in res.text
    assert "transcribe.js" in res.text
    assert "SRT" in res.text and "VTT" in res.text


def test_transcribe_options(client):
    res = client.get("/api/transcribe/options")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {
        "available", "model", "max_seconds", "max_upload_mb", "language"
    }
    assert body["max_seconds"] >= 10
    assert body["max_upload_mb"] >= 1


def test_transcribe_endpoint_503_si_no_esta_instalado(client, monkeypatch):
    monkeypatch.setattr(transcribe, "TRANSCRIBE_AVAILABLE", False)
    res = client.post(
        "/api/transcribe",
        files={"file": ("audio.mp3", b"datos", "audio/mpeg")},
        data={"language": "es"},
    )
    assert res.status_code == 503
    assert "no está activada" in res.json()["detail"]


def test_transcribe_rejects_file_without_file(client):
    assert client.post("/api/transcribe", data={"language": "es"}).status_code == 422


def test_transcribe_unknown_job(client):
    assert client.get("/api/transcribe/nope").status_code == 404
    assert client.get("/api/transcribe/nope/file").status_code == 404
    assert client.post("/api/transcribe/nope/cancel").status_code == 404


# ---------------------------------------------------------------------------
# Validaciones y formatos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["", "auto", "AUTO", "automático", "es", "en", "pt-BR"])
def test_normalize_language_acepta_formatos(value, monkeypatch):
    monkeypatch.setattr(transcribe, "TRANSCRIBE_LANGUAGE", "")
    if value.lower() == "pt-br":
        with pytest.raises(HTTPException):
            transcribe.normalize_language(value)
        return
    assert transcribe.normalize_language(value) in (None, "es", "en")


def test_normalize_language_rechaza_codigos_raros():
    with pytest.raises(HTTPException) as excinfo:
        transcribe.normalize_language("español!")
    assert excinfo.value.status_code == 400


def test_normalize_language_usa_config_por_defecto(monkeypatch):
    monkeypatch.setattr(transcribe, "TRANSCRIBE_LANGUAGE", "es")
    assert transcribe.normalize_language("auto") == "es"
    assert transcribe.normalize_language("") == "es"


def test_format_timestamp_srt_y_vtt():
    assert transcribe.format_timestamp(0) == "00:00:00,000"
    assert transcribe.format_timestamp(65.5) == "00:01:05,500"
    assert transcribe.format_timestamp(3661.25) == "01:01:01,250"
    assert transcribe.format_timestamp(65.5, decimal=".") == "00:01:05.500"


SEGMENTS = [
    {"start": 0.0, "end": 2.5, "text": " Hola, esto es una prueba. "},
    {"start": 2.5, "end": 5.0, "text": "Segunda frase."},
    {"start": 5.0, "end": 6.0, "text": "   "},
]


def test_build_txt():
    assert transcribe.build_txt(SEGMENTS) == "Hola, esto es una prueba. Segunda frase.\n"


def test_build_srt():
    srt = transcribe.build_srt(SEGMENTS)
    assert srt.startswith("1\n00:00:00,000 --> 00:00:02,500\nHola, esto es una prueba.")
    assert "2\n00:00:02,500 --> 00:00:05,000\nSegunda frase." in srt
    assert "3\n" not in srt  # el segmento vacío se omite
    assert srt.endswith("\n")


def test_build_vtt():
    vtt = transcribe.build_vtt(SEGMENTS)
    assert vtt.startswith("WEBVTT\n\n")
    assert "00:00:00.000 --> 00:00:02.500" in vtt
    assert "Segunda frase." in vtt
    assert "00:00:05.000 --> 00:00:06.000" not in vtt


def test_build_srt_corrige_fin_invalido():
    srt = transcribe.build_srt([{"start": 1.0, "end": 1.0, "text": "Hola"}])
    assert "00:00:01,000 --> 00:00:01,500" in srt


# ---------------------------------------------------------------------------
# Trabajo completo (sin modelo real)
# ---------------------------------------------------------------------------


def test_run_transcribe_job_completa_el_trabajo(monkeypatch):
    tmpdir = Path(tempfile.mkdtemp(prefix="videodl_tr_test_"))
    src = tmpdir / "entrada.mp3"
    src.write_bytes(b"audio falso")

    monkeypatch.setattr(
        transcribe,
        "ffprobe_meta",
        lambda _path: {"has_audio": True, "duration": 6.0},
    )

    def fake_extract(_src, dest, _job_id, _duration):
        Path(dest).write_bytes(b"RIFF falso")

    monkeypatch.setattr(transcribe, "extract_audio", fake_extract)

    fake_segments = [
        SimpleNamespace(start=0.0, end=2.0, text=" Hola "),
        SimpleNamespace(start=2.0, end=4.0, text=" mundo "),
    ]
    monkeypatch.setattr(
        transcribe,
        "transcribe_audio",
        lambda _path, _language: (
            iter(fake_segments),
            SimpleNamespace(language="es", language_probability=0.98),
        ),
    )

    job_id = transcriptions.new(
        input_name="entrevista.mp3",
        input_size=11,
        output_size=0,
        message="Preparando…",
        percent=0.0,
        text=None,
        segments=[],
        segments_count=0,
        language=None,
        language_probability=None,
        duration=0,
        tmpdir=str(tmpdir),
    )

    try:
        transcribe._run_transcribe_job(job_id, src)
        job = transcriptions.get(job_id)
        assert job["status"] == "finished"
        assert job["percent"] == 100.0
        assert job["text"] == "Hola mundo"
        assert job["segments_count"] == 2
        assert job["language"] == "es"
        assert job["language_probability"] == 0.98
        assert job["duration"] == 6.0
        assert job["tmpdir"] is None
        assert not tmpdir.exists()
    finally:
        transcriptions.delete(job_id)
        if tmpdir.exists():
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)


def test_run_transcribe_job_sin_audio(monkeypatch):
    tmpdir = Path(tempfile.mkdtemp(prefix="videodl_tr_test_"))
    src = tmpdir / "entrada.mp3"
    src.write_bytes(b"datos")

    monkeypatch.setattr(
        transcribe,
        "ffprobe_meta",
        lambda _path: {"has_audio": False, "duration": 0.0},
    )

    job_id = transcriptions.new(
        input_name="video.mp4",
        input_size=5,
        output_size=0,
        message="Preparando…",
        percent=0.0,
        text=None,
        segments=[],
        segments_count=0,
        language=None,
        language_probability=None,
        duration=0,
        tmpdir=str(tmpdir),
    )

    try:
        transcribe._run_transcribe_job(job_id, src)
        job = transcriptions.get(job_id)
        assert job["status"] == "error"
        assert "pista de audio" in job["error"]
    finally:
        transcriptions.delete(job_id)
        if tmpdir.exists():
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Descargas
# ---------------------------------------------------------------------------


def _finished_job() -> str:
    job_id = transcriptions.new(
        input_name="entrevista.mp3",
        input_size=100,
        output_size=0,
        message="¡Listo!",
        percent=100.0,
        text="Hola mundo",
        segments=[
            {"start": 0.0, "end": 1.5, "text": "Hola"},
            {"start": 1.5, "end": 3.0, "text": "mundo"},
        ],
        segments_count=2,
        language="es",
        language_probability=0.99,
        duration=3.0,
        tmpdir=None,
    )
    transcriptions.update(job_id, status="finished")
    return job_id


def test_transcribe_download_txt_srt_vtt(client):
    job_id = _finished_job()
    try:
        txt = client.get(f"/api/transcribe/{job_id}/file?format=txt")
        assert txt.status_code == 200
        assert txt.text == "Hola mundo\n"
        assert "attachment" in txt.headers["content-disposition"]
        assert "entrevista.txt" in txt.headers["content-disposition"]

        srt = client.get(f"/api/transcribe/{job_id}/file?format=srt")
        assert srt.status_code == 200
        assert "00:00:00,000 --> 00:00:01,500" in srt.text

        vtt = client.get(f"/api/transcribe/{job_id}/file?format=vtt")
        assert vtt.status_code == 200
        assert vtt.text.startswith("WEBVTT")
        assert "00:00:01.500 --> 00:00:03.000" in vtt.text
    finally:
        transcriptions.delete(job_id)


def test_transcribe_download_rejects_bad_format(client):
    job_id = _finished_job()
    try:
        res = client.get(f"/api/transcribe/{job_id}/file?format=docx")
        assert res.status_code == 400
    finally:
        transcriptions.delete(job_id)


def test_transcribe_download_requires_finished(client):
    job_id = transcriptions.new(
        input_name="audio.mp3",
        input_size=10,
        status="transcribing",
        segments=[],
        tmpdir=None,
    )
    try:
        res = client.get(f"/api/transcribe/{job_id}/file")
        assert res.status_code == 409
    finally:
        transcriptions.delete(job_id)
