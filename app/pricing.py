"""Tabla de precios por modelo y costo por respuesta."""
import json
from pathlib import Path

from app.config import ConfigError

TOKENS_PER_PRICE_UNIT = 1_000_000


class Prices:
    """Precios en USD por millon de tokens.

    :param models: diccionario ``modelo -> {"input": x, "output": y}``
    """

    def __init__(self, models: dict):
        self._models = models

    def has(self, model: str) -> bool:
        """Indica si el modelo tiene precio.

        :param model: nombre del modelo
        :return: ``True`` si existe en la tabla
        """
        return model in self._models

    def cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached: bool = False,
    ) -> float:
        """Calcula el costo de una llamada.

        :param model: nombre del modelo
        :param input_tokens: tokens de entrada
        :param output_tokens: tokens de salida
        :param cached: si la llamada vino de la cache (no cuesta)
        :return: el costo en USD
        :raises ConfigError: si el modelo no tiene precio
        """
        if cached:
            return 0.0
        if model not in self._models:
            raise ConfigError(f"No price for model {model!r}")
        price = self._models[model]
        total = input_tokens * price["input"] + output_tokens * price["output"]
        return total / TOKENS_PER_PRICE_UNIT


def load_prices(path) -> Prices:
    """Carga la tabla de precios de un archivo JSON.

    :param path: ruta del archivo
    :return: los precios
    :raises ConfigError: si el archivo falta o no tiene el formato esperado
    """
    try:
        with open(Path(path), encoding="utf-8") as handle:
            models = json.load(handle)["models"]
        for price in models.values():
            float(price["input"])
            float(price["output"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise ConfigError(f"Invalid prices file {path}") from error
    return Prices(models)
