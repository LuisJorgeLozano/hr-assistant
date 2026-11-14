"""Pruebas unitarias de las reglas de compliance al arrancar."""
import pytest

from app.compliance import check_compliance
from app.config import ConfigError

LONG_KEY = "a-key-with-enough-length"
SAFE = {
    "environment": "production",
    "model_provider": "gateway",
    "api_keys": {"acme": LONG_KEY},
}


@pytest.mark.parametrize(
    "values",
    [
        SAFE,
        {"environment": "development", "model_provider": "fake", "api_keys": {}},
        {"environment": "development", "api_keys": {"acme": "short"}},
    ],
    ids=["safe production", "empty development", "weak development"],
)
def test_safe_production_and_any_development_are_not_blocked(make_config, values):
    check_compliance(make_config(**values))


def test_every_broken_rule_is_reported_together_without_values(make_config):
    config = make_config(
        environment="production",
        model_provider="fake",
        api_keys={"acme": "short-key-1234"},
        langsmith_tracing=True,
        hide_inputs=False,
        hide_outputs=False,
    )
    with pytest.raises(ConfigError) as error:
        check_compliance(config)
    message = str(error.value)
    for rule in ("MODEL_PROVIDER", "API_KEYS", "HIDE_INPUTS", "HIDE_OUTPUTS"):
        assert rule in message
    assert "short-key-1234" not in message


def test_visible_inputs_are_allowed_when_tracing_is_off(make_config):
    values = dict(SAFE, langsmith_tracing=False, hide_inputs=False)
    check_compliance(make_config(**values))
