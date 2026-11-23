"""Lectura y validacion de la configuracion desde variables de entorno."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_EMPLOYEES_PATH = DATA_DIR / "employees.json"
DEFAULT_PRICES_PATH = DATA_DIR / "model_prices.json"
DEFAULT_MODEL_SMALL = "@cf/meta/llama-3.1-8b-instruct-fast"
DEFAULT_MODEL_LARGE = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
GATEWAY_VARIABLES = ("CF_ACCOUNT_ID", "CF_GATEWAY_ID", "CF_API_TOKEN")


class ConfigError(ValueError):
    """Configuracion invalida: impide arrancar la aplicacion."""


@dataclass(frozen=True)
class Config:  # pylint: disable=too-many-instance-attributes
    """Configuracion de la aplicacion.

    :param model_provider: nombre del modelo a usar
    :param agent_max_steps: tope de vueltas del bucle del agente
    :param max_question_chars: largo maximo de la pregunta
    :param employees_path: ruta del archivo de empleados
    :param service_name: valor del campo ``service`` del log
    :param slo_p95_ms: meta de latencia p95 en milisegundos
    :param langsmith_tracing: si las trazas de LangSmith estan encendidas
    :param hide_inputs: no mandar a LangSmith las entradas
    :param hide_outputs: no mandar a LangSmith las salidas
    :param environment: ``production`` activa las reglas de compliance
    :param api_keys: mapa de cliente a clave (nunca se muestra en ``repr``)
    :param rate_limit_per_minute: peticiones por cliente por minuto
    :param max_answer_chars: largo maximo de la respuesta que se devuelve
    """

    model_provider: str
    agent_max_steps: int
    max_question_chars: int
    employees_path: Path
    service_name: str = "hr-assistant"
    slo_p95_ms: int = 2000
    langsmith_tracing: bool = False
    hide_inputs: bool = True
    hide_outputs: bool = True
    cf_account_id: str = ""
    cf_gateway_id: str = "default"
    cf_api_token: str = field(default="", repr=False)
    model_small: str = DEFAULT_MODEL_SMALL
    model_large: str = DEFAULT_MODEL_LARGE
    routing: bool = True
    router_max_chars: int = 80
    history_window: int = 6
    model_max_tokens: int = 300
    model_temperature: float = 0
    cache_ttl_seconds: int = 0
    prices_path: Path = DEFAULT_PRICES_PATH
    environment: str = "development"
    api_keys: Dict[str, str] = field(default_factory=dict, repr=False)
    rate_limit_per_minute: int = 30
    max_answer_chars: int = 4000


def parse_api_keys(raw: str) -> Dict[str, str]:
    """Convierte ``cliente:clave,cliente2:clave2`` en un mapa cliente a clave.

    Los mensajes de error dicen la posicion de la entrada (desde 1) y su largo,
    nunca su valor.

    :param raw: valor de la variable ``API_KEYS``
    :return: mapa de nombre de cliente a clave (vacio si ``raw`` esta vacio)
    :raises ConfigError: si alguna entrada esta mal formada o un cliente se repite
    """
    keys: Dict[str, str] = {}
    if not raw.strip():
        return keys
    for number, entry in enumerate(raw.split(","), start=1):
        client, separator, key = entry.partition(":")
        client, key = client.strip(), key.strip()
        if not separator or not client or not key:
            raise ConfigError(
                f"API_KEYS entry {number} is malformed (length {len(entry.strip())});"
                " expected client:key"
            )
        if client in keys:
            raise ConfigError(
                f"API_KEYS entry {number} repeats a client name"
                f" (length {len(entry.strip())})"
            )
        keys[client] = key
    return keys


def _non_negative_int(env: Mapping[str, str], name: str, default: int) -> int:
    """Lee un entero mayor o igual que cero del entorno.

    :param env: variables de entorno
    :param name: nombre de la variable
    :param default: valor si la variable no existe
    :return: el entero validado
    :raises ConfigError: si no es un entero mayor o igual que cero
    """
    if name not in env:
        return default
    raw = env[name]
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from error
    if value < 0:
        raise ConfigError(f"{name} must be 0 or greater, got {value}")
    return value


def _number(env: Mapping[str, str], name: str, default: float) -> float:
    """Lee un numero del entorno.

    :param env: variables de entorno
    :param name: nombre de la variable
    :param default: valor si la variable no existe
    :return: el numero validado
    :raises ConfigError: si no es un numero
    """
    if name not in env:
        return default
    try:
        return float(env[name])
    except ValueError as error:
        raise ConfigError(f"{name} must be a number, got {env[name]!r}") from error


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    """Lee un entero positivo del entorno.

    :param env: variables de entorno
    :param name: nombre de la variable
    :param default: valor si la variable no existe
    :return: el entero validado
    :raises ConfigError: si no es un entero mayor que cero
    """
    if name not in env:
        return default
    raw = env[name]
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from error
    if value < 1:
        raise ConfigError(f"{name} must be greater than 0, got {value}")
    return value


def _boolean(env: Mapping[str, str], name: str, default: bool) -> bool:
    """Lee un booleano (``true`` o ``false``) del entorno.

    :param env: variables de entorno
    :param name: nombre de la variable
    :param default: valor si la variable no existe
    :return: el booleano validado
    :raises ConfigError: si el valor no es ``true`` ni ``false``
    """
    if name not in env:
        return default
    raw = env[name].strip().lower()
    if raw not in ("true", "false"):
        raise ConfigError(f"{name} must be true or false, got {env[name]!r}")
    return raw == "true"


def load_config(env: Mapping[str, str]) -> Config:
    """Construye la configuracion a partir del entorno.

    :param env: variables de entorno
    :return: la configuracion validada
    :raises ConfigError: si algun valor es invalido
    """
    path = env.get("EMPLOYEES_PATH")
    prices = env.get("PRICES_PATH")
    provider = env.get("MODEL_PROVIDER", "fake")
    if provider == "gateway":
        for name in GATEWAY_VARIABLES:
            if not env.get(name):
                raise ConfigError(f"{name} is required when MODEL_PROVIDER=gateway")
    return Config(
        model_provider=provider,
        agent_max_steps=_positive_int(env, "AGENT_MAX_STEPS", 3),
        max_question_chars=_positive_int(env, "MAX_QUESTION_CHARS", 2000),
        employees_path=Path(path) if path else DEFAULT_EMPLOYEES_PATH,
        service_name=env.get("SERVICE_NAME") or "hr-assistant",
        slo_p95_ms=_positive_int(env, "SLO_P95_MS", 2000),
        langsmith_tracing=_boolean(env, "LANGSMITH_TRACING", False),
        hide_inputs=_boolean(env, "HIDE_INPUTS", True),
        hide_outputs=_boolean(env, "HIDE_OUTPUTS", True),
        cf_account_id=env.get("CF_ACCOUNT_ID", ""),
        cf_gateway_id=env.get("CF_GATEWAY_ID") or "default",
        cf_api_token=env.get("CF_API_TOKEN", ""),
        model_small=env.get("MODEL_SMALL") or DEFAULT_MODEL_SMALL,
        model_large=env.get("MODEL_LARGE") or DEFAULT_MODEL_LARGE,
        routing=_boolean(env, "ROUTING", True),
        router_max_chars=_positive_int(env, "ROUTER_MAX_CHARS", 80),
        history_window=_non_negative_int(env, "HISTORY_WINDOW", 6),
        model_max_tokens=_positive_int(env, "MODEL_MAX_TOKENS", 300),
        model_temperature=_number(env, "MODEL_TEMPERATURE", 0),
        cache_ttl_seconds=_non_negative_int(env, "CACHE_TTL_SECONDS", 0),
        prices_path=Path(prices) if prices else DEFAULT_PRICES_PATH,
        environment=(env.get("ENVIRONMENT") or "development").strip().lower(),
        api_keys=parse_api_keys(env.get("API_KEYS", "")),
        rate_limit_per_minute=_positive_int(env, "RATE_LIMIT_PER_MINUTE", 30),
        max_answer_chars=_positive_int(env, "MAX_ANSWER_CHARS", 4000),
    )
