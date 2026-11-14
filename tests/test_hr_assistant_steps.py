"""Pasos pytest-bdd de los escenarios del HR Assistant."""
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from conftest import ScriptedModel, tool_call

scenarios("features/hr_assistant.feature")


@pytest.fixture
def ctx():
    """Estado de un escenario: opciones, modelo y ultima respuesta."""
    return {"overrides": {}, "model": None, "response": None}


def _client(make_client, ctx):
    return make_client(model=ctx["model"], **ctx["overrides"])


@given(parsers.parse("a model that never answers and a limit of {n:d} steps"))
def never_answering_model(ctx, n):
    ctx["model"] = ScriptedModel([tool_call("get_employee", employee_id="EMP-0001")])
    ctx["overrides"]["agent_max_steps"] = n


@given(parsers.parse("a question limit of {n:d} characters"))
def question_limit(ctx, n):
    ctx["overrides"]["max_question_chars"] = n


@when(parsers.parse('I ask "{question}"'))
def ask(make_client, ctx, question):
    client = _client(make_client, ctx)
    ctx["response"] = client.post("/ask", json={"question": question})


@when("I ask an empty question")
def ask_empty(make_client, ctx):
    ctx["response"] = _client(make_client, ctx).post("/ask", json={"question": ""})


@when(parsers.parse("I ask a question of {n:d} characters"))
def ask_long(make_client, ctx, n):
    ctx["response"] = _client(make_client, ctx).post("/ask", json={"question": "a" * n})


@when(parsers.parse('I ask "{question}" with one turn of history'))
def ask_with_history(make_client, ctx, question):
    ctx["client"] = _client(make_client, ctx)
    history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    ]
    ctx["response"] = ctx["client"].post(
        "/ask", json={"question": question, "history": history}
    )
    assert ctx["response"].status_code == 200


@when(parsers.parse('I ask "{question}" without history'))
def ask_without_history(ctx, question):
    ctx["response"] = ctx["client"].post("/ask", json={"question": question})


@when("I request the health endpoint")
def request_health(make_client, ctx):
    ctx["response"] = _client(make_client, ctx).get("/health")


@when("I request the home page")
def request_home(make_client, ctx):
    ctx["response"] = _client(make_client, ctx).get("/")


@then(parsers.parse("the response status is {code:d}"))
def check_status(ctx, code):
    assert ctx["response"].status_code == code


@then(parsers.parse('the answer mentions "{text}"'))
def answer_mentions(ctx, text):
    assert text in ctx["response"].json()["answer"]


@then(parsers.parse('the answer is "{text}"'))
def answer_is(ctx, text):
    assert ctx["response"].json()["answer"] == text


@then(parsers.parse('the tools used are "{name}"'))
def tools_used_are(ctx, name):
    assert set(ctx["response"].json()["tools_used"]) == {name}


@then("no tools were used")
def no_tools(ctx):
    assert ctx["response"].json()["tools_used"] == []


@then(parsers.parse("the step count is {n:d}"))
def step_count(ctx, n):
    assert ctx["response"].json()["steps"] == n


@then('the health status is "ok" and includes a numeric pid')
def health_ok(ctx):
    body = ctx["response"].json()
    assert body["status"] == "ok"
    assert isinstance(body["pid"], int)


@then('the page contains the test ids "question", "send" and "answer"')
def page_has_test_ids(ctx):
    for test_id in ("question", "send", "answer"):
        assert f'data-testid="{test_id}"' in ctx["response"].text
