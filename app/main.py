"""API web sin estado del HR Assistant."""
import functools
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.agent import Agent
from app.auth import API_KEY_HEADER, INVALID_KEY_DETAIL, find_client
from app.compliance import check_compliance
from app.config import Config, ConfigError, load_config
from app.directory import Directory
from app.guardrails import (
    MAX_HISTORY_MESSAGES,
    looks_like_injection,
    redact,
    sanitize_output,
)
from app.llm import ModelUnavailable, create_model
from app.observability import (
    JsonLogger,
    Metrics,
    SystemClock,
    client_var,
    elapsed_ms,
    request_id_var,
)
from app.pricing import load_prices
from app.ratelimit import RateLimiter
from app.tracing import traced

INDEX_FILE = Path(__file__).resolve().parent / "static" / "index.html"
REQUEST_ID_HEADER = "X-Request-ID"
VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
INJECTION_DETAIL = "question rejected by input policy"


class HistoryMessage(BaseModel):
    """Mensaje previo de la conversacion.

    Solo se aceptan ``user`` y ``assistant``: un cliente no puede colar un
    mensaje ``system`` para cambiar las instrucciones del agente.
    """

    role: Literal["user", "assistant"]
    content: str


class AskRequest(BaseModel):
    """Cuerpo de ``POST /ask``."""

    question: str
    history: Optional[List[HistoryMessage]] = None


@dataclass
class Services:
    """Dependencias que necesita ``POST /ask`` para responder."""

    config: Config
    model: Any
    directory: Any
    logger: Any
    tracer: Callable
    prices: Any
    metrics: Metrics


def _pick_request_id(candidate: Optional[str]) -> str:
    """Elige el id de la peticion: el del cliente si es valido, o un UUID.

    :param candidate: valor del encabezado ``X-Request-ID`` (puede faltar)
    :return: el id que se usara en toda la peticion
    """
    if candidate is not None and VALID_REQUEST_ID.fullmatch(candidate):
        return candidate
    return str(uuid.uuid4())


def _client_field(request: Request) -> dict:
    """Devuelve ``{"client": nombre}`` si la peticion se autentico, o vacio.

    :param request: la peticion en curso
    :return: campos extra para el log
    """
    client = getattr(request.state, "client", None)
    return {} if client is None else {"client": client}


def _check_prices(config: Config, prices) -> None:
    """Exige un precio para cada modelo configurado.

    :param config: configuracion de la aplicacion
    :param prices: tabla de precios cargada
    :raises ConfigError: si falta el precio de algun modelo
    """
    for name in (config.model_small, config.model_large):
        if not prices.has(name):
            raise ConfigError(f"No price for model {name!r}")


def _build_tracer(config: Config) -> Callable:
    """Arma el trazador segun la configuracion y la clave de LangSmith.

    :param config: configuracion de la aplicacion
    :return: funcion que envuelve a otra con el trazado
    """
    tracing_on = config.langsmith_tracing and bool(
        os.environ.get("LANGSMITH_API_KEY")
    )
    return functools.partial(
        traced,
        enabled=tracing_on,
        hide_inputs=config.hide_inputs,
        hide_outputs=config.hide_outputs,
    )


def _make_protected(config: Config, limiter: RateLimiter) -> Callable:
    """Crea la dependencia que autentica y aplica el limite de peticiones.

    :param config: configuracion con las claves por cliente
    :param limiter: limitador de peticiones por cliente
    :return: dependencia de FastAPI que devuelve el nombre del cliente
    """

    def protected(request: Request) -> str:
        """Exige ``X-API-Key`` valida y cuenta la peticion contra el limite.

        :param request: la peticion en curso
        :return: el nombre del cliente
        :raises HTTPException: ``401`` sin clave valida; ``429`` si pasa el limite
        """
        client = find_client(config.api_keys, request.headers.get(API_KEY_HEADER))
        if client is None:
            raise HTTPException(status_code=401, detail=INVALID_KEY_DETAIL)
        request.state.client = client
        wait = limiter.check(client)
        if wait:
            raise HTTPException(
                status_code=429,
                detail="rate limit exceeded",
                headers={"Retry-After": str(wait)},
            )
        return client

    return protected


def _install_observer(app: FastAPI, clock, logger, metrics: Metrics) -> None:
    """Registra el middleware que mide la latencia y registra cada peticion.

    :param app: la aplicacion FastAPI
    :param clock: reloj con ``now()``
    :param logger: logger JSON
    :param metrics: metricas del proceso
    """

    @app.middleware("http")
    async def observe(request: Request, call_next):
        """Fija el id de la peticion, mide la latencia y registra el evento."""
        request_id = _pick_request_id(request.headers.get(REQUEST_ID_HEADER))
        token = request_id_var.set(request_id)
        start = clock.now()
        try:
            try:
                response = await call_next(request)
            except Exception as error:  # pylint: disable=broad-exception-caught
                logger.log(
                    "error",
                    error_type=type(error).__name__,
                    **_client_field(request),
                )
                response = JSONResponse(
                    status_code=500,
                    content={"detail": "internal error", "request_id": request_id},
                )
            latency = elapsed_ms(start, clock.now())
            response.headers[REQUEST_ID_HEADER] = request_id
            logger.log(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                latency_ms=latency,
                **_client_field(request),
            )
            metrics.record_request(latency, response.status_code >= 500)
            return response
        finally:
            request_id_var.reset(token)


def _clean_history(messages: List[HistoryMessage], max_chars: int):
    """Valida el historial y oculta la PII de cada mensaje.

    :param messages: historial que manda el cliente
    :param max_chars: largo maximo de cada mensaje
    :return: el historial limpio y los tipos de PII encontrados
    :raises HTTPException: ``422`` si el historial es demasiado largo
    """
    too_many = len(messages) > MAX_HISTORY_MESSAGES
    too_long = any(len(m.content) > max_chars for m in messages)
    if too_many or too_long:
        raise HTTPException(status_code=422, detail="Invalid history")
    cleaned, found = [], set()
    for message in messages:
        content, kinds = redact(message.content)
        found.update(kinds)
        cleaned.append({"role": message.role, "content": content})
    return cleaned, found


def _validate_input(body: AskRequest, svc: Services):
    """Aplica los guardrails de entrada: largo, historial e inyeccion.

    :param body: cuerpo de la peticion
    :param svc: dependencias de la aplicacion
    :return: pregunta limpia, historial limpio y tipos de PII encontrados
    :raises HTTPException: ``422`` por largo o historial; ``400`` por inyeccion
    """
    question = body.question
    if not question.strip() or len(question) > svc.config.max_question_chars:
        raise HTTPException(status_code=422, detail="Invalid question length")
    history, input_pii = _clean_history(
        body.history or [], svc.config.max_question_chars
    )
    if looks_like_injection(question):
        svc.logger.log("security", action="prompt_injection_blocked")
        raise HTTPException(status_code=400, detail=INJECTION_DETAIL)
    question, kinds = redact(question)
    input_pii.update(kinds)
    return question, history, input_pii


def _model_unavailable(svc: Services, error: Exception) -> JSONResponse:
    """Registra el fallo del modelo y arma la respuesta ``502``.

    :param svc: dependencias de la aplicacion
    :param error: el error que lanzo el modelo
    :return: respuesta ``502`` sin detalles internos
    """
    svc.logger.log("error", error_type=type(error).__name__)
    return JSONResponse(
        status_code=502,
        content={"detail": "model unavailable", "request_id": request_id_var.get()},
    )


def _build_response(result, answer: str, pii: set) -> dict:
    """Arma el cuerpo de la respuesta de ``POST /ask``.

    :param result: resultado del agente
    :param answer: respuesta ya saneada
    :param pii: tipos de PII ocultados en la entrada y la salida
    :return: el cuerpo JSON de la respuesta
    """
    return {
        "answer": answer,
        "steps": result.steps,
        "tools_used": result.tools_used,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "request_id": request_id_var.get(),
        "model": result.model,
        "route": result.route,
        "cached_calls": result.cached_calls,
        "cost_usd": result.cost_usd,
        "pii_redacted": sorted(pii),
    }


def _answer(body: AskRequest, svc: Services):
    """Valida la pregunta, corre el agente y arma la respuesta.

    :param body: cuerpo de la peticion
    :param svc: dependencias de la aplicacion
    :return: el cuerpo de la respuesta, o una respuesta ``502``
    """
    question, history, input_pii = _validate_input(body, svc)
    agent = Agent(
        svc.model,
        svc.directory,
        svc.config.agent_max_steps,
        logger=svc.logger,
        tracer=svc.tracer,
        config=svc.config,
        prices=svc.prices,
    )
    try:
        result = agent.run(question, history)
    except ModelUnavailable as error:
        return _model_unavailable(svc, error)
    svc.metrics.add_tokens(result.input_tokens, result.output_tokens)
    svc.metrics.add_cost(result.cost_usd)
    answer, output_pii = sanitize_output(result.answer, svc.config.max_answer_chars)
    if input_pii or output_pii:
        svc.logger.log(
            "security",
            action="pii_redacted",
            input_types=sorted(input_pii),
            output_types=output_pii,
        )
    return _build_response(result, answer, input_pii.union(output_pii))


def create_app(
    config: Optional[Config] = None,
    model=None,
    directory=None,
    clock=None,
    logger=None,
):
    """Crea la aplicacion con sus dependencias.

    :param config: configuracion (por omision, la del entorno)
    :param model: modelo (por omision, segun ``MODEL_PROVIDER``)
    :param directory: directorio (por omision, el de ``EMPLOYEES_PATH``)
    :param clock: reloj con ``now()`` (por omision, el del sistema)
    :param logger: logger JSON (por omision, uno a la salida estandar)
    :return: la aplicacion FastAPI
    """
    config = config or load_config(os.environ)
    check_compliance(config)
    directory = directory or Directory(config.employees_path)
    prices = load_prices(config.prices_path)
    _check_prices(config, prices)
    model = model or create_model(
        config.model_provider, directory.departments, config
    )
    clock = clock or SystemClock()
    logger = logger or JsonLogger(config.service_name, clock)
    metrics = Metrics()
    svc = Services(
        config, model, directory, logger, _build_tracer(config), prices, metrics
    )
    limiter = RateLimiter(config.rate_limit_per_minute, clock)
    protected = _make_protected(config, limiter)
    app = FastAPI(title="HR Assistant")
    _install_observer(app, clock, logger, metrics)

    @app.get("/")
    def home():
        """Sirve la pagina web."""
        return FileResponse(INDEX_FILE, media_type="text/html")

    @app.get("/health")
    def health():
        """Informa que el proceso esta vivo."""
        return {"status": "ok", "pid": os.getpid()}

    @app.get("/metrics", dependencies=[Depends(protected)])
    def get_metrics():
        """Informa las metricas de este proceso."""
        return metrics.snapshot(config.slo_p95_ms)

    @app.post("/ask")
    def ask(body: AskRequest, client: str = Depends(protected)):
        """Responde una pregunta; no guarda nada entre peticiones."""
        token = client_var.set(client)
        try:
            return _answer(body, svc)
        finally:
            client_var.reset(token)

    return app


app = create_app()
