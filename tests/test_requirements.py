"""Pruebas de las dependencias declaradas.

La importante aquí es la de yt-dlp: desde 2025 yt-dlp necesita un runtime de
JavaScript para YouTube, y se instala con los extras ``default`` (solucionador
``yt-dlp-ejs``) y ``deno`` (runtime). Si alguien vuelve a pedirlo "pelado",
YouTube falla desde el servidor con el aviso anti-bot y la degradación no se ve
hasta que se despliega.
"""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _lineas_de(paquete: str) -> list[str]:
    texto = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
    return [
        linea.strip()
        for linea in texto.splitlines()
        if linea.strip() and not linea.strip().startswith("#") and linea.split("[")[0].split(">")[0].split("=")[0].strip().lower() == paquete
    ]


def test_yt_dlp_se_instala_con_runtime_javascript():
    """yt-dlp debe traer el runtime JS: sin él YouTube no funciona en el servidor."""
    lineas = _lineas_de("yt-dlp")

    assert len(lineas) == 1, f"requirements.txt debe pedir yt-dlp una sola vez: {lineas}"
    declaracion = lineas[0]
    assert "[" in declaracion, (
        "yt-dlp debe instalarse con extras ([default,deno]); sin runtime de "
        f"JavaScript YouTube responde con «Sign in to confirm you're not a bot»: {declaracion!r}"
    )
    extras = declaracion[declaracion.index("[") + 1 : declaracion.index("]")]
    nombres = {extra.strip().lower() for extra in extras.split(",")}
    assert {"default", "deno"} <= nombres, (
        f"yt-dlp necesita los extras default y deno, no {sorted(nombres)}"
    )


def test_dependencias_principales_presentes():
    """Un repaso rápido: los paquetes que la app importa deben estar declarados."""
    for paquete in ("fastapi", "uvicorn", "python-multipart", "segno"):
        assert _lineas_de(paquete), f"falta {paquete} en requirements.txt"
