"""Pruebas de extremo a extremo con ffmpeg real.

Cubren el pipeline completo del compresor y del recortador de clips: se genera un
vídeo de prueba con el propio ffmpeg, se sube por la API y se comprueba que el
trabajo termina, que el archivo resultante es un MP4 válido y que se respetan las
dimensiones y el tamaño objetivo. No hacen falta recursos externos ni red.

Si ffmpeg/ffprobe no están instalados las pruebas se saltan (por ejemplo en un
equipo de desarrollo sin ffmpeg); el CI sí los instala antes de ejecutarlas.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from videodl.config import FFMPEG, FFMPEG_AVAILABLE, FFPROBE_AVAILABLE
from videodl.media import ffprobe_meta

pytestmark = pytest.mark.skipif(
    not (FFMPEG_AVAILABLE and FFPROBE_AVAILABLE),
    reason="ffmpeg/ffprobe no están instalados",
)

TERMINAL_STATUSES = {"finished", "error", "cancelled"}
JOB_TIMEOUT_SECONDS = 180


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory) -> Path:
    """Genera un MP4 de prueba (~3 s, 480x270, con audio y bitrate alto).

    El bitrate es alto a propósito: así el archivo supera 1 MB y el compresor
    tiene que recodificar de verdad (no le basta con remultiplexar).
    """
    path = tmp_path_factory.mktemp("media") / "prueba.mp4"
    args = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=size=480x270:rate=15:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        # CBR real: sin minrate/maxrate, x264 infravalora el bitrate en contenido
        # sintético y el archivo no llegaría a 1 MB.
        "-b:v", "4M", "-minrate", "4M", "-maxrate", "4M", "-bufsize", "1M",
        "-x264-params", "nal-hrd=cbr",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-movflags", "+faststart",
        str(path),
    ]
    subprocess.run(args, check=True, capture_output=True)
    assert path.exists() and path.stat().st_size > 1024 * 1024, "el vídeo de prueba es demasiado pequeño"
    return path


def wait_for_job(client, base: str, job_id: str) -> dict:
    """Espera a que el trabajo termine y devuelve su estado final."""
    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    job: dict = {}
    while time.monotonic() < deadline:
        res = client.get(f"{base}/{job_id}")
        assert res.status_code == 200, res.text
        job = res.json()
        if job.get("status") in TERMINAL_STATUSES:
            return job
        time.sleep(0.2)
    pytest.fail(f"El trabajo {job_id} no terminó en {JOB_TIMEOUT_SECONDS}s: {job}")


def test_compress_end_to_end(client, sample_video):
    """Un vídeo de más de 1 MB con objetivo 1 MB se recodifica y cabe."""
    with sample_video.open("rb") as fh:
        res = client.post(
            "/api/compress",
            files={"file": ("prueba.mp4", fh, "video/mp4")},
            data={"target_mb": "1", "max_height": "480", "quality_mode": "size"},
        )
    assert res.status_code == 200, res.text
    job_id = res.json()["id"]

    job = wait_for_job(client, "/api/compress", job_id)
    assert job["status"] == "finished", job
    assert job["output_size"] > 0
    assert job["output_size"] <= 1024 * 1024, job["output_size"]
    assert job["output_size"] < sample_video.stat().st_size
    assert job["filename"].endswith(".mp4")

    file_res = client.get(f"/api/compress/{job_id}/file")
    assert file_res.status_code == 200
    assert file_res.headers["content-type"] == "video/mp4"
    assert len(file_res.content) > 0
    # El trabajo se libera en cuanto se entrega el archivo.
    assert client.get(f"/api/compress/{job_id}").status_code == 404


def test_compress_quality_mode(client, sample_video):
    """El modo "priorizar calidad" recodifica y termina correctamente."""
    with sample_video.open("rb") as fh:
        res = client.post(
            "/api/compress",
            files={"file": ("prueba.mp4", fh, "video/mp4")},
            data={"target_mb": "1", "max_height": "360", "quality_mode": "quality"},
        )
    assert res.status_code == 200, res.text
    job = wait_for_job(client, "/api/compress", res.json()["id"])
    assert job["status"] == "finished", job
    assert job["output_size"] > 0


def test_clip_upload_vertical_end_to_end(client, sample_video):
    """Un archivo subido se recorta y se reencuadra en vertical 9:16."""
    with sample_video.open("rb") as fh:
        res = client.post(
            "/api/clips/upload",
            files={"file": ("prueba.mp4", fh, "video/mp4")},
            data={
                "start": "0",
                "end": "1",
                "aspect": "vertical",
                "quality": "baja",
                "duration": "3",
            },
        )
    assert res.status_code == 200, res.text
    job_id = res.json()["id"]

    job = wait_for_job(client, "/api/clips", job_id)
    assert job["status"] == "finished", job
    assert (job["width"], job["height"]) == (480, 854), job
    assert job["output_size"] > 0
    assert job["filename"].endswith(".mp4")

    file_res = client.get(f"/api/clips/{job_id}/file")
    assert file_res.status_code == 200
    assert file_res.headers["content-type"] == "video/mp4"
    assert len(file_res.content) > 0
    assert client.get(f"/api/clips/{job_id}").status_code == 404


def test_clip_upload_square_end_to_end(client, sample_video):
    """El formato cuadrado 1:1 produce un vídeo cuadrado."""
    with sample_video.open("rb") as fh:
        res = client.post(
            "/api/clips/upload",
            files={"file": ("prueba.mp4", fh, "video/mp4")},
            data={
                "start": "0.5",
                "end": "1.5",
                "aspect": "square",
                "quality": "media",
                "duration": "3",
            },
        )
    assert res.status_code == 200, res.text
    job = wait_for_job(client, "/api/clips", res.json()["id"])
    assert job["status"] == "finished", job
    assert job["width"] == job["height"] == 720, job
    assert job["output_size"] > 0


@pytest.fixture(scope="session")
def portrait_video(tmp_path_factory) -> Path:
    """Vídeo vertical 480x854: el compresor no debe deformarlo ni achicarlo."""
    path = tmp_path_factory.mktemp("media") / "vertical.mp4"
    args = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=480x854:rate=15:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-c:v", "libx264", "-preset", "ultrafast", "-b:v", "4M",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        str(path),
    ]
    subprocess.run(args, check=True)
    return path


@pytest.fixture(scope="session")
def webm_video(tmp_path_factory) -> Path:
    """VP9/Opus que cabe en el tamaño pedido pero no se reproduce en WhatsApp."""
    path = tmp_path_factory.mktemp("media") / "vertical.webm"
    args = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=480x270:rate=15:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8",
        "-b:v", "2M", "-pix_fmt", "yuv420p", "-c:a", "libopus",
        str(path),
    ]
    subprocess.run(args, check=True)
    return path


@pytest.fixture(scope="session")
def long_video(tmp_path_factory) -> Path:
    """120 s a 320x180: no hay bitrate que lo deje en 1 MB con calidad usable."""
    path = tmp_path_factory.mktemp("media") / "largo.mp4"
    args = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15:duration=120",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=120",
        "-c:v", "libx264", "-preset", "ultrafast", "-b:v", "300k",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
        str(path),
    ]
    subprocess.run(args, check=True)
    return path


def _download_compress_output(client, job_id: str, tmp_path: Path) -> Path:
    res = client.get(f"/api/compress/{job_id}/file")
    assert res.status_code == 200, res.text
    out = tmp_path / "salida.mp4"
    out.write_bytes(res.content)
    return out


def test_compress_portrait_uses_short_side(client, portrait_video, tmp_path):
    """Un vertical 480x854 con tope 360 debe quedar en 360x640, no en 270x480."""
    with portrait_video.open("rb") as fh:
        res = client.post(
            "/api/compress",
            files={"file": ("vertical.mp4", fh, "video/mp4")},
            data={"target_mb": "1", "max_height": "360", "quality_mode": "size"},
        )
    assert res.status_code == 200, res.text
    job_id = res.json()["id"]
    job = wait_for_job(client, "/api/compress", job_id)
    assert job["status"] == "finished", job
    assert job["output_size"] <= 1024 * 1024, job["output_size"]

    out = _download_compress_output(client, job_id, tmp_path)
    meta = ffprobe_meta(out)
    assert meta["height"] > meta["width"], meta
    assert meta["width"] == 360, meta


def test_compress_webm_reencodes_to_h264(client, webm_video, tmp_path):
    """Aunque el WebM quepa, el MP4 final debe ser H.264 (compatible con móviles)."""
    with webm_video.open("rb") as fh:
        res = client.post(
            "/api/compress",
            files={"file": ("vertical.webm", fh, "video/webm")},
            data={"target_mb": "2", "max_height": "0", "quality_mode": "size"},
        )
    assert res.status_code == 200, res.text
    job_id = res.json()["id"]
    job = wait_for_job(client, "/api/compress", job_id)
    assert job["status"] == "finished", job

    out = _download_compress_output(client, job_id, tmp_path)
    meta = ffprobe_meta(out)
    assert meta["vcodec"] == "h264", meta
    assert meta["acodec"] in ("", "aac"), meta


def test_compress_target_impossible_fails_clearly(client, long_video):
    """Si el tamaño no se puede cumplir, se avisa en vez de devolver algo más grande."""
    with long_video.open("rb") as fh:
        res = client.post(
            "/api/compress",
            files={"file": ("largo.mp4", fh, "video/mp4")},
            data={"target_mb": "1", "max_height": "0", "quality_mode": "size"},
        )
    assert res.status_code == 200, res.text
    job = wait_for_job(client, "/api/compress", res.json()["id"])
    assert job["status"] == "error", job
    assert "No se puede dejar en 1 MB" in (job["error"] or ""), job
