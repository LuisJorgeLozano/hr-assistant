"""Pruebas unitarias del modelo real, con transporte simulado (sin red)."""
import json

import httpx
import pytest

from conftest import SMALL, gateway_reply, make_gateway

from app.llm import ModelUnavailable

URL = (
    "https://gateway.ai.cloudflare.com/v1/acct/gw/"
    "workers-ai/v1/chat/completions"
)
MESSAGES = [{"role": "user", "content": "Hola"}]


@pytest.fixture
def gateway_config(make_config):
    def _make(**overrides):
        return make_config(
            model_provider="gateway",
            cf_account_id="acct",
            cf_gateway_id="gw",
            cf_api_token="tok",
            **overrides,
        )

    return _make


@pytest.mark.parametrize("ttl, expected", [(60, "60"), (0, None)])
def test_request_has_the_exact_url_body_and_headers(gateway_config, ttl, expected):
    seen = []

    def handler(request):
        seen.append(request)
        return gateway_reply()

    config = gateway_config(
        cache_ttl_seconds=ttl, model_max_tokens=123, model_temperature=0
    )
    make_gateway(config, handler).complete(MESSAGES, SMALL)
    request = seen[0]
    assert str(request.url) == URL
    assert request.headers["authorization"] == "Bearer tok"
    assert request.headers.get("cf-aig-cache-ttl") == expected
    assert json.loads(request.content) == {
        "model": SMALL,
        "messages": MESSAGES,
        "max_tokens": 123,
        "temperature": 0,
        # Decision: response_format se envia siempre (lo mas simple), porque
        # el agente exige JSON en toda respuesta del modelo.
        "response_format": {"type": "json_object"},
    }


def test_request_asks_for_a_json_object(gateway_config):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return gateway_reply()

    make_gateway(gateway_config(), handler).complete(MESSAGES, SMALL)
    assert seen[0]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize(
    "status, cached", [("HIT", True), ("MISS", False), (None, False)]
)
def test_usage_and_cache_status_are_read_from_the_response(
    gateway_config, status, cached
):
    model = make_gateway(
        gateway_config(), lambda request: gateway_reply(cache_status=status)
    )
    completion = model.complete(MESSAGES, SMALL)
    assert completion.text == '{"answer": "ok"}'
    assert (completion.input_tokens, completion.output_tokens) == (10, 5)
    assert completion.cached is cached
    assert completion.model == SMALL


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(500, text="oops"),
        lambda request: httpx.Response(200, text="not json"),
        lambda request: httpx.Response(200, json={"unexpected": True}),
        lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow")),
    ],
    ids=["http-error", "broken-json", "missing-fields", "timeout"],
)
def test_any_gateway_failure_becomes_model_unavailable(gateway_config, handler):
    model = make_gateway(gateway_config(), handler)
    with pytest.raises(ModelUnavailable):
        model.complete(MESSAGES, SMALL)
