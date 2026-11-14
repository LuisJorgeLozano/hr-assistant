"""Fixtures compartidas de las pruebas del HR Assistant.

Contrato que estas pruebas esperan de la aplicacion (lo implementa el developer):

- ``app.config``: ``Config(model_provider, agent_max_steps, max_question_chars,
  employees_path)`` (dataclass), ``load_config(env: Mapping)`` y ``ConfigError``
  (subclase de ``ValueError``).
- ``app.directory``: ``Directory(path)`` con ``get_employee(id) -> dict | None`` y
  ``search_by_department(name) -> list[dict]``.
- ``app.llm``: ``Completion(text, input_tokens, output_tokens)``, ``FakeModel(
  departments)`` con ``complete(messages) -> Completion`` y
  ``create_model(provider, departments)``.
- ``app.agent``: ``Agent(model, directory, max_steps)`` con ``run(question,
  history=None)`` que devuelve un objeto con ``answer``, ``steps``,
  ``tools_used``, ``input_tokens`` y ``output_tokens``.
- ``app.main``: ``create_app(config=None, model=None, directory=None, clock=None,
  logger=None)``.

Contrato de la sesion 2 (observabilidad):

- ``Config`` agrega con valores por omision ``service_name="hr-assistant"``,
  ``slo_p95_ms=2000``, ``langsmith_tracing=False``, ``hide_inputs=True`` y
  ``hide_outputs=True`` (las pruebas de la sesion 1 siguen construyendola igual).
- ``app.observability``: ``JsonLogger(service, clock, stream=None)`` con
  ``log(event, **fields)``; ``request_id_var`` (``ContextVar``);
  ``Metrics(max_samples=1000)`` con ``record_request(latency_ms, failed)``,
  ``add_tokens(input_tokens, output_tokens)`` y ``snapshot(slo_p95_ms)``.
  El reloj tiene ``now()`` y devuelve un ``datetime`` con zona UTC; la latencia
  es la diferencia de ``now()`` en milisegundos. Los percentiles son de rango
  mas cercano (nearest rank).
- ``app.tracing``: ``is_enabled(env)``, ``make_hider(hide)`` y
  ``traced(name, enabled=False)``.
- ``Agent(model, directory, max_steps, logger=None, tracer=None)``.
- Campo del evento ``error``: ``error_type``.

Contrato de la sesion 3 (costos):

- ``Config`` agrega con valores por omision ``cf_account_id``, ``cf_gateway_id``,
  ``cf_api_token`` (fuera de ``repr``), ``model_small``, ``model_large``,
  ``routing``, ``router_max_chars``, ``history_window``, ``model_max_tokens``,
  ``model_temperature``, ``cache_ttl_seconds`` y ``prices_path``.
- ``app.router.choose_model(question, config) -> (modelo, motivo)``.
- ``app.pricing.load_prices(path)`` devuelve un objeto con
  ``cost(model, input_tokens, output_tokens, cached=False)``. ``create_app``
  lo carga de ``config.prices_path`` y levanta ``ConfigError`` si
  ``model_small`` o ``model_large`` no tienen precio.
- ``Completion`` gana ``model`` y ``cached`` (con valores por omision) y
  ``complete(messages, model=None)`` en todos los modelos.
- ``app.llm.GatewayModel(config, client=None)`` y ``ModelUnavailable``.
- ``Agent(..., config=None, prices=None)``; el resultado suma ``model``,
  ``route``, ``cached_calls`` y ``cost_usd``.
- ``Metrics.add_cost(usd)`` y ``cost_usd`` en el snapshot.
- Un ``X-Request-ID`` valido tiene de 1 a 64 caracteres de ``[A-Za-z0-9._-]``.

Contrato de la sesion 4 (produccion):

- ``Config`` agrega ``environment="development"``, ``api_keys`` (mapa cliente a
  clave, fuera de ``repr``, vacio por omision) y ``rate_limit_per_minute=30``.
  ``load_config`` lee ``ENVIRONMENT``, ``API_KEYS`` y ``RATE_LIMIT_PER_MINUTE``
  (entero mayor que 0). Una ``API_KEYS`` mal formada lanza ``ConfigError`` cuyo
  mensaje nombra ``API_KEYS``, el numero de entrada y su largo con la forma
  ``entry 2`` y ``length 18`` (entrada desde 1), nunca el valor.
- ``app.compliance.check_compliance(config)``: con ``environment="production"``
  lanza ``ConfigError`` (sin valores en el mensaje) si el modelo es ``fake``, si
  no hay claves o alguna mide menos de 16, o si hay trazas con ``hide_inputs``
  o ``hide_outputs`` en falso. Junta todas las faltas en un solo mensaje.
- ``app.ratelimit.RateLimiter(limit, clock)`` con ``check(client) -> int``:
  devuelve 0 si la peticion cabe en el minuto, o los segundos que faltan
  (entero, al menos 1) si se pasa del limite. Usa ``clock.now()``.
- ``create_app`` llama a ``check_compliance``, exige ``X-API-Key`` en
  ``POST /ask`` y ``GET /metrics`` (primero clave, luego limite) y usa su
  ``clock`` inyectado para el limite. El log lleva ``client``.
- ``scripts/smoke.py`` expone ``smoke(url, key, client) -> bool`` y
  ``main(args) -> int``; la clave viene de ``SMOKE_API_KEY``.
- Los clientes de prueba de ``make_client`` y ``make_observed`` mandan la clave
  de ``ACME_KEY`` por omision, asi que las pruebas de las sesiones 1 a 3 no
  cambian.
"""
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Config
from app.directory import Directory
from app.llm import Completion, FakeModel
from app.main import create_app
from app.observability import JsonLogger

EMPLOYEES_FILE = Path(__file__).resolve().parents[2] / "spec" / "employees.json"
PRICES_FILE = Path(__file__).resolve().parents[2] / "spec" / "model_prices.json"
DEPARTMENTS = ["Tecnología", "Ventas", "Finanzas"]
SMALL = "@cf/meta/llama-3.1-8b-instruct-fast"
LARGE = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
ACME_KEY = "acme-test-key-0123456789"
GLOBEX_KEY = "globex-test-key-9876543210"
API_KEYS = {"acme": ACME_KEY, "globex": GLOBEX_KEY}
ACME_HEADERS = {"X-API-Key": ACME_KEY}


def gateway_reply(text='{"answer": "ok"}', cache_status=None):
    """Respuesta del gateway en formato chat completions (10 y 5 tokens)."""
    headers = {"cf-aig-cache-status": cache_status} if cache_status else {}
    body = {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    return httpx.Response(200, json=body, headers=headers)


def make_gateway(config, handler):
    """GatewayModel que habla con ``handler`` en vez de la red."""
    from app.llm import GatewayModel  # pylint: disable=import-outside-toplevel

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GatewayModel(config, client=client)


class ScriptedModel:
    """Modelo de prueba que devuelve respuestas fijas en orden."""

    def __init__(self, replies, cached=False):
        self.replies = list(replies)
        self.cached = cached
        self.calls = []
        self.models = []

    def complete(self, messages, model=None):
        """Devuelve la siguiente respuesta (repite la ultima si se acaban)."""
        self.calls.append(list(messages))
        self.models.append(model)
        index = min(len(self.calls) - 1, len(self.replies) - 1)
        text = self.replies[index]
        words = sum(len(m["content"].split()) for m in messages)
        return Completion(
            text, words, len(text.split()), model=model, cached=self.cached
        )


def tool_call(name, **args):
    """Construye el JSON que el modelo usa para pedir una herramienta."""
    return json.dumps({"tool": name, "args": args})


def final_answer(text):
    """Construye el JSON que el modelo usa para responder."""
    return json.dumps({"answer": text})


class FixedClock:
    """Reloj de prueba: la hora solo cambia cuando la prueba lo pide."""

    def __init__(self):
        self.current = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

    def now(self):
        """Devuelve la hora actual del reloj."""
        return self.current

    def advance_ms(self, milliseconds):
        """Avanza el reloj."""
        self.current += timedelta(milliseconds=milliseconds)


class SlowModel:
    """Envuelve un modelo y hace que cada llamada tarde ``delay_ms``."""

    def __init__(self, inner, clock, delay_ms):
        self.inner = inner
        self.clock = clock
        self.delay_ms = delay_ms

    def complete(self, messages, model=None):
        """Avanza el reloj y delega en el modelo real."""
        self.clock.advance_ms(self.delay_ms)
        return self.inner.complete(messages, model)


class FailingModel:
    """Modelo que siempre truena con un mensaje que no debe llegar al log."""

    def complete(self, messages, model=None):
        """Lanza un error."""
        raise RuntimeError("secret failure detail")


def read_events(stream):
    """Convierte las lineas JSON de un log capturado en diccionarios."""
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]


def make_logger(clock=None, service="hr-assistant"):
    """Crea un logger que escribe en memoria; devuelve ``(logger, stream)``."""
    stream = io.StringIO()
    return JsonLogger(service, clock or FixedClock(), stream), stream


class Observed:
    """Cliente de prueba junto con su reloj y su log capturado."""

    def __init__(self, client, stream, clock):
        self.client = client
        self.stream = stream
        self.clock = clock

    def events(self, name=None):
        """Eventos del log, filtrados por nombre si se indica."""
        events = read_events(self.stream)
        return [e for e in events if name is None or e["event"] == name]


@pytest.fixture
def make_observed(make_config, directory):
    """Fabrica de aplicaciones con reloj fijo y log capturado."""

    def _make(model=None, clock=None, **overrides):
        clock = clock or FixedClock()
        config = make_config(**overrides)
        logger, stream = make_logger(clock, config.service_name)
        model = model or FakeModel(DEPARTMENTS)
        app = create_app(config, model, directory, clock=clock, logger=logger)
        client = TestClient(
            app, raise_server_exceptions=False, headers=ACME_HEADERS
        )
        return Observed(client, stream, clock)

    return _make


@pytest.fixture
def directory():
    return Directory(EMPLOYEES_FILE)


@pytest.fixture
def make_config():
    def _make(**overrides):
        values = {
            "model_provider": "fake",
            "agent_max_steps": 3,
            "max_question_chars": 2000,
            "employees_path": EMPLOYEES_FILE,
            "prices_path": PRICES_FILE,
            "api_keys": dict(API_KEYS),
        }
        values.update(overrides)
        return Config(**values)

    return _make


@pytest.fixture
def make_client(make_config, directory):
    def _make(model=None, **overrides):
        model = model or FakeModel(DEPARTMENTS)
        app = create_app(make_config(**overrides), model, directory)
        return TestClient(app, headers=ACME_HEADERS)

    return _make
