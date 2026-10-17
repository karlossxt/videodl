import socket

import pytest
from fastapi import HTTPException

from videodl.security import (
    ConcurrencyLimiter,
    RateLimiter,
    ensure_public_url,
    host_is_public,
    validate_url,
)


@pytest.mark.parametrize(
    "url",
    ["http://example.com", "https://foo.bar/baz", "HTTPS://Example.com"],
)
def test_validate_url_accepts_http(url):
    validate_url(url)  # no lanza


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com", "file:///etc/passwd", "javascript:alert(1)", "", "example.com"],
)
def test_validate_url_rejects_other_schemes(url):
    with pytest.raises(HTTPException) as exc:
        validate_url(url)
    assert exc.value.status_code == 400


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "localhost", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1", "0.0.0.0"],
)
def test_private_hosts_are_rejected(host):
    assert host_is_public(host) is False


@pytest.mark.parametrize("host", ["8.8.8.8", "1.1.1.1", "93.184.216.34"])
def test_public_ips_are_allowed(host):
    assert host_is_public(host) is True


def _fake_addrinfo(*ips):
    """Simula el resultado de ``socket.getaddrinfo`` para las IPs indicadas."""
    infos = []
    for ip in ips:
        if ":" in ip:
            infos.append((socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, 0, 0, 0)))
        else:
            infos.append((socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)))
    return infos


def test_domain_resolving_to_public_ip_is_allowed(monkeypatch):
    """Un dominio normal (p. ej. youtube.com) NO debe bloquearse."""
    monkeypatch.setattr(
        "videodl.security.socket.getaddrinfo",
        lambda host, port, *a, **k: _fake_addrinfo("142.251.150.4", "2001:4860:4826:400::"),
    )
    assert host_is_public("www.youtube.com") is True


def test_domain_with_any_private_ip_is_rejected(monkeypatch):
    """Basta con que una de las IPs resueltas sea privada para bloquear el host."""
    monkeypatch.setattr(
        "videodl.security.socket.getaddrinfo",
        lambda host, port, *a, **k: _fake_addrinfo("93.184.216.34", "192.168.1.10"),
    )
    assert host_is_public("rebind.example") is False


def test_unresolvable_domain_is_rejected(monkeypatch):
    def _boom(host, port, *a, **k):
        raise socket.gaierror("no existe")

    monkeypatch.setattr("videodl.security.socket.getaddrinfo", _boom)
    assert host_is_public("no-existe.invalid") is False


def test_ensure_public_url_accepts_public_domain(monkeypatch):
    monkeypatch.setattr(
        "videodl.security.socket.getaddrinfo",
        lambda host, port, *a, **k: _fake_addrinfo("142.251.150.4"),
    )
    ensure_public_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")  # no lanza


def test_ensure_public_url_blocks_private():
    with pytest.raises(HTTPException) as exc:
        ensure_public_url("http://169.254.169.254/latest/meta-data/")
    assert exc.value.status_code == 400


def test_ensure_public_url_blocks_localhost():
    with pytest.raises(HTTPException):
        ensure_public_url("http://localhost:8000/admin")


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
