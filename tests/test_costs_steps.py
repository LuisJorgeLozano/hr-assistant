"""Pasos pytest-bdd de los escenarios de costos."""
import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from conftest import DEPARTMENTS, LARGE, SMALL, gateway_reply, make_gateway
from app.llm import FakeModel

scenarios("features/costs.feature")

API_TOKEN = "cf-secret-token-123"
MODELS = {"small": SMALL, "large": LARGE}


@pytest.fixture
def ctx():
    """Estado de un escenario: opciones, modelo y respuestas."""
    return {
        "overrides": {},
        "model": None,
        "history": [],
        "response": None,
        "responses": [],
        "tokens": {},
    }


def _gateway_config(make_config, ctx):
    return make_config(
        model_provider="gateway",
        cf_account_id="acct",
        cf_gateway_id="gw",
        cf_api_token=API_TOKEN,
        cache_ttl_seconds=60,
        **ctx["overrides"],
    )


def _post(make_client, ctx, question, headers=None, reuse=False, **overrides):
    options = dict(ctx["overrides"], **overrides)
    if reuse and "client" in ctx:
        client = ctx["client"]
    else:
        client = make_client(ctx["model"] or FakeModel(DEPARTMENTS), **options)
    body = {"question": question}
    if ctx["history"]:
        body["history"] = ctx["history"]
    ctx["client"] = client
    ctx["response"] = client.post("/ask", json=body, headers=headers or {})
    ctx["responses"].append(ctx["response"])
    return ctx["response"]


@given("routing is off")
def routing_off(ctx):
    ctx["overrides"]["routing"] = False


@given(parsers.parse("a conversation history of {n:d} messages"))
def long_history(ctx, n):
    roles = ["user", "assistant"]
    ctx["history"] = [
        {"role": roles[i % 2], "content": f"earlier message number {i} here"}
        for i in range(n)
    ]


@given("a gateway that is unreachable")
def unreachable_gateway(make_config, ctx):
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    ctx["model"] = make_gateway(_gateway_config(make_config, ctx), handler)


@given("a gateway that answers from its cache")
def cached_gateway(make_config, ctx):
    ctx["model"] = make_gateway(
        _gateway_config(make_config, ctx), lambda request: gateway_reply(
            cache_status="HIT"
        )
    )


@when(parsers.parse('I ask "{question}"'))
def ask(make_client, ctx, question):
    _post(make_client, ctx, question)


@when(parsers.parse('I ask "{question}" with the request id "{request_id}"'))
def ask_with_id(make_client, ctx, question, request_id):
    _post(make_client, ctx, question, {"X-Request-ID": request_id})


@when(
    parsers.parse(
        'I ask "{question}" with a window of {small:d} and again with a '
        "window of {large:d}"
    )
)
def ask_with_two_windows(make_client, ctx, question, small, large):
    for name, window in (("small", small), ("large", large)):
        response = _post(make_client, ctx, question, history_window=window)
        ctx["tokens"][name] = response.json()["input_tokens"]


@when(parsers.parse("I ask {n:d} questions"))
def ask_many(make_client, ctx, n):
    for _ in range(n):
        _post(make_client, ctx, "Tell me about EMP-0004", reuse=True)


@when("I request the metrics")
def request_metrics(ctx):
    ctx["metrics"] = ctx["client"].get("/metrics").json()


@then(parsers.parse("the response status is {code:d}"))
def check_status(ctx, code):
    assert ctx["response"].status_code == code


@then(parsers.parse("the answer used the {size} model"))
def used_model(ctx, size):
    assert ctx["response"].json()["model"] == MODELS[size]


@then(parsers.parse('the route is "{route}"'))
def route_is(ctx, route):
    assert ctx["response"].json()["route"] == route


@then("the cost is greater than zero")
def cost_positive(ctx):
    assert ctx["response"].json()["cost_usd"] > 0


@then("the cost is zero")
def cost_zero(ctx):
    assert ctx["response"].json()["cost_usd"] == 0


@then(parsers.parse("there is at least {n:d} cached call"))
def cached_calls(ctx, n):
    assert ctx["response"].json()["cached_calls"] >= n


@then("the small window used fewer input tokens")
def window_saves_tokens(ctx):
    assert ctx["tokens"]["small"] < ctx["tokens"]["large"]


@then("the metrics cost equals the sum of the answer costs")
def metrics_cost(ctx):
    total = sum(r.json()["cost_usd"] for r in ctx["responses"])
    assert total > 0
    assert ctx["metrics"]["cost_usd"] == pytest.approx(total)


@then(parsers.parse('the error body is "{detail}" with request id "{rid}"'))
def error_body(ctx, detail, rid):
    assert ctx["response"].json() == {"detail": detail, "request_id": rid}


@then("the response does not contain the API token")
def no_token_leak(ctx):
    assert API_TOKEN not in ctx["response"].text
