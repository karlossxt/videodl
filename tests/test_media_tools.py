"""Pruebas de vídeo a GIF, extraer audio y unir o cortar audio."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

from videodl import media_tools as mt
from videodl import stores

needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="ffmpeg/ffprobe no están instalados",
)


# ---------------------------------------------------------------------------
# Validación y comandos (no necesitan ffmpeg)
# ---------------------------------------------------------------------------


def test_gif_validate_acepta_valores_correctos():
    mt.gif_validate(0, 5, 480, 12)


@pytest.mark.parametrize(
    "start,end,width,fps",
    [
        (0, 5, 999, 12),    # ancho desconocido
        (0, 5, 480, 99),    # fps desconocido
        (-1, 5, 480, 12),   # inicio negativo
        (5, 5, 480, 12),    # final igual al inicio
        (6, 5, 480, 12),    # final antes del inicio
        (0, 0.2, 480, 12),  # demasiado corto
    ],
)
def test_gif_validate_rechaza_entradas_invalidas(start, end, width, fps):
    with pytest.raises(HTTPException) as exc:
        mt.gif_validate(start, end, width, fps)
    assert exc.value.status_code == 400


def test_gif_validate_respeta_el_maximo(monkeypatch):
    monkeypatch.setattr(mt, "GIF_MAX_SECONDS", 10)
    mt.gif_validate(0, 10, 480, 12)
    with pytest.raises(HTTPException) as exc:
        mt.gif_validate(0, 10.5, 480, 12)
    assert exc.value.status_code == 400
    assert "10" in exc.value.detail


def test_gif_args_usa_paleta_y_recorta():
    args = mt.gif_args(Path("in.mp4"), Path("out.gif"), 2.0, 3.0, 480, 12)
    joined = " ".join(map(str, args))
    assert "palettegen" in joined and "paletteuse" in joined
    assert "fps=12" in joined and "min(480,iw)" in joined
    assert args[args.index("-ss") + 1] == "2.000"
    assert args[args.index("-t") + 1] == "3.000"
    assert "-an" in args  # un GIF no lleva audio


def test_gif_args_sin_inicio_no_pasa_ss():
    args = mt.gif_args(Path("in.mp4"), Path("out.gif"), 0.0, 3.0, 320, 8)
    assert "-ss" not in args


def test_edit_filter_normaliza_y_concatena_en_orden():
    f = mt.edit_filter(3)
    assert f.count("aresample=44100") == 3
    assert "[a0][a1][a2]concat=n=3:v=0:a=1[out]" in f


@pytest.mark.parametrize("fmt,bitrate", [("ogg", 192), ("mp3", 64)])
def test_audio_formato_o_calidad_invalidos(fmt, bitrate):
    with pytest.raises(HTTPException):
        mt._audio_validate_format(fmt, bitrate)


def test_audio_codec_args_por_formato():
    assert "libmp3lame" in mt._audio_codec_args("mp3", 192)
    assert "aac" in mt._audio_codec_args("m4a", 192)
    wav = mt._audio_codec_args("wav", 192)
    assert "pcm_s16le" in wav and "-b:a" not in wav


# ---------------------------------------------------------------------------
# Trabajos reales con ffmpeg
# ---------------------------------------------------------------------------


def _ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    _ff("-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=440", "-t", "6",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(d / "v.mp4"))
    _ff("-f", "lavfi", "-i", "sine=frequency=880", "-t", "4", str(d / "a.wav"))
    _ff("-f", "lavfi", "-i", "testsrc=size=160x120:rate=10", "-t", "1",
        "-pix_fmt", "yuv420p", str(d / "mudo.mp4"))
    return d


def _work(media: Path, *names: str) -> tuple[Path, list[Path]]:
    work = Path(tempfile.mkdtemp(prefix="t_media_"))
    paths = []
    for name in names:
        shutil.copy(media / name, work / name)
        paths.append(work / name)
    return work, paths


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(out.strip())


@needs_ffmpeg
def test_gif_se_crea_con_la_duracion_pedida(media):
    work, (src,) = _work(media, "v.mp4")
    job = stores.gifs.new(percent=0.0, tmpdir=str(work), path=None)
    mt._run_gif_job(job, src, "mi video", 1.0, 4.0, 320, 10)
    data = stores.gifs.get(job)
    assert data["status"] == "finished", data.get("error")
    assert data["filename"].endswith(".gif")
    out = Path(data["path"])
    assert out.read_bytes()[:6] in (b"GIF87a", b"GIF89a")
    assert _duration(out) == pytest.approx(3.0, abs=0.4)
    stores.gifs.delete(job)


@needs_ffmpeg
def test_gif_de_un_audio_falla_con_mensaje_claro(media):
    work, (src,) = _work(media, "a.wav")
    job = stores.gifs.new(percent=0.0, tmpdir=str(work), path=None)
    mt._run_gif_job(job, src, "x", 0.0, 2.0, 480, 12)
    data = stores.gifs.get(job)
    assert data["status"] == "error"
    assert "vídeo" in data["error"]
    assert not work.exists()  # la carpeta temporal se limpia


@needs_ffmpeg
def test_gif_cancelado_limpia_la_carpeta(media):
    work, (src,) = _work(media, "v.mp4")
    job = stores.gifs.new(percent=0.0, tmpdir=str(work), path=None, cancel=True)
    mt._run_gif_job(job, src, "x", 0.0, 3.0, 480, 12)
    assert stores.gifs.get(job)["status"] == "cancelled"
    assert not work.exists()


@needs_ffmpeg
@pytest.mark.parametrize("fmt", ["mp3", "m4a", "wav"])
def test_extraer_audio_en_cada_formato(media, fmt):
    work, (src,) = _work(media, "v.mp4")
    job = stores.audios.new(percent=0.0, tmpdir=str(work), path=None)
    mt._run_extract_job(job, src, "peli", fmt, 192)
    data = stores.audios.get(job)
    assert data["status"] == "finished", data.get("error")
    assert data["filename"] == f"peli.{fmt}"
    assert _duration(Path(data["path"])) == pytest.approx(6.0, abs=0.5)
    stores.audios.delete(job)


@needs_ffmpeg
def test_extraer_audio_de_un_video_sin_sonido(media):
    work, (src,) = _work(media, "mudo.mp4")
    job = stores.audios.new(percent=0.0, tmpdir=str(work), path=None)
    mt._run_extract_job(job, src, "mudo", "mp3", 192)
    data = stores.audios.get(job)
    assert data["status"] == "error"
    assert "audio" in data["error"]


@needs_ffmpeg
def test_unir_dos_audios_suma_las_duraciones(media):
    work, srcs = _work(media, "v.mp4", "a.wav")
    job = stores.audios.new(percent=0.0, tmpdir=str(work), path=None)
    mt._run_edit_job(job, srcs, ["v", "a"], 0.0, 0.0, "mp3", 192)
    data = stores.audios.get(job)
    assert data["status"] == "finished", data.get("error")
    assert data["filename"] == "audio-unido.mp3"
    assert _duration(Path(data["path"])) == pytest.approx(10.0, abs=0.6)
    stores.audios.delete(job)


@needs_ffmpeg
def test_cortar_un_audio_respeta_inicio_y_final(media):
    work, srcs = _work(media, "v.mp4")
    job = stores.audios.new(percent=0.0, tmpdir=str(work), path=None)
    mt._run_edit_job(job, srcs, ["mi cancion"], 1.0, 3.5, "m4a", 128)
    data = stores.audios.get(job)
    assert data["status"] == "finished", data.get("error")
    assert data["filename"] == "mi cancion recortado.m4a"
    assert _duration(Path(data["path"])) == pytest.approx(2.5, abs=0.4)
    stores.audios.delete(job)


@needs_ffmpeg
def test_cortar_con_inicio_fuera_de_rango_falla(media):
    work, srcs = _work(media, "a.wav")
    job = stores.audios.new(percent=0.0, tmpdir=str(work), path=None)
    mt._run_edit_job(job, srcs, ["a"], 99.0, 0.0, "mp3", 192)
    data = stores.audios.get(job)
    assert data["status"] == "error"
    assert "supera" in data["error"]


# ---------------------------------------------------------------------------
# Rutas HTTP
# ---------------------------------------------------------------------------


def test_las_opciones_de_la_api_se_publican(client):
    gif = client.get("/api/gif/options").json()
    assert gif["widths"] == [320, 480, 640] and gif["max_seconds"] >= 1
    audio = client.get("/api/audio/options").json()
    assert audio["formats"] == ["mp3", "m4a", "wav"] and audio["max_files"] >= 2


@pytest.mark.parametrize(
    "path", ["/video-a-gif", "/extraer-audio", "/unir-audio",
             "/en/video-a-gif", "/en/extraer-audio", "/en/unir-audio"],
)
def test_las_paginas_nuevas_cargan(client, path):
    res = client.get(path)
    assert res.status_code == 200
    assert "<h1" in res.text


def test_la_pagina_inglesa_esta_traducida(client):
    html = client.get("/en/video-a-gif").text
    assert "Convert a video to an animated GIF" in html
    assert "Convertir un vídeo a GIF animado" not in html


def test_el_catalogo_ya_no_marca_estas_herramientas_como_proximamente():
    from videodl.catalog import tool_by_slug

    for slug in ("video-a-gif", "extraer-audio", "unir-audio"):
        tool = tool_by_slug(slug)
        assert tool.status == "available" and tool.route == f"/{slug}"


def test_gif_rechaza_un_rango_invalido_antes_de_subir(client):
    res = client.post(
        "/api/gif/upload",
        files={"file": ("v.mp4", b"x", "video/mp4")},
        data={"start": "5", "end": "2", "width": "480", "fps": "12"},
    )
    assert res.status_code in (400, 503)


def test_unir_exige_dos_archivos_o_un_recorte(client):
    res = client.post(
        "/api/audio/edit",
        files=[("files", ("a.mp3", b"x", "audio/mpeg"))],
        data={"start": "0", "end": "0", "format": "mp3", "bitrate": "192"},
    )
    assert res.status_code in (400, 503)


def test_unir_rechaza_formatos_que_no_son_audio(client):
    res = client.post(
        "/api/audio/edit",
        files=[
            ("files", ("a.txt", b"x", "text/plain")),
            ("files", ("b.mp3", b"x", "audio/mpeg")),
        ],
        data={"format": "mp3", "bitrate": "192"},
    )
    assert res.status_code in (400, 503)


def test_trabajos_inexistentes_devuelven_404(client):
    assert client.get("/api/gif/no-existe").status_code == 404
    assert client.get("/api/audio/no-existe/file").status_code == 404
    assert client.post("/api/gif/no-existe/cancel").status_code == 404


@needs_ffmpeg
def test_flujo_completo_por_la_api(client, media):
    """Sube dos audios, espera al trabajo y descarga el resultado una sola vez."""
    res = client.post(
        "/api/audio/edit",
        files=[
            ("files", ("v.mp4", (media / "v.mp4").read_bytes(), "video/mp4")),
            ("files", ("a.wav", (media / "a.wav").read_bytes(), "audio/wav")),
        ],
        data={"format": "mp3", "bitrate": "128"},
    )
    assert res.status_code == 200, res.text
    job_id = res.json()["id"]

    for _ in range(100):
        status = client.get(f"/api/audio/{job_id}").json()
        if status["status"] in ("finished", "error"):
            break
        time.sleep(0.2)
    assert status["status"] == "finished", status

    file = client.get(f"/api/audio/{job_id}/file")
    assert file.status_code == 200
    assert file.headers["content-type"].startswith("audio/mpeg")
    # Tras la descarga el trabajo se borra.
    assert client.get(f"/api/audio/{job_id}").status_code == 404
