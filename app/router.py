"""Enrutador de modelos: una regla en codigo, no otro modelo."""
import re

from app.directory import normalize

KEYWORDS = ("compara", "resume", "explica", "por qué", "analiza", "todos")
_PATTERNS = [
    (word, re.compile(r"\b" + re.escape(normalize(word)) + r"\b"))
    for word in KEYWORDS
]


def choose_model(question: str, config) -> tuple:
    """Elige el modelo para una pregunta.

    :param question: pregunta del usuario
    :param config: configuracion con ``routing``, ``router_max_chars``,
        ``model_small`` y ``model_large``
    :return: tupla ``(modelo, motivo)``
    """
    if not config.routing:
        return config.model_large, "routing_off"
    if len(question) > config.router_max_chars:
        return config.model_large, "too_long"
    text = normalize(question)
    for word, pattern in _PATTERNS:
        if pattern.search(text):
            return config.model_large, f"keyword:{word}"
    return config.model_small, "simple"
