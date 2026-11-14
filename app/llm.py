"""Interfaz del modelo y modelo simulado determinista."""
import json
import re
from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

import httpx

from app.directory import normalize

REQUEST_TIMEOUT_SECONDS = 30.0
TOOL_RESULT_PREFIX = "Resultado de la herramienta: "
GUIDANCE = "Pregúntame por un empleado (EMP-0001) o un departamento."
EMPLOYEE_ID = re.compile(r"\bEMP-\d{4}\b")


@dataclass(frozen=True)
class Completion:
    """Respuesta de un modelo.

    :param text: objeto JSON como texto
    :param input_tokens: tokens de entrada (aproximados)
    :param output_tokens: tokens de salida (aproximados)
    :param model: nombre del modelo que respondio
    :param cached: si el gateway respondio desde su cache
    """

    text: str
    input_tokens: int
    output_tokens: int
    model: Optional[str] = None
    cached: bool = False


class ModelUnavailable(Exception):
    """El modelo real no respondio o respondio algo inutilizable."""


class Model(Protocol):
    """Interfaz que el agente usa para hablar con cualquier modelo."""

    def complete(
        self, messages: Sequence[dict], model: Optional[str] = None
    ) -> Completion:
        """Responde a una conversacion.

        :param messages: mensajes con ``role`` y ``content``
        :param model: nombre del modelo que debe responder
        :return: la respuesta del modelo
        """


class GatewayModel:
    """Modelo real: Workers AI a traves de AI Gateway de Cloudflare.

    :param config: configuracion con las variables ``CF_*`` y las palancas
    :param client: cliente ``httpx.Client`` (por omision, uno nuevo)
    """

    def __init__(self, config, client=None):
        self._config = config
        self._client = client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)

    def _url(self) -> str:
        """Arma la URL del gateway.

        :return: la URL de chat completions
        """
        return (
            "https://gateway.ai.cloudflare.com/v1/"
            f"{self._config.cf_account_id}/{self._config.cf_gateway_id}/"
            "workers-ai/v1/chat/completions"
        )

    def complete(
        self, messages: Sequence[dict], model: Optional[str] = None
    ) -> Completion:
        """Llama al gateway.

        :param messages: mensajes con ``role`` y ``content``
        :param model: modelo a usar (por omision, ``MODEL_LARGE``)
        :return: la respuesta con los tokens que informa el gateway
        :raises ModelUnavailable: ante cualquier falla de red, HTTP o formato
        """
        config = self._config
        model = model or config.model_large
        headers = {"Authorization": f"Bearer {config.cf_api_token}"}
        if config.cache_ttl_seconds > 0:
            headers["cf-aig-cache-ttl"] = str(config.cache_ttl_seconds)
        body = {
            "model": model,
            "messages": list(messages),
            "max_tokens": config.model_max_tokens,
            "temperature": config.model_temperature,
            "response_format": {"type": "json_object"},
        }
        try:
            response = self._client.post(self._url(), json=body, headers=headers)
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            usage = data["usage"]
            input_tokens = int(usage["prompt_tokens"])
            output_tokens = int(usage["completion_tokens"])
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
            raise ModelUnavailable(type(error).__name__) from None
        status = response.headers.get("cf-aig-cache-status", "")
        return Completion(
            text,
            input_tokens,
            output_tokens,
            model=model,
            cached=status.upper() == "HIT",
        )


class FakeModel:
    """Modelo simulado: reglas fijas, sin red; responde igual con cualquier nombre.

    :param departments: departamentos que existen en los datos
    """

    def __init__(self, departments: Sequence[str]):
        self._departments = list(departments)

    def complete(
        self, messages: Sequence[dict], model: Optional[str] = None
    ) -> Completion:
        """Decide con reglas sobre el ultimo mensaje.

        :param messages: mensajes con ``role`` y ``content``
        :param model: nombre del modelo simulado (solo se devuelve)
        :return: la respuesta con conteo aproximado de tokens
        """
        reply = self._decide(messages[-1]["content"])
        text = json.dumps(reply, ensure_ascii=False)
        input_tokens = sum(len(m["content"].split()) for m in messages)
        output_tokens = len(reply["answer"].split()) if "answer" in reply else len(
            text.split()
        )
        return Completion(text, input_tokens, output_tokens, model=model)

    def _decide(self, content: str) -> dict:
        """Aplica las reglas en orden.

        :param content: texto del ultimo mensaje
        :return: objeto de herramienta o de respuesta
        """
        if content.startswith(TOOL_RESULT_PREFIX):
            result = content[len(TOOL_RESULT_PREFIX):]
            return {"answer": f"Según el directorio: {result}"}
        found = EMPLOYEE_ID.search(content)
        if found:
            return {"tool": "get_employee", "args": {"employee_id": found.group()}}
        text = normalize(content)
        for department in self._departments:
            if normalize(department) in text:
                return {
                    "tool": "search_by_department",
                    "args": {"department": department},
                }
        return {"answer": GUIDANCE}


def create_model(
    provider: str, departments: Sequence[str], config=None
) -> Model:
    """Crea el modelo segun el proveedor.

    :param provider: nombre del proveedor (``fake`` o ``gateway``)
    :param departments: departamentos que existen en los datos
    :param config: configuracion (obligatoria con ``gateway``)
    :return: el modelo
    :raises ValueError: si el proveedor es desconocido
    """
    if provider == "fake":
        return FakeModel(departments)
    if provider == "gateway" and config is not None:
        return GatewayModel(config)
    raise ValueError(f"Unknown MODEL_PROVIDER: {provider!r}")
