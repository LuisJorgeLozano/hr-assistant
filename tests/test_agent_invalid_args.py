"""Pruebas de argumentos invalidos: sin 500 y sin datos dudosos en el log."""
import json

import pytest
from conftest import ScriptedModel, final_answer, make_logger, read_events, tool_call

from app.agent import Agent

NON_TEXT_CALLS = [
    ("search_by_department", {"department": 5}),
    ("get_employee", {"employee_id": 7}),
]


@pytest.mark.parametrize("name, args", NON_TEXT_CALLS)
def test_non_text_argument_is_reported_to_the_model(directory, name, args):
    model = ScriptedModel([tool_call(name, **args), final_answer("Sorry")])
    result = Agent(model, directory, 3).run("Anything")
    feedback = model.calls[1][-1]["content"]
    assert f"Invalid arguments for {name}" in feedback
    assert result.answer == "Sorry"
    assert result.tools_used == []


@pytest.mark.parametrize("name, args", NON_TEXT_CALLS)
def test_non_text_argument_does_not_produce_a_500(make_client, name, args):
    model = ScriptedModel([tool_call(name, **args), final_answer("Sorry")])
    client = make_client(model)
    response = client.post("/ask", json={"question": "Anything"})
    assert response.status_code == 200
    assert f"Invalid arguments for {name}" in model.calls[1][-1]["content"]


@pytest.mark.parametrize("name, args", NON_TEXT_CALLS)
def test_non_text_argument_leaves_no_args_in_the_audit_log(directory, name, args):
    logger, stream = make_logger()
    model = ScriptedModel([tool_call(name, **args), final_answer("ok")])
    Agent(model, directory, 3, logger=logger).run("Anything")
    raw = json.dumps(read_events(stream))
    assert "args" not in raw


@pytest.mark.parametrize(
    "name, args",
    [
        ("get_employee", {"employee_id": "my salary is 5000, call 555-1234"}),
        ("search_by_department", {"department": "private free text"}),
    ],
)
def test_unexpected_text_is_not_logged_only_the_tool_name(directory, name, args):
    logger, stream = make_logger()
    model = ScriptedModel([tool_call(name, **args), final_answer("ok")])
    Agent(model, directory, 3, logger=logger).run("Anything")
    events = read_events(stream)
    audits = [e for e in events if e["event"] == "audit"]
    assert len(audits) == 1
    assert audits[0]["tool"] == name
    assert "args" not in audits[0]
    assert list(args.values())[0] not in json.dumps(events)


def test_expected_arguments_are_still_logged(directory):
    logger, stream = make_logger()
    replies = [
        tool_call("search_by_department", department="ventas"),
        final_answer("ok"),
    ]
    Agent(ScriptedModel(replies), directory, 3, logger=logger).run("Sales team?")
    audit = [e for e in read_events(stream) if e["event"] == "audit"][0]
    assert audit["args"] == {"department": "ventas"}
