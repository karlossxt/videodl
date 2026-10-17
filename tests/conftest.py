"""Configuración común de los tests.

Se añade la raíz del proyecto al ``sys.path`` para poder importar ``videodl`` y
se desactiva el rate limiting para que las pruebas no dependan de él.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "0")
