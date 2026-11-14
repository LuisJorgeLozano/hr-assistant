"""Acceso por clave: valida ``X-API-Key`` y devuelve el nombre del cliente."""
import hmac
from typing import Mapping, Optional

API_KEY_HEADER = "X-API-Key"
INVALID_KEY_DETAIL = "invalid or missing API key"


def find_client(
    api_keys: Mapping[str, str], candidate: Optional[str]
) -> Optional[str]:
    """Busca el cliente dueno de una clave, comparando en tiempo constante.

    Revisa todas las entradas sin cortar al primer acierto, para que el tiempo
    no revele cuantos clientes hay ni cual coincidio.

    :param api_keys: mapa de cliente a clave
    :param candidate: valor del encabezado (puede faltar)
    :return: el nombre del cliente, o ``None`` si la clave no es valida
    """
    if not candidate:
        return None
    given = candidate.encode("utf-8")
    found = None
    for client, key in api_keys.items():
        if hmac.compare_digest(given, key.encode("utf-8")):
            found = client
    return found
