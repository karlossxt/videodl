import pytest

from videodl.security import ConcurrencyLimiter, RateLimiter


def test_rate_limiter_counts_within_window():
    limiter = RateLimiter(per_minute=3)
    assert all(limiter.allow("1.2.3.4") for _ in range(3))
    assert limiter.allow("1.2.3.4") is False
    # Otra clave no se ve afectada.
    assert limiter.allow("5.6.7.8") is True


def test_rate_limiter_disabled():
    limiter = RateLimiter(per_minute=0)
    assert all(limiter.allow("x") for _ in range(100))


def test_concurrency_limiter():
    limiter = ConcurrencyLimiter(1)
    assert limiter.acquire() is True
    assert limiter.acquire() is False
    limiter.release()
    assert limiter.acquire() is True
    limiter.release()


def test_concurrency_limiter_no_revienta_si_se_libera_de_mas():
    limiter = ConcurrencyLimiter(1)
    limiter.release()  # no debe lanzar ValueError
    assert limiter.acquire() is True
    limiter.release()


# ---------------------------------------------------------------------------
# client_ip: IP del visitante detrás de un proxy
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(self, headers=None, peer="10.0.0.1"):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.client = type("C", (), {"host": peer})() if peer else None


def test_client_ip_por_defecto_ignora_cabeceras_falsificables():
    from videodl.security import client_ip

    req = _FakeRequest({"cf-connecting-ip": "1.2.3.4", "x-forwarded-for": "9.9.9.9"})
    assert client_ip(req) == "10.0.0.1"           # sin cabecera configurada, no se fía de nada
    assert client_ip(req, "") == "10.0.0.1"


def test_client_ip_usa_la_cabecera_configurada():
    from videodl.security import client_ip

    req = _FakeRequest({"cf-connecting-ip": "203.0.113.7"})
    assert client_ip(req, "cf-connecting-ip") == "203.0.113.7"
    v6 = _FakeRequest({"cf-connecting-ip": "2001:db8::1"})
    assert client_ip(v6, "cf-connecting-ip") == "2001:db8::1"


def test_client_ip_toma_el_primer_valor_si_hay_varios():
    from videodl.security import client_ip

    req = _FakeRequest({"x-real": "203.0.113.7, 10.1.1.1"})
    assert client_ip(req, "x-real") == "203.0.113.7"


@pytest.mark.parametrize("value", ["", "no-es-una-ip", "999.1.1.1", "1.2.3.4:80", "<script>"])
def test_client_ip_ignora_valores_que_no_son_una_ip(value):
    from videodl.security import client_ip

    req = _FakeRequest({"cf-connecting-ip": value})
    assert client_ip(req, "cf-connecting-ip") == "10.0.0.1"


def test_client_ip_sin_cabecera_ni_conexion():
    from videodl.security import client_ip

    assert client_ip(_FakeRequest(peer=None), "cf-connecting-ip") == "desconocido"
