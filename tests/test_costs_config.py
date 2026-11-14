"""Pruebas unitarias de la configuracion de costos."""
import pytest

from app.config import ConfigError, load_config

CLOUDFLARE = {
    "CF_ACCOUNT_ID": "acct",
    "CF_GATEWAY_ID": "gw",
    "CF_API_TOKEN": "secret-token",
}


def test_cost_defaults_follow_the_specification():
    config = load_config({})
    assert config.cf_gateway_id == "default"
    assert config.cf_account_id == ""
    assert config.model_small == "@cf/meta/llama-3.1-8b-instruct-fast"
    assert config.model_large == "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    assert config.routing is True
    assert config.router_max_chars == 80
    assert config.history_window == 6
    assert config.model_max_tokens == 300
    assert config.model_temperature == 0
    assert config.cache_ttl_seconds == 0
    assert str(config.prices_path).endswith("data/model_prices.json")


def test_cost_values_can_be_overridden_and_window_may_be_zero():
    config = load_config(
        {
            "ROUTING": "false",
            "ROUTER_MAX_CHARS": "40",
            "HISTORY_WINDOW": "0",
            "MODEL_MAX_TOKENS": "100",
            "MODEL_TEMPERATURE": "0.5",
            "CACHE_TTL_SECONDS": "60",
        }
    )
    assert config.routing is False
    assert (config.router_max_chars, config.history_window) == (40, 0)
    assert config.model_max_tokens == 100
    assert config.model_temperature == 0.5
    assert config.cache_ttl_seconds == 60


@pytest.mark.parametrize(
    "name, value",
    [
        ("HISTORY_WINDOW", "-1"),
        ("ROUTER_MAX_CHARS", "abc"),
        ("MODEL_MAX_TOKENS", "0"),
        ("CACHE_TTL_SECONDS", "-5"),
        ("ROUTING", "sometimes"),
    ],
)
def test_invalid_cost_values_prevent_startup(name, value):
    with pytest.raises(ConfigError, match=name):
        load_config({name: value})


@pytest.mark.parametrize("missing", sorted(CLOUDFLARE))
def test_gateway_without_a_cloudflare_variable_prevents_startup(missing):
    env = {"MODEL_PROVIDER": "gateway", **CLOUDFLARE}
    del env[missing]
    with pytest.raises(ConfigError, match=missing):
        load_config(env)


def test_api_token_is_not_shown_in_the_config_repr():
    config = load_config({"MODEL_PROVIDER": "gateway", **CLOUDFLARE})
    assert config.cf_api_token == "secret-token"
    assert "secret-token" not in repr(config)
