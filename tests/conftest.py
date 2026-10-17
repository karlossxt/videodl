"""Configuración común de los tests.

Se añade la raíz del proyecto al ``sys.path`` para poder importar ``videodl`` y
se desactiva el rate limiting para que las pruebas no dependan de él.

La variable de entorno se fija **antes** de importar la app: la configuración se
resuelve al importar el módulo, así que el orden importa.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "0")


@pytest.fixture()
def client():
    """Cliente de pruebas sobre la app FastAPI.

    La importación se hace aquí dentro (y no a nivel de módulo) para que la
    variable de entorno de arriba ya esté fijada cuando se importe la app.
    """
    from fastapi.testclient import TestClient

    from main import app

    return TestClient(app)
