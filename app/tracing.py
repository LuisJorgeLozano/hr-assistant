"""Trazas opcionales en LangSmith; sin clave no se conecta a nada."""
import functools
from typing import Mapping, Optional


def is_enabled(env: Mapping[str, str]) -> bool:
    """Indica si las trazas estan encendidas y hay clave.

    La clave solo se comprueba; nunca se copia ni se muestra.

    :param env: variables de entorno
    :return: ``True`` si ``LANGSMITH_TRACING`` es ``true`` y hay clave
    """
    flag = env.get("LANGSMITH_TRACING", "").strip().lower() == "true"
    return flag and bool(env.get("LANGSMITH_API_KEY"))


def make_hider(hide: bool):
    """Crea la funcion que oculta entradas o salidas.

    :param hide: si es verdadero, no se manda nada
    :return: funcion que recibe los datos y devuelve lo que se manda
    """

    def _process(data: dict) -> dict:
        return {} if hide else data

    return _process


def _tag_current_run(request_id: str, client: Optional[str] = None) -> None:
    """Agrega el ``request_id`` (y el cliente) a los metadatos de la traza actual.

    :param request_id: id de la peticion
    :param client: nombre del cliente autenticado (nunca su clave)
    """
    try:
        from langsmith.run_helpers import (  # pylint: disable=import-outside-toplevel
            get_current_run_tree,
        )

        run = get_current_run_tree()
        if run is not None:
            run.metadata["request_id"] = request_id
            if client is not None:
                run.metadata["client"] = client
    except Exception:  # pylint: disable=broad-exception-caught
        pass  # una traza fallida nunca debe romper la peticion


def traced(
    name: str,
    enabled: bool = False,
    hide_inputs: bool = True,
    hide_outputs: bool = True,
):
    """Crea un decorador que traza la funcion en LangSmith.

    Si no esta activo devuelve la funcion tal cual, sin tocar la red.

    :param name: nombre de la traza
    :param enabled: si las trazas estan activas
    :param hide_inputs: no mandar las entradas
    :param hide_outputs: no mandar las salidas
    :return: el decorador
    """
    if not enabled:
        return lambda func: func

    def _decorator(func):
        from langsmith import traceable  # pylint: disable=import-outside-toplevel

        from app.observability import (  # pylint: disable=import-outside-toplevel
            client_var,
            request_id_var,
        )

        @functools.wraps(func)
        def _tagged(*args, **kwargs):
            _tag_current_run(request_id_var.get(), client_var.get())
            return func(*args, **kwargs)

        return traceable(
            name=name,
            process_inputs=make_hider(hide_inputs),
            process_outputs=make_hider(hide_outputs),
        )(_tagged)

    return _decorator
