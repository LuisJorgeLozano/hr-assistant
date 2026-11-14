"""Pruebas unitarias de la configuracion."""
import pytest

from app.config import ConfigError, load_config


def test_defaults_are_used_when_environment_is_empty():
    config = load_config({})
    assert config.model_provider == "fake"
    assert config.agent_max_steps == 3
    assert config.max_question_chars == 2000
    assert str(config.employees_path).endswith("data/employees.json")


def test_valid_values_override_the_defaults():
    config = load_config({"AGENT_MAX_STEPS": "5", "MAX_QUESTION_CHARS": "100"})
    assert config.agent_max_steps == 5
    assert config.max_question_chars == 100


@pytest.mark.parametrize("value", ["0", "-1", "abc", ""])
def test_invalid_step_limit_prevents_startup(value):
    with pytest.raises(ConfigError, match="AGENT_MAX_STEPS"):
        load_config({"AGENT_MAX_STEPS": value})


def test_observability_defaults_are_safe():
    config = load_config({})
    assert config.service_name == "hr-assistant"
    assert config.slo_p95_ms == 2000
    assert config.langsmith_tracing is False
    assert config.hide_inputs is True
    assert config.hide_outputs is True


def test_observability_values_can_be_overridden():
    config = load_config(
        {
            "SERVICE_NAME": "hr-test",
            "SLO_P95_MS": "750",
            "LANGSMITH_TRACING": "true",
            "HIDE_INPUTS": "false",
            "HIDE_OUTPUTS": "false",
        }
    )
    assert config.service_name == "hr-test"
    assert config.slo_p95_ms == 750
    assert config.langsmith_tracing is True
    assert (config.hide_inputs, config.hide_outputs) == (False, False)


@pytest.mark.parametrize(
    "name, value",
    [
        ("SLO_P95_MS", "0"),
        ("SLO_P95_MS", "fast"),
        ("HIDE_INPUTS", "maybe"),
        ("HIDE_OUTPUTS", "2"),
        ("LANGSMITH_TRACING", "yes please"),
    ],
)
def test_invalid_observability_values_prevent_startup(name, value):
    with pytest.raises(ConfigError, match=name):
        load_config({name: value})
