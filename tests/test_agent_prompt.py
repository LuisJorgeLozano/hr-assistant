"""Pruebas unitarias del prompt de sistema y del analisis tolerante del JSON."""
import pytest

from conftest import ScriptedModel, final_answer, tool_call

from app.agent import Agent

HISTORY = [
    {"role": "user", "content": "old question"},
    {"role": "assistant", "content": "old answer"},
]


def test_first_message_is_a_system_prompt_describing_the_protocol(directory):
    model = ScriptedModel([final_answer("Done")])
    Agent(model, directory, 3).run("Hello")
    first = model.calls[0][0]
    assert first["role"] == "system"
    for expected in ("JSON", "get_employee", "search_by_department", "answer", "tool"):
        assert expected in first["content"]


def test_system_prompt_comes_before_history_and_question(directory):
    model = ScriptedModel([final_answer("Done")])
    Agent(model, directory, 3).run("New question", HISTORY)
    sent = model.calls[0]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[1:3] == HISTORY


def test_system_prompt_survives_a_zero_history_window(make_config, directory):
    model = ScriptedModel([final_answer("Done")])
    config = make_config(history_window=0)
    Agent(model, directory, 3, config=config).run("Hello", HISTORY)
    sent = model.calls[0]
    assert [m["role"] for m in sent] == ["system", "user"]


def test_system_prompt_is_sent_again_on_every_step(directory):
    replies = [tool_call("get_employee", employee_id="EMP-0005"), final_answer("Ok")]
    model = ScriptedModel(replies)
    Agent(model, directory, 3).run("Who is EMP-0005?")
    assert all(call[0]["role"] == "system" for call in model.calls)
    assert len([m for m in model.calls[1] if m["role"] == "system"]) == 1


def test_history_messages_in_the_log_do_not_count_the_system_prompt(directory):
    from conftest import make_logger, read_events  # pylint: disable=import-outside-toplevel

    logger, stream = make_logger()
    model = ScriptedModel([final_answer("Done")])
    Agent(model, directory, 3, logger=logger).run("Hello", HISTORY)
    run = [e for e in read_events(stream) if e["event"] == "agent_run"][0]
    assert run["history_messages"] == 2


@pytest.mark.parametrize(
    "text",
    [
        '```json\n{"answer": "Hi"}\n```',
        '```\n{"answer": "Hi"}\n```',
        'Claro, aqui va: {"answer": "Hi"}',
        'Respuesta:\n```json\n{"answer": "Hi"}\n```\nListo.',
    ],
    ids=["json-fence", "plain-fence", "text-before", "text-around-fence"],
)
def test_parse_accepts_json_wrapped_in_fences_or_text(text):
    assert Agent._parse(text) == {"answer": "Hi"}  # pylint: disable=protected-access


def test_parse_extracts_only_the_first_object():
    first = '{"tool": "get_employee", "args": {"employee_id": "EMP-0001"}}'
    text = f'Uno {first} y {{"answer": "x"}}'
    parsed = Agent._parse(text)  # pylint: disable=protected-access
    assert parsed == {"tool": "get_employee", "args": {"employee_id": "EMP-0001"}}


@pytest.mark.parametrize(
    "text", ["not json at all", "{broken", "", None, "```json\n```"]
)
def test_parse_returns_none_without_valid_json(text):
    assert Agent._parse(text) is None  # pylint: disable=protected-access


def test_fenced_answer_completes_the_run_in_one_step(directory):
    model = ScriptedModel(['```json\n{"answer": "Hola"}\n```'])
    result = Agent(model, directory, 3).run("Hello")
    assert result.answer == "Hola"
    assert result.steps == 1


def test_fenced_tool_call_is_executed(directory):
    fenced = (
        'Voy a buscar:\n```json\n'
        '{"tool": "get_employee", "args": {"employee_id": "EMP-0005"}}\n```'
    )
    model = ScriptedModel([fenced, final_answer("Listo")])
    result = Agent(model, directory, 3).run("Who is EMP-0005?")
    assert result.tools_used == ["get_employee"]
    assert result.answer == "Listo"
