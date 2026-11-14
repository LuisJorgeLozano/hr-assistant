"""Pruebas unitarias del limite de peticiones por cliente."""
from conftest import FixedClock

from app.ratelimit import RateLimiter


def test_the_request_over_the_limit_is_blocked_with_the_seconds_left():
    clock = FixedClock()
    limiter = RateLimiter(2, clock)
    assert limiter.check("acme") == 0
    clock.advance_ms(10_000)
    assert limiter.check("acme") == 0
    clock.advance_ms(5_000)
    assert limiter.check("acme") == 45


def test_the_window_frees_when_the_oldest_request_expires():
    clock = FixedClock()
    limiter = RateLimiter(1, clock)
    assert limiter.check("acme") == 0
    assert limiter.check("acme") > 0
    clock.advance_ms(61_000)
    assert limiter.check("acme") == 0
