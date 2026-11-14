"""Pruebas unitarias de la configuracion de produccion."""
import pytest

from app.config import ConfigError, load_config

LONG_KEY = "a-key-with-enough-length"


def test_production_defaults_are_development_with_no_keys():
    config = load_config({})
    assert config.environment == "development"
    assert config.api_keys == {}
    assert config.rate_limit_per_minute == 30


def test_well_formed_api_keys_become_a_client_map_without_spaces():
    config = load_config(
        {
            "API_KEYS": f" acme : {LONG_KEY} , globex:other-key-long-enough ",
            "ENVIRONMENT": "production",
            "RATE_LIMIT_PER_MINUTE": "5",
        }
    )
    assert config.api_keys == {"acme": LONG_KEY, "globex": "other-key-long-enough"}
    assert config.environment == "production"
    assert config.rate_limit_per_minute == 5


@pytest.mark.parametrize(
    "value, entry, length",
    [
        ("acme:abc,nocolonhere", 2, 11),
        (":abcdef", 1, 7),
        ("acme:", 1, 5),
        ("acme:abc,acme:def", 2, 8),
    ],
)
def test_malformed_api_keys_report_position_and_length_never_the_value(
    value, entry, length
):
    with pytest.raises(ConfigError) as error:
        load_config({"API_KEYS": value})
    message = str(error.value)
    assert "API_KEYS" in message
    assert f"entry {entry}" in message
    assert f"length {length}" in message
    for secret in ("abc", "def", "abcdef", "nocolonhere"):
        assert secret not in message


@pytest.mark.parametrize("value", ["0", "-3", "often"])
def test_invalid_rate_limit_prevents_startup(value):
    with pytest.raises(ConfigError, match="RATE_LIMIT_PER_MINUTE"):
        load_config({"RATE_LIMIT_PER_MINUTE": value})


def test_repr_of_the_config_never_shows_the_keys(make_config):
    text = repr(make_config(api_keys={"acme": "super-secret-key-value-1"}))
    assert "super-secret-key-value-1" not in text
