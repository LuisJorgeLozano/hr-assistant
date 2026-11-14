"""Pruebas unitarias del agente."""
import json

from conftest import (
    ScriptedModel,
    final_answer,
    make_logger,
    read_events,
    tool_call,
)

from app.agent import Agent


def test_tool_result_is_fed_back_to_the_model(directory):
    model = ScriptedModel(
        [tool_call("get_employee", employee_id="EMP-0005"), final_answer("Done")]
    )
    result = Agent(model, directory, 3).run("Who is EMP-0005?")
    assert result.answer == "Done"
    assert result.steps == 2
    assert result.tools_used == ["get_employee"]
    last = model.calls[1][-1]
    assert last["role"] == "user"
    assert last["content"].startswith("Resultado de la herramienta: ")
    assert "Sofía" in last["content"]


def test_unknown_tool_is_returned_to_the_model_as_an_error(directory):
    model = ScriptedModel([tool_call("delete_all"), final_answer("Sorry")])
    result = Agent(model, directory, 3).run("Do it")
    assert result.answer == "Sorry"
    assert model.calls[1][-1]["content"].startswith("Resultado de la herramienta: ")


def test_invalid_model_output_is_handled_without_crashing(directory):
    model = ScriptedModel(["not json at all"])
    result = Agent(model, directory, 2).run("Hello")
    assert result.answer == (
        "No pude completar la respuesta. Intenta con una pregunta más concreta."
    )
    assert result.steps == 2


def _run_with_log(directory, replies, max_steps, question, history=None):
    logger, stream = make_logger()
    model = ScriptedModel(replies)
    agent = Agent(model, directory, max_steps, logger=logger)
    result = agent.run(question, history)
    return result, read_events(stream)


def test_each_tool_call_leaves_an_audit_line_with_its_arguments(directory):
    replies = [
        tool_call("get_employee", employee_id="EMP-0001"),
        final_answer("ok"),
    ]
    _, events = _run_with_log(directory, replies, 3, "Who is EMP-0001?")
    audits = [e for e in events if e["event"] == "audit"]
    assert len(audits) == 1
    assert audits[0]["action"] == "tool_call"
    assert audits[0]["tool"] == "get_employee"
    assert audits[0]["args"] == {"employee_id": "EMP-0001"}


def test_agent_run_line_counts_the_work_but_never_includes_the_text(directory):
    question = "Who is EMP-0001, in confidence?"
    history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Yo"},
    ]
    replies = [
        tool_call("get_employee", employee_id="EMP-0001"),
        final_answer("Secret"),
    ]
    result, events = _run_with_log(directory, replies, 3, question, history)
    run = [e for e in events if e["event"] == "agent_run"][0]
    assert run["question_chars"] == len(question)
    assert run["history_messages"] == 2
    assert (run["steps"], run["tools"], run["stopped"]) == (2, ["get_employee"], False)
    assert (run["input_tokens"], run["output_tokens"]) == (
        result.input_tokens,
        result.output_tokens,
    )
    assert result.input_tokens > 0
    raw = json.dumps(events)
    assert question not in raw
    assert "Secret" not in raw


def test_agent_run_reports_stopped_when_the_step_limit_is_reached(directory):
    replies = [tool_call("get_employee", employee_id="EMP-0001")]
    _, events = _run_with_log(directory, replies, 2, "Loop forever")
    run = [e for e in events if e["event"] == "agent_run"][0]
    assert run["stopped"] is True
    assert run["steps"] == 2
