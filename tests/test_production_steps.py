"""Pasos pytest-bdd de los escenarios de produccion."""
import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, scenarios, then, when

from conftest import (
    ACME_KEY,
    API_KEYS,
    DEPARTMENTS,
    EMPLOYEES_FILE,
    FixedClock,
    make_logger,
    read_events,
)
from app.config import ConfigError, load_config
from app.llm import FakeModel
from app.main import create_app

scenarios("features/production.feature")

SAFE_PRODUCTION = {
    "environment": "production",
    "model_provider": "gateway",
    "cf_account_id": "account",
    "cf_api_token": "token",
    "langsmith_tracing": False,
    "api_keys": {"acme": ACME_KEY},
}
UNSAFE_CHANGES = {
    "the fake model": {"model_provider": "fake"},
    "no API keys": {"api_keys": {}},
    "a key shorter than 16": {"api_keys": {"acme": "short-key-1234"}},
    "traces that show inputs": {"langsmith_tracing": True, "hide_inputs": False},
}


@pytest.fixture
def ctx():
    """Estado de un escenario: reloj, opciones, respuestas y error."""
    return {
        "clock": FixedClock(),
        "overrides": {},
        "app": None,
        "responses": [],
        "response": None,
        "error": None,
        "config": None,
        "stream": None,
    }


def _client(make_config, directory, ctx):
    """Crea (una vez) la aplicacion y un cliente sin clave por omision."""
    if ctx["app"] is None:
        config = make_config(**ctx["overrides"])
        logger, stream = make_logger(ctx["clock"])
        app = create_app(
            config, FakeModel(DEPARTMENTS), directory, ctx["clock"], logger
        )
        ctx["app"] = TestClient(app, raise_server_exceptions=False)
        ctx["stream"] = stream
    return ctx["app"]


def _send(make_config, directory, ctx, route, headers=None):
    method, path = route.split(" ")
    client = _client(make_config, directory, ctx)
    if method == "POST":
        response = client.post(path, json={"question": "Hi"}, headers=headers)
    else:
        response = client.get(path, headers=headers)
    ctx["response"] = response
    ctx["responses"].append(response)


def _ask(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    make_config, directory, ctx, client_name, question, request_id=None
):
    # Los argumentos son las fixtures de pytest-bdd más los datos del paso.
    headers = {"X-API-Key": API_KEYS[client_name]}
    if request_id:
        headers["X-Request-ID"] = request_id
    response = _client(make_config, directory, ctx).post(
        "/ask", json={"question": question}, headers=headers
    )
    ctx["response"] = response
    ctx["responses"].append(response)


def _line(ctx, event, request_id):
    events = read_events(ctx["stream"])
    lines = [e for e in events if e["event"] == event]
    return [e for e in lines if e["request_id"] == request_id]


@given(parsers.parse("a limit of {n:d} requests per minute"))
def request_limit(ctx, n):
    ctx["overrides"]["rate_limit_per_minute"] = n


@given(parsers.parse("a production setup with {problem}"))
def production_setup(make_config, ctx, problem):
    values = dict(SAFE_PRODUCTION, **UNSAFE_CHANGES[problem])
    ctx["config"] = make_config(**values)


@when(parsers.parse('I send "{route}" without a key'))
def send_without_key(make_config, directory, ctx, route):
    _send(make_config, directory, ctx, route)


@when(parsers.parse('I send "{route}" with the key "{key}"'))
def send_with_key(make_config, directory, ctx, route, key):
    _send(make_config, directory, ctx, route, {"X-API-Key": key})


@when(parsers.parse('I send "{route}" with the key of "{name}"'))
def send_with_client_key(make_config, directory, ctx, route, name):
    _send(make_config, directory, ctx, route, {"X-API-Key": API_KEYS[name]})


@when(
    parsers.parse(
        'I ask "{question}" as "{name}" with the request id "{request_id}"'
    )
)
def ask_with_id(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    make_config, directory, ctx, question, name, request_id
):
    _ask(make_config, directory, ctx, name, question, request_id)


@when(parsers.parse('I ask {n:d} questions as "{name}"'))
def ask_many(make_config, directory, ctx, n, name):
    for _ in range(n):
        _ask(make_config, directory, ctx, name, "Tell me about EMP-0004")


@when("one minute and one second passes")
def minute_passes(ctx):
    ctx["clock"].advance_ms(61_000)


@when("I start the product")
def start_product(directory, ctx):
    try:
        create_app(ctx["config"], FakeModel(DEPARTMENTS), directory)
    except ConfigError as error:
        ctx["error"] = str(error)


@when(parsers.parse('I load the configuration with API_KEYS "{value}"'))
def load_malformed(ctx, value):
    try:
        load_config({"API_KEYS": value, "EMPLOYEES_PATH": str(EMPLOYEES_FILE)})
    except ConfigError as error:
        ctx["error"] = str(error)


@then(parsers.parse("the response status is {code:d}"))
def check_status(ctx, code):
    assert ctx["response"].status_code == code


@then(parsers.parse('the response is {code:d} with the detail "{detail}"'))
def check_detail(ctx, code, detail):
    assert ctx["response"].status_code == code
    assert ctx["response"].json()["detail"] == detail


@then("the Retry-After header is a number of seconds up to 60")
def retry_after_header(ctx):
    seconds = int(ctx["response"].headers["Retry-After"])
    assert 1 <= seconds <= 60


@then(parsers.parse('the "{event}" log line for "{rid}" has the client "{name}"'))
def log_has_client(ctx, event, rid, name):
    lines = _line(ctx, event, rid)
    assert lines
    assert all(line["client"] == name for line in lines)


@then("no key appears in the log or in any response")
def no_key_anywhere(ctx):
    texts = [ctx["stream"].getvalue()] + [r.text for r in ctx["responses"]]
    secrets = list(API_KEYS.values()) + ["wrong-key-that-nobody-owns"]
    for secret in secrets:
        assert not any(secret in text for text in texts)


@then(parsers.parse('it refuses to start and the message names "{rule}"'))
def refuses_to_start(ctx, rule):
    assert ctx["error"] is not None
    assert rule in ctx["error"]


@then("the message does not contain any API key")
def message_has_no_key(ctx):
    secrets = list(ctx["config"].api_keys.values())
    assert not any(secret in ctx["error"] for secret in secrets)


@then(parsers.parse('the message names "{first}" and "{second}"'))
def message_names_both(ctx, first, second):
    assert first in ctx["error"]
    assert second in ctx["error"]


@then(parsers.parse('the message does not contain "{text}"'))
def message_lacks_text(ctx, text):
    assert text not in ctx["error"]
