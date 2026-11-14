"""API web sin estado del HR Assistant."""
import functools
import os
import re
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.agent import Agent
from app.auth import API_KEY_HEADER, INVALID_KEY_DETAIL, find_client
from app.compliance import check_compliance
from app.config import Config, ConfigError, load_config
from app.directory import Directory
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


class HistoryMessage(BaseModel):
    """Mensaje previo de la conversacion."""

    role: str
    content: str


class AskRequest(BaseModel):
    """Cuerpo de ``POST /ask``."""

    question: str
    history: Optional[List[HistoryMessage]] = None


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


def create_app(  # pylint: disable=too-many-locals
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
    for name in (config.model_small, config.model_large):
        if not prices.has(name):
            raise ConfigError(f"No price for model {name!r}")
    model = model or create_model(
        config.model_provider, directory.departments, config
    )
    clock = clock or SystemClock()
    logger = logger or JsonLogger(config.service_name, clock)
    metrics = Metrics()
    tracing_on = config.langsmith_tracing and bool(
        os.environ.get("LANGSMITH_API_KEY")
    )
    tracer = functools.partial(
        traced,
        enabled=tracing_on,
        hide_inputs=config.hide_inputs,
        hide_outputs=config.hide_outputs,
    )
    limiter = RateLimiter(config.rate_limit_per_minute, clock)
    app = FastAPI(title="HR Assistant")

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
            return _answer(body)
        finally:
            client_var.reset(token)

    def _answer(body: AskRequest):
        """Valida la pregunta, corre el agente y arma la respuesta."""
        question = body.question
        if not question.strip() or len(question) > config.max_question_chars:
            raise HTTPException(status_code=422, detail="Invalid question length")
        history = [m.model_dump() for m in body.history or []]
        agent = Agent(
            model,
            directory,
            config.agent_max_steps,
            logger=logger,
            tracer=tracer,
            config=config,
            prices=prices,
        )
        try:
            result = agent.run(question, history)
        except ModelUnavailable as error:
            logger.log("error", error_type=type(error).__name__)
            return JSONResponse(
                status_code=502,
                content={
                    "detail": "model unavailable",
                    "request_id": request_id_var.get(),
                },
            )
        metrics.add_tokens(result.input_tokens, result.output_tokens)
        metrics.add_cost(result.cost_usd)
        return {
            "answer": result.answer,
            "steps": result.steps,
            "tools_used": result.tools_used,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "request_id": request_id_var.get(),
            "model": result.model,
            "route": result.route,
            "cached_calls": result.cached_calls,
            "cost_usd": result.cost_usd,
        }

    return app


app = create_app()
