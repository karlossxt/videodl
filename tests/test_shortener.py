"""Pruebas del acortador de enlaces: validación, almacén SQLite y rutas HTTP."""

from __future__ import annotations

import time

import pytest

from videodl.links import (
    LinkCapacityError,
    LinkError,
    LinkStore,
    host_is_blocked,
    is_valid_code,
    normalize_url,
    parse_host_list,
)

# ---------------------------------------------------------------------------
# Validación de URLs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://ejemplo.com/ruta?a=1#x", "https://ejemplo.com/ruta?a=1#x"),
        ("ejemplo.com/ruta", "https://ejemplo.com/ruta"),             # sin esquema
        ("  https://Ejemplo.COM/Ruta  ", "https://ejemplo.com/Ruta"),  # host en minúsculas
        ("https://ejemplo.com:443/x", "https://ejemplo.com/x"),       # puerto por defecto
        ("http://ejemplo.com:80/x", "http://ejemplo.com/x"),
        ("https://ejemplo.com:8443/x", "https://ejemplo.com:8443/x"),  # otro puerto se conserva
        ("https://bücher.de/libro", "https://xn--bcher-kva.de/libro"),  # acentos latinos válidos
    ],
)
def test_urls_validas_se_normalizan(raw, expected):
    assert normalize_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "ftp://ejemplo.com/archivo",
        "mailto:alguien@ejemplo.com",
        "file:///etc/passwd",
        "https://usuario:clave@ejemplo.com/",          # credenciales en la URL
        "https://ejemplo.com/con espacios",
        "https://ejemplo.com/\nsalto",
        "http://192.168.1.1/admin",                    # IP privada
        "http://8.8.8.8/",                             # cualquier IP
        "http://[::1]/",
        "http://localhost/",
        "localhost:8000/x",
        "http://intranet/",                            # nombre de una sola etiqueta
        "http://router.local/",
        "http://servidor.internal/",
        "https://" + "a" * 2100 + ".com",
    ],
)
def test_urls_peligrosas_o_invalidas_se_rechazan(raw):
    with pytest.raises(LinkError):
        normalize_url(raw)


def test_homografo_cirilico_se_rechaza():
    # La primera «а» es cirílica: se ve igual que «apple.com» pero es otro dominio.
    with pytest.raises(LinkError, match="alfabetos"):
        normalize_url("https://аpple.com/login")


def test_no_se_encadenan_acortadores():
    for host in ("bit.ly", "tinyurl.com", "www.t.co", "sub.is.gd"):
        with pytest.raises(LinkError, match="acortado"):
            normalize_url(f"https://{host}/abc")


def test_no_se_acorta_el_propio_sitio():
    own = {"fastools.org"}
    for url in ("https://fastools.org/x", "https://www.fastools.org/x", "https://a.fastools.org/"):
        with pytest.raises(LinkError, match="mismo sitio"):
            normalize_url(url, own_hosts=own)
    assert normalize_url("https://notfastools.org/", own_hosts=own)  # no es subdominio


def test_dominios_bloqueados_incluyen_subdominios():
    blocked = parse_host_list("Malo.com, www.peor.net;otro.org")
    assert blocked == {"malo.com", "peor.net", "otro.org"}
    with pytest.raises(LinkError, match="no está permitido"):
        normalize_url("https://sub.malo.com/x", blocked_hosts=blocked)
    assert host_is_blocked("https://www.peor.net/x", blocked)
    assert not host_is_blocked("https://bueno.com/x", blocked)


def test_codigos_validos():
    assert is_valid_code("abc123")
    assert not is_valid_code("abc")           # muy corto
    assert not is_valid_code("a" * 13)        # muy largo
    assert not is_valid_code("ab/../c")
    assert not is_valid_code("")


# ---------------------------------------------------------------------------
# Almacén SQLite
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    return LinkStore(tmp_path / "data" / "links.db", salt=b"sal-de-prueba")


def test_crear_y_reutilizar_codigo(store):
    code, created = store.create("https://ejemplo.com/a")
    assert created and is_valid_code(code) and len(code) == 6
    again, created_again = store.create("https://ejemplo.com/a")
    assert (again, created_again) == (code, False)
    other, _ = store.create("https://ejemplo.com/b")
    assert other != code and store.count() == 2


def test_crea_la_carpeta_de_datos_y_esta_disponible(tmp_path):
    s = LinkStore(tmp_path / "no" / "existe" / "links.db")
    assert s.available()
    assert (tmp_path / "no" / "existe" / "links.db").exists()


def test_resolver_cuenta_visitas_pero_get_no(store):
    code, _ = store.create("https://ejemplo.com/a")
    assert store.get(code)["clicks"] == 0           # la vista previa no cuenta
    assert store.resolve(code)["url"] == "https://ejemplo.com/a"
    assert store.resolve(code)["url"] == "https://ejemplo.com/a"
    assert store.get(code)["clicks"] == 2
    assert store.resolve("noexiste") is None


def test_los_reportes_distintos_bloquean_el_enlace(store):
    code, _ = store.create("https://ejemplo.com/a")
    assert store.report(code, "ip-1", threshold=3) == "reported"
    assert store.report(code, "ip-1", threshold=3) == "reported"   # el mismo informante no suma
    assert store.report(code, "ip-2", threshold=3) == "reported"
    assert store.report(code, "ip-3", threshold=3) == "disabled"
    assert store.get(code)["disabled"] == 1
    assert store.report(code, "ip-4", threshold=3) == "disabled"
    assert store.report("noexiste", "ip-1", threshold=3) == "unknown"


def test_no_se_guarda_la_ip_en_claro(store, tmp_path):
    code, _ = store.create("https://ejemplo.com/a")
    store.report(code, "203.0.113.9", threshold=3)
    raw = (tmp_path / "data" / "links.db").read_bytes()
    assert b"203.0.113.9" not in raw


def test_un_enlace_bloqueado_no_se_puede_volver_a_crear(store):
    code, _ = store.create("https://ejemplo.com/a")
    for ip in ("1", "2", "3"):
        store.report(code, ip, threshold=3)
    with pytest.raises(LinkError, match="bloqueado"):
        store.create("https://ejemplo.com/a")


def test_limite_de_enlaces(tmp_path):
    s = LinkStore(tmp_path / "links.db", max_links=2)
    s.create("https://ejemplo.com/1")
    s.create("https://ejemplo.com/2")
    with pytest.raises(LinkCapacityError):
        s.create("https://ejemplo.com/3")
    # Una URL ya existente se reutiliza aunque el almacén esté lleno.
    assert s.create("https://ejemplo.com/1")[1] is False


def test_purga_de_enlaces_sin_uso_conserva_los_bloqueados(store):
    viejo, _ = store.create("https://ejemplo.com/viejo")
    usado, _ = store.create("https://ejemplo.com/usado")
    bloqueado, _ = store.create("https://ejemplo.com/bloqueado")
    for ip in ("1", "2", "3"):
        store.report(bloqueado, ip, threshold=3)

    long_ago = int(time.time()) - 400 * 86400
    with store._conn() as conn:
        conn.execute("UPDATE links SET created = ?", (long_ago,))
        conn.execute("UPDATE links SET last_used = ? WHERE code = ?", (int(time.time()), usado))

    assert store.purge_stale(365) == 1
    assert store.get(viejo) is None
    assert store.get(usado) is not None
    assert store.get(bloqueado) is not None          # el bloqueo no se pierde
    assert store.purge_stale(0) == 0                 # 0 = nunca caduca


# ---------------------------------------------------------------------------
# Rutas HTTP
# ---------------------------------------------------------------------------


@pytest.fixture
def api(client, tmp_path, monkeypatch):
    """Cliente con un almacén temporal y un informante distinguible por cabecera."""
    from videodl import shortener
    from videodl.security import RateLimiter

    monkeypatch.setattr(shortener, "store", LinkStore(tmp_path / "links.db", salt=b"s"))
    monkeypatch.setattr(shortener, "create_limiter", RateLimiter(100, window_seconds=3600))
    monkeypatch.setattr(shortener, "SHORTLINKS_REPORT_THRESHOLD", 2)
    monkeypatch.setattr(shortener, "_client", lambda r: r.headers.get("x-test-ip", "ip-0"))
    return client


def test_crear_enlace_y_redirigir(api):
    res = api.post("/api/links", json={"url": "ejemplo.com/destino?x=1"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["url"] == "https://ejemplo.com/destino?x=1"
    assert data["path"] == f"/l/{data['code']}" and data["created"] is True

    go = api.get(data["path"], follow_redirects=False)
    assert go.status_code == 302
    assert go.headers["location"] == "https://ejemplo.com/destino?x=1"


def test_vista_previa_no_cuenta_visitas(api):
    code = api.post("/api/links", json={"url": "https://ejemplo.com/a"}).json()["code"]
    for _ in range(3):
        preview = api.get(f"/api/links/{code}")
        assert preview.status_code == 200 and preview.json()["clicks"] == 0
    api.get(f"/l/{code}", follow_redirects=False)
    assert api.get(f"/api/links/{code}").json()["clicks"] == 1


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "http://127.0.0.1/", "https://bit.ly/x", "https://u:p@ejemplo.com/"]
)
def test_la_api_rechaza_destinos_peligrosos(api, url):
    res = api.post("/api/links", json={"url": url})
    assert res.status_code == 400 and res.json()["detail"]


def test_la_api_rechaza_el_propio_sitio(api):
    assert api.post("/api/links", json={"url": "https://fastools.org/x"}).status_code == 400


def test_codigo_inexistente_o_invalido(api):
    assert api.get("/l/zzzzzz", follow_redirects=False).status_code == 404
    assert api.get("/l/..%2fetc", follow_redirects=False).status_code == 404
    assert api.get("/api/links/zzzzzz").status_code == 404
    assert api.post("/api/links/zzzzzz/report").status_code == 404


def test_reportes_bloquean_y_dejan_de_redirigir(api):
    code = api.post("/api/links", json={"url": "https://ejemplo.com/phishing"}).json()["code"]
    assert api.post(f"/api/links/{code}/report", headers={"x-test-ip": "a"}).json() == {"status": "reported"}
    assert api.post(f"/api/links/{code}/report", headers={"x-test-ip": "b"}).json() == {"status": "disabled"}
    assert api.get(f"/l/{code}", follow_redirects=False).status_code == 410
    assert api.get(f"/api/links/{code}").status_code == 410


def test_limite_de_creacion_por_hora(api, monkeypatch):
    from videodl import shortener
    from videodl.security import RateLimiter

    monkeypatch.setattr(shortener, "create_limiter", RateLimiter(2, window_seconds=3600))
    for i in range(2):
        assert api.post("/api/links", json={"url": f"https://ejemplo.com/{i}"}).status_code == 200
    assert api.post("/api/links", json={"url": "https://ejemplo.com/3"}).status_code == 429
    # Un enlace inválido no gasta cupo: sigue devolviendo 400, no 429.
    assert api.post("/api/links", json={"url": "javascript:1"}).status_code == 400


def test_interruptor_de_emergencia(api, monkeypatch):
    from videodl import shortener

    monkeypatch.setattr(shortener, "SHORTLINKS_PER_HOUR", 0)
    assert api.post("/api/links", json={"url": "https://ejemplo.com/a"}).status_code == 503


def test_paginas_y_robots(api):
    assert api.get("/acortar-enlaces").status_code == 200
    en = api.get("/en/acortar-enlaces")
    assert en.status_code == 200 and "Free link shortener" in en.text
    assert "Disallow: /l/" in api.get("/robots.txt").text
    assert api.get("/api/health").json()["shortener"] is True
