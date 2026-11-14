"""Pruebas unitarias de las palancas de costo dentro del agente."""
import pytest

from conftest import (
    PRICES_FILE,
    SMALL,
    ScriptedModel,
    final_answer,
    tool_call,
)

from app.agent import Agent
from app.pricing import load_prices

HISTORY = [
    {"role": "user" if i % 2 == 0 else "assistant", "content": f"old {i}"}
    for i in range(6)
]


@pytest.mark.parametrize("window, kept", [(0, 0), (2, 2), (50, 6)])
def test_history_is_trimmed_to_the_window(make_config, directory, window, kept):
    model = ScriptedModel([final_answer("Done")])
    config = make_config(history_window=window)
    Agent(model, directory, 3, config=config).run("Hi there", HISTORY)
    # El primer mensaje es el prompt de sistema; no cuenta como historial.
    sent = model.calls[0]
    assert sent[0]["role"] == "system"
    assert len(sent) == kept + 2
    assert sent[-1] == {"role": "user", "content": "Hi there"}
    assert sent[1:-1] == HISTORY[len(HISTORY) - kept:]


def test_one_model_serves_every_step_and_the_cost_adds_up(make_config, directory):
    replies = [tool_call("get_employee", employee_id="EMP-0005"), final_answer("Ok")]
    model = ScriptedModel(replies)
    prices = load_prices(PRICES_FILE)
    agent = Agent(
        model, directory, 3, config=make_config(history_window=0), prices=prices
    )
    result = agent.run("Who is EMP-0005?", HISTORY)
    assert model.models == [SMALL, SMALL]
    assert (result.model, result.route) == (SMALL, "simple")
    assert result.cached_calls == 0
    expected = prices.cost(SMALL, result.input_tokens, result.output_tokens)
    assert result.cost_usd == pytest.approx(expected)
    assert result.cost_usd > 0
