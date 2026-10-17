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
