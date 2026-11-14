"""Pasos pytest-bdd de los escenarios de observabilidad."""
import uuid

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from conftest import DEPARTMENTS, FailingModel, FixedClock, SlowModel
from app.llm import FakeModel

scenarios("features/observability.feature")

ROUTED_QUESTION = "What is the weather today?"


@pytest.fixture
def ctx():
    """Estado de un escenario: reloj, modelo, opciones y ultima respuesta."""
    return {
        "clock": FixedClock(),
        "model": None,
        "delay_ms": None,
        "overrides": {},
        "observed": None,
        "response": None,
        "answer_text": None,
    }


def _observed(make_observed, ctx):
    if ctx["observed"] is None:
        model = ctx["model"] or FakeModel(DEPARTMENTS)
        if ctx["delay_ms"] is not None:
            model = SlowModel(model, ctx["clock"], ctx["delay_ms"])
        ctx["observed"] = make_observed(
            model=model, clock=ctx["clock"], **ctx["overrides"]
        )
    return ctx["observed"]


def _ask(make_observed, ctx, question, headers=None):
    observed = _observed(make_observed, ctx)
    ctx["response"] = observed.client.post(
        "/ask", json={"question": question}, headers=headers or {}
    )
    if ctx["response"].status_code == 200:
        ctx["answer_text"] = ctx["response"].json()["answer"]
    ctx["question"] = question


def _lines_for(ctx, event, request_id):
    events = _observed_events(ctx, event)
    return [e for e in events if e["request_id"] == request_id]


def _observed_events(ctx, event):
    return ctx["observed"].events(event)


@given(parsers.parse("each model call takes {n:d} ms"))
def slow_model(ctx, n):
    ctx["delay_ms"] = n


@given("a model that always fails")
def failing_model(ctx):
    ctx["model"] = FailingModel()


@given(parsers.parse("a latency target of {n:d} ms"))
def latency_target(ctx, n):
    ctx["overrides"]["slo_p95_ms"] = n


@when(parsers.parse('I ask "{question}" without a request id'))
def ask_without_id(make_observed, ctx, question):
    _ask(make_observed, ctx, question)


@when(parsers.parse('I ask "{question}" with the request id "{request_id}"'))
def ask_with_id(make_observed, ctx, question, request_id):
    _ask(make_observed, ctx, question, {"X-Request-ID": request_id})


@when(parsers.parse("I ask {n:d} questions"))
def ask_many(make_observed, ctx, n):
    for _ in range(n):
        _ask(make_observed, ctx, ROUTED_QUESTION)


@when("I request the metrics")
def request_metrics(make_observed, ctx):
    ctx["response"] = _observed(make_observed, ctx).client.get("/metrics")


@when("I request the home page")
def request_home(make_observed, ctx):
    ctx["response"] = _observed(make_observed, ctx).client.get("/")


@then(parsers.parse("the response status is {code:d}"))
def check_status(ctx, code):
    assert ctx["response"].status_code == code


@then("the X-Request-ID header is a generated UUID")
def header_is_uuid(ctx):
    value = ctx["response"].headers["X-Request-ID"]
    assert str(uuid.UUID(value)) == value


@then("the body request_id equals the X-Request-ID header")
def body_matches_header(ctx):
    response = ctx["response"]
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


@then(parsers.parse('the X-Request-ID header is "{value}"'))
def header_is(ctx, value):
    assert ctx["response"].headers["X-Request-ID"] == value


@then(parsers.parse('the body request_id is "{value}"'))
def body_request_id_is(ctx, value):
    assert ctx["response"].json()["request_id"] == value


@then(
    parsers.parse(
        'the log has a "request" line for "{rid}" with status {status:d} '
        "and latency {latency:d} ms"
    )
)
def request_line(ctx, rid, status, latency):
    lines = _lines_for(ctx, "request", rid)
    assert len(lines) == 1
    line = lines[0]
    assert (line["method"], line["path"]) == ("POST", "/ask")
    assert line["status"] == status
    assert line["latency_ms"] == latency


@then(parsers.parse('the log has an "agent_run" line for "{rid}"'))
def agent_run_line(ctx, rid):
    lines = _lines_for(ctx, "agent_run", rid)
    assert len(lines) == 1
    assert lines[0]["steps"] == 2
    assert lines[0]["stopped"] is False


@then(parsers.parse('the log has an "audit" line for "{rid}" with tool "{tool}"'))
def audit_line(ctx, rid, tool):
    lines = _lines_for(ctx, "audit", rid)
    assert [(e["action"], e["tool"]) for e in lines] == [("tool_call", tool)]


@then("the log does not contain the question or the answer")
def log_has_no_personal_text(ctx):
    raw = ctx["observed"].stream.getvalue()
    assert ctx["question"] not in raw
    assert ctx["answer_text"] not in raw


@then(parsers.parse('the log does not contain "{text}"'))
def log_lacks_text(ctx, text):
    assert text not in ctx["observed"].stream.getvalue()


@then(parsers.parse('the error body is "{detail}" with request id "{rid}"'))
def error_body(ctx, detail, rid):
    assert ctx["response"].json() == {"detail": detail, "request_id": rid}
    assert ctx["response"].headers["X-Request-ID"] == rid


@then(parsers.parse('the log has an "error" line for "{rid}" with type "{kind}"'))
def error_line(ctx, rid, kind):
    lines = _lines_for(ctx, "error", rid)
    assert [e["error_type"] for e in lines] == [kind]


@then("the metrics show 2 requests and no errors")
def metrics_counts(ctx):
    body = ctx["response"].json()
    assert body["requests"] == 2
    assert body["error_rate"] == 0


@then(parsers.parse("the metrics show tokens and a p95 of {n:d} ms"))
def metrics_tokens_and_p95(ctx, n):
    body = ctx["response"].json()
    assert body["tokens"]["input"] > 0
    assert body["tokens"]["output"] > 0
    assert body["latency_ms"]["p95"] == n


@then(parsers.parse("the latency target is met: {met}"))
def target_met(ctx, met):
    slo = ctx["response"].json()["slo"]
    assert slo["met"] is (met == "true")
    assert slo["p95_ms_target"] == ctx["overrides"]["slo_p95_ms"]


@then("the page has a place for the request id")
def page_shows_request_id(ctx):
    page = ctx["response"].text
    assert 'data-testid="request-id"' in page
    assert "request_id" in page
