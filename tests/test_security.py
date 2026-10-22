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
