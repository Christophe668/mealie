from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from mealie.mcp import asgi
from mealie.mcp.asgi import SimpleRateLimitMiddleware, mcp_enabled, register_mcp


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://mealie.example.com", True),
        ("http://localhost:8080", True),
        ("http://127.0.0.1:9000", True),
        ("http://[::1]:9000", True),
        ("http://192.168.1.5:9925", False),
        ("http://mealie.lan", False),
    ],
)
def test_mcp_enabled(url: str, expected: bool):
    assert mcp_enabled(url) is expected


def test_register_mcp_skips_plain_http_lan_base_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(asgi, "get_app_settings", lambda: SimpleNamespace(BASE_URL="http://192.168.1.5:9925"))
    app = FastAPI()
    routes_before = list(app.router.routes)

    register_mcp(app)

    assert app.router.routes == routes_before
    assert app.user_middleware == []


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def clock(monkeypatch: pytest.MonkeyPatch) -> Generator[_Clock]:
    fake = _Clock()
    monkeypatch.setattr(SimpleRateLimitMiddleware, "_clock", staticmethod(fake))
    SimpleRateLimitMiddleware.reset()
    yield fake
    SimpleRateLimitMiddleware.reset()


def test_per_key_limit_and_window(clock: _Clock):
    assert all(SimpleRateLimitMiddleware.allow("a") for _ in range(SimpleRateLimitMiddleware.LIMIT))
    assert not SimpleRateLimitMiddleware.allow("a")
    assert SimpleRateLimitMiddleware.allow("b")

    clock.now += SimpleRateLimitMiddleware.WINDOW_SECONDS
    assert SimpleRateLimitMiddleware.allow("a")


def test_expired_keys_are_removed(clock: _Clock):
    for i in range(50):
        SimpleRateLimitMiddleware.allow(f"ip-{i}")
    assert SimpleRateLimitMiddleware.tracked_keys() == 50

    clock.now += SimpleRateLimitMiddleware.WINDOW_SECONDS + 1
    SimpleRateLimitMiddleware.allow("fresh")

    assert SimpleRateLimitMiddleware.tracked_keys() == 1


def test_key_count_is_capped(clock: _Clock, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(SimpleRateLimitMiddleware, "MAX_KEYS", 10)
    monkeypatch.setattr(SimpleRateLimitMiddleware, "GLOBAL_LIMIT", 1000)

    for i in range(25):
        SimpleRateLimitMiddleware.allow(f"ip-{i}")

    assert SimpleRateLimitMiddleware.tracked_keys() == 10


def test_global_ceiling_across_keys(clock: _Clock, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(SimpleRateLimitMiddleware, "GLOBAL_LIMIT", 5)

    assert all(SimpleRateLimitMiddleware.allow(f"ip-{i}") for i in range(5))
    assert not SimpleRateLimitMiddleware.allow("ip-new")

    clock.now += SimpleRateLimitMiddleware.WINDOW_SECONDS
    assert SimpleRateLimitMiddleware.allow("ip-new")
