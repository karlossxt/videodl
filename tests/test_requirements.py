"""Pruebas de las dependencias declaradas y de la imagen de producción.

FasTools ya no descarga vídeos de plataformas externas, así que las dependencias
de descarga (yt-dlp, el proveedor de PO tokens y el runtime Deno) no deben volver
a colarse: encarecen la imagen y reintroducen una superficie legal y de red que
el proyecto ha retirado a propósito.
"""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _lineas_de(paquete: str) -> list[str]:
    texto = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
    return [
        linea.strip()
        for linea in texto.splitlines()
        if linea.strip()
        and not linea.strip().startswith("#")
        and linea.split("[")[0].split(">")[0].split("=")[0].strip().lower() == paquete
    ]


def test_dependencias_principales_presentes():
    for paquete in ("fastapi", "uvicorn", "python-multipart", "segno"):
        assert _lineas_de(paquete), f"falta {paquete} en requirements.txt"


def test_no_quedan_dependencias_de_descarga():
    for paquete in ("yt-dlp", "bgutil-ytdlp-pot-provider", "curl-cffi", "deno"):
        assert not _lineas_de(paquete), f"{paquete} ya no debe estar en requirements.txt"


def test_dockerfile_no_instala_utilidades_de_descarga():
    dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8").lower()
    for rastro in ("yt-dlp", "bgutil", "deno", "pot-provider", "/etc/secrets"):
        assert rastro not in dockerfile, f"el Dockerfile todavía menciona {rastro!r}"


def test_dev_dependencies_incluyen_pytest_httpx_y_ruff():
    dev = (RAIZ / "requirements-dev.txt").read_text(encoding="utf-8")
    for paquete in ("pytest", "httpx", "ruff"):
        assert paquete in dev


def test_transcripcion_es_una_dependencia_opcional():
    """faster-whisper no debe engordar la imagen por defecto."""
    assert not _lineas_de("faster-whisper")
    opcional = (RAIZ / "requirements-transcribe.txt").read_text(encoding="utf-8")
    assert "faster-whisper" in opcional
    dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    assert "INSTALL_TRANSCRIBE" in dockerfile
