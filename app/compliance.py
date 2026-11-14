"""Reglas de compliance que impiden arrancar en produccion con un setup inseguro."""
from app.config import Config, ConfigError

MIN_KEY_LENGTH = 16


def check_compliance(config: Config) -> None:
    """Revisa las reglas de produccion y junta todas las faltas en un error.

    Con ``environment`` distinto de ``production`` no bloquea nada. Los mensajes
    nombran la regla, nunca un valor (y menos una clave).

    :param config: configuracion ya validada
    :raises ConfigError: si alguna regla de produccion no se cumple
    """
    if config.environment != "production":
        return
    problems = []
    if config.model_provider == "fake":
        problems.append("MODEL_PROVIDER must not be fake in production")
    if not config.api_keys:
        problems.append("API_KEYS must not be empty in production")
    elif any(len(key) < MIN_KEY_LENGTH for key in config.api_keys.values()):
        problems.append(
            f"API_KEYS: every key must have at least {MIN_KEY_LENGTH} characters"
        )
    if config.langsmith_tracing:
        if not config.hide_inputs:
            problems.append("HIDE_INPUTS must be true when tracing is on")
        if not config.hide_outputs:
            problems.append("HIDE_OUTPUTS must be true when tracing is on")
    if problems:
        raise ConfigError("Unsafe production setup: " + "; ".join(problems))
