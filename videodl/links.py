"""Lógica del acortador de enlaces: validación de URLs y almacén SQLite.

No depende de FastAPI para poder probarse por sí sola. Las rutas HTTP viven en
``shortener.py``.

Un acortador abierto es un blanco habitual de phishing, así que la validación es
deliberadamente estricta: solo ``http``/``https`` con un dominio real (nada de
IPs, ``localhost`` ni nombres internos), sin usuario ni contraseña en la URL, sin
encadenar otros acortadores ni apuntar al propio sitio, y con una lista de
dominios bloqueados que se puede ampliar sin tocar el código.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
import sqlite3
import threading
import time
import unicodedata
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger("videodl.links")

# Sin caracteres que se confunden al leerlos (0/O, 1/l/I).
CODE_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6
CODE_RE = re.compile(r"^[A-Za-z0-9]{4,12}$")
MAX_URL_LENGTH = 2048

# Encadenar acortadores esconde el destino real: no se admiten.
KNOWN_SHORTENERS = frozenset(
    {
        "bit.ly", "tinyurl.com", "t.co", "goo.gl", "is.gd", "cutt.ly", "ow.ly",
        "rebrand.ly", "buff.ly", "shorturl.at", "t.ly", "rb.gy", "tiny.cc",
        "lnkd.in", "s.id", "v.gd", "bl.ink", "short.io",
    }
)

# Sufijos que nunca son un sitio público.
_INTERNAL_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".corp", ".intranet")

_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_EXPLICIT_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")
_HOST_PORT_RE = re.compile(r"^[^/?#]*:\d+(?:[/?#]|$)")
_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?$")


class LinkError(ValueError):
    """Entrada no válida; el mensaje se muestra tal cual a la persona usuaria."""


class LinkCapacityError(RuntimeError):
    """El almacén alcanzó su límite de enlaces."""


# El japonés mezcla legítimamente kanji, hiragana y katakana.
_JAPANESE_SCRIPTS = frozenset({"CJK", "HIRAGANA", "KATAKANA"})


def _mixes_scripts(text: str) -> bool:
    """Indica si las letras de ``text`` pertenecen a más de un alfabeto."""
    scripts = {
        unicodedata.name(ch, "?").split(" ")[0] for ch in text if ch.isalpha()
    }
    if scripts <= _JAPANESE_SCRIPTS:
        return False
    return len(scripts) > 1


def _matches_host(host: str, candidates: Iterable[str]) -> bool:
    """Coincide con el dominio o con cualquiera de sus subdominios."""
    return any(host == c or host.endswith("." + c) for c in candidates if c)


def parse_host_list(raw: str) -> frozenset[str]:
    """Convierte ``"a.com, B.org"`` en un conjunto de dominios en minúsculas."""
    hosts = set()
    for item in re.split(r"[\s,;]+", raw or ""):
        item = item.strip().lower().rstrip(".")
        if item.startswith("www."):
            item = item[4:]
        if item:
            hosts.add(item)
    return frozenset(hosts)


def host_is_blocked(url: str, blocked: Iterable[str]) -> bool:
    """Indica si el destino de ``url`` está en la lista de bloqueados."""
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return _matches_host(host, blocked)


def normalize_url(
    raw: str,
    *,
    own_hosts: Iterable[str] = (),
    blocked_hosts: Iterable[str] = (),
) -> str:
    """Valida y normaliza el enlace. Lanza ``LinkError`` con un motivo claro."""
    text = (raw or "").strip()
    if not text:
        raise LinkError("Escribe el enlace que quieres acortar.")
    if len(text) > MAX_URL_LENGTH:
        raise LinkError(f"El enlace es demasiado largo (máximo {MAX_URL_LENGTH} caracteres).")
    if any(ord(ch) <= 32 or ord(ch) == 127 for ch in text):
        raise LinkError("El enlace no puede tener espacios ni saltos de línea.")

    # Sin esquema («ejemplo.com/ruta») se asume https. Cualquier otro esquema
    # (javascript:, data:, mailto:, ftp:…) se rechaza más abajo.
    if not _EXPLICIT_SCHEME_RE.match(text):
        if _SCHEME_RE.match(text) and not _HOST_PORT_RE.match(text):
            raise LinkError("Solo se pueden acortar enlaces http o https.")
        text = "https://" + text.lstrip("/")

    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError as exc:
        raise LinkError("El enlace no es válido.") from exc

    if parts.scheme.lower() not in ("http", "https"):
        raise LinkError("Solo se pueden acortar enlaces http o https.")
    if parts.username is not None or parts.password is not None:
        raise LinkError("El enlace no puede incluir usuario ni contraseña.")

    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise LinkError("El enlace no tiene un dominio válido.")

    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise LinkError("El dominio del enlace no es válido.") from exc

    labels = host.split(".")
    if (
        len(host) > 253
        or len(labels) < 2
        or not all(_LABEL_RE.match(label) for label in labels)
    ):
        raise LinkError("Usa un dominio completo, por ejemplo ejemplo.com (no una dirección IP).")
    # Homógrafos: «аpple.com» con una «а» cirílica se ve igual que «apple.com».
    # Se rechazan las etiquetas que mezclan alfabetos distintos (latino con
    # cirílico o griego, por ejemplo). Las letras con acento (ñ, ü, é) siguen
    # siendo latinas y se aceptan.
    for label in labels:
        if label.startswith("xn--"):
            try:
                shown = label.encode("ascii").decode("idna")
            except UnicodeError:
                raise LinkError("El dominio del enlace no es válido.") from None
            if _mixes_scripts(shown):
                raise LinkError("El dominio mezcla alfabetos distintos y no se puede acortar.")
    tld = labels[-1]
    if not (tld.isalpha() or tld.startswith("xn--")) or len(tld) < 2:
        raise LinkError("Usa un dominio completo, por ejemplo ejemplo.com (no una dirección IP).")
    if host.endswith(_INTERNAL_SUFFIXES):
        raise LinkError("Ese enlace apunta a una red interna, no a un sitio público.")

    bare = host[4:] if host.startswith("www.") else host
    own = {h.lower().removeprefix("www.") for h in own_hosts if h}
    if _matches_host(bare, own):
        raise LinkError("No se pueden acortar enlaces de este mismo sitio.")
    if _matches_host(bare, KNOWN_SHORTENERS):
        raise LinkError("Ese enlace ya está acortado. Pega el enlace original.")
    if _matches_host(bare, blocked_hosts):
        raise LinkError("Ese sitio no está permitido en el acortador.")

    netloc = host
    default_port = 443 if parts.scheme.lower() == "https" else 80
    if port and port != default_port:
        netloc = f"{host}:{port}"

    url = urlunsplit((parts.scheme.lower(), netloc, parts.path, parts.query, parts.fragment))
    if len(url) > MAX_URL_LENGTH:
        raise LinkError(f"El enlace es demasiado largo (máximo {MAX_URL_LENGTH} caracteres).")
    return url


def is_valid_code(code: str) -> bool:
    return bool(CODE_RE.match(code or ""))


def _new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


_SCHEMA = """
CREATE TABLE IF NOT EXISTS links (
    code      TEXT PRIMARY KEY,
    url       TEXT NOT NULL,
    url_hash  TEXT NOT NULL,
    created   INTEGER NOT NULL,
    last_used INTEGER,
    clicks    INTEGER NOT NULL DEFAULT 0,
    disabled  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_links_hash ON links(url_hash);
CREATE TABLE IF NOT EXISTS reports (
    code     TEXT NOT NULL,
    reporter TEXT NOT NULL,
    created  INTEGER NOT NULL,
    PRIMARY KEY (code, reporter)
);
"""


class LinkStore:
    """Almacén SQLite de enlaces cortos (una conexión por operación)."""

    def __init__(self, path: Path | str, *, max_links: int = 100_000, salt: bytes | None = None):
        self.path = Path(path)
        self.max_links = max_links
        # La sal evita guardar IPs reales: solo un hash para no contar dos veces
        # al mismo informante. Si no se configura, cambia en cada arranque.
        self._salt = salt or secrets.token_bytes(16)
        self._init_lock = threading.Lock()
        self._ready = False

    # -- infraestructura ----------------------------------------------------

    @contextmanager
    def _conn(self):
        self._ensure_ready()
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # confirma o revierte la transacción
                yield conn
        finally:
            conn.close()

    def _ensure_ready(self) -> None:
        if self._ready:
            return
        with self._init_lock:
            if self._ready:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.path), timeout=10)
            try:
                try:
                    conn.execute("PRAGMA journal_mode=WAL")
                except sqlite3.DatabaseError:  # p. ej. sistema de archivos sin WAL
                    logger.warning("SQLite sin modo WAL en %s", self.path)
                conn.executescript(_SCHEMA)
                conn.commit()
            finally:
                conn.close()
            self._ready = True

    def available(self) -> bool:
        """Comprueba que la base de datos se puede abrir y escribir."""
        try:
            with self._conn() as conn:
                conn.execute("SELECT 1 FROM links LIMIT 1")
            return True
        except (sqlite3.Error, OSError):
            logger.exception("El almacén de enlaces no está disponible")
            return False

    def reporter_key(self, identity: str) -> str:
        return hashlib.sha256(self._salt + identity.encode("utf-8")).hexdigest()[:32]

    # -- operaciones ---------------------------------------------------------

    def count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]

    def create(self, url: str) -> tuple[str, bool]:
        """Devuelve ``(código, es_nuevo)``. Reutiliza el código si la URL ya existe."""
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        now = int(time.time())
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT code, disabled FROM links WHERE url_hash = ? AND url = ?",
                (url_hash, url),
            ).fetchall()
            if any(row["disabled"] for row in rows):
                raise LinkError("Ese enlace fue bloqueado tras varios reportes.")
            if rows:
                return rows[0]["code"], False

            if conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] >= self.max_links:
                raise LinkCapacityError("Se alcanzó el límite de enlaces.")

            for _ in range(8):
                code = _new_code()
                try:
                    conn.execute(
                        "INSERT INTO links (code, url, url_hash, created) VALUES (?, ?, ?, ?)",
                        (code, url, url_hash, now),
                    )
                    return code, True
                except sqlite3.IntegrityError:
                    continue
        raise RuntimeError("No se pudo generar un código único.")

    def get(self, code: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT code, url, created, clicks, disabled FROM links WHERE code = ?",
                (code,),
            ).fetchone()
        return dict(row) if row else None

    def resolve(self, code: str) -> dict | None:
        """Devuelve el enlace y cuenta la visita. ``None`` si no existe."""
        now = int(time.time())
        with self._conn() as conn:
            row = conn.execute(
                "SELECT code, url, disabled FROM links WHERE code = ?", (code,)
            ).fetchone()
            if row is None:
                return None
            if not row["disabled"]:
                conn.execute(
                    "UPDATE links SET clicks = clicks + 1, last_used = ? WHERE code = ?",
                    (now, code),
                )
        return dict(row)

    def report(self, code: str, identity: str, threshold: int) -> str:
        """Registra un reporte. Devuelve ``unknown``, ``reported`` o ``disabled``."""
        now = int(time.time())
        reporter = self.reporter_key(identity)
        with self._conn() as conn:
            row = conn.execute("SELECT disabled FROM links WHERE code = ?", (code,)).fetchone()
            if row is None:
                return "unknown"
            if row["disabled"]:
                return "disabled"
            conn.execute(
                "INSERT OR IGNORE INTO reports (code, reporter, created) VALUES (?, ?, ?)",
                (code, reporter, now),
            )
            total = conn.execute(
                "SELECT COUNT(*) FROM reports WHERE code = ?", (code,)
            ).fetchone()[0]
            if threshold > 0 and total >= threshold:
                conn.execute("UPDATE links SET disabled = 1 WHERE code = ?", (code,))
                return "disabled"
        return "reported"

    def purge_stale(self, days: int) -> int:
        """Borra enlaces sin uso en ``days`` días. Los bloqueados se conservan."""
        if days <= 0:
            return 0
        cutoff = int(time.time()) - days * 86400
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM links WHERE disabled = 0 AND COALESCE(last_used, created) < ?",
                (cutoff,),
            )
            conn.execute("DELETE FROM reports WHERE code NOT IN (SELECT code FROM links)")
            return cur.rowcount
