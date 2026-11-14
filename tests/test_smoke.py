"""Pruebas unitarias de la prueba de humo, con respuestas simuladas."""
import importlib.util
from pathlib import Path

import httpx
import pytest

SMOKE_FILE = Path(__file__).resolve().parents[1] / "scripts" / "smoke.py"
KEY = "smoke-test-key-0123456789"


@pytest.fixture(name="smoke_module")
def load_smoke_module():
    spec = importlib.util.spec_from_file_location("smoke", SMOKE_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_client(ask_without_key=401, ask_with_key=200):
    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.headers.get("X-API-Key") == KEY:
            return httpx.Response(ask_with_key, json={"answer": "ok"})
        return httpx.Response(ask_without_key, json={"detail": "nope"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_smoke_prints_ok_for_each_check_when_the_service_is_healthy(
    smoke_module, capsys
):
    assert smoke_module.smoke("https://hr.test", KEY, make_client()) is True
    output = capsys.readouterr().out
    assert output.count("[OK]") == 3
    assert "[FAIL]" not in output
    assert KEY not in output


def test_smoke_fails_and_exits_nonzero_when_ask_is_open_without_a_key(
    smoke_module, capsys, monkeypatch
):
    client = make_client(ask_without_key=200)
    assert smoke_module.smoke("https://hr.test", KEY, client) is False
    assert capsys.readouterr().out.count("[FAIL]") == 1
    monkeypatch.delenv("SMOKE_API_KEY", raising=False)
    assert smoke_module.main(["https://hr.test"]) != 0
