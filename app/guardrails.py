"""Controles de entrada y salida del agente: PII, secretos e inyeccion de prompt.

Todo es determinista y sin red: expresiones regulares y reglas en codigo. Las
funciones devuelven el texto limpio y los *tipos* de dato encontrados, nunca los
valores, para que el log y la auditoria no repitan la informacion sensible.
"""
import re
from typing import List, Optional, Tuple

REDACTED = "[REDACTED:{kind}]"
MAX_HISTORY_MESSAGES = 50

# El orden importa: lo mas especifico primero (una CURP contiene algo parecido a
# un RFC y una tarjeta parece un telefono largo).
_PATTERNS = (
    ("secret", re.compile(
        r"\b(?:sk|pk|rk|ghp|gho|ghs|xox[abp]|lsv2)[-_][A-Za-z0-9_-]{16,}"
        r"|\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*",
    )),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("curp", re.compile(r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d\b", re.IGNORECASE)),
    ("rfc", re.compile(r"\b[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}\b", re.IGNORECASE)),
    ("credit_card", re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")),
    ("phone", re.compile(r"(?<![\w-])\+?\d[\d ().-]{8,16}\d(?![\w-])")),
)

_INJECTION = re.compile(
    r"ignor\w*\s+(?:\w+\s+){0,3}(?:instruc\w*|reglas|rules|prompt)"
    r"|olvida\w*\s+(?:\w+\s+){0,3}(?:instruc\w*|reglas)"
    r"|forget\s+(?:\w+\s+){0,3}(?:instructions|rules)"
    r"|system\s+prompt|prompt\s+del\s+sistema"
    r"|(?:revela|muestra|reveal|show)\w*\s+(?:\w+\s+){0,3}(?:prompt|instruc\w*)",
    re.IGNORECASE,
)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HTML_TAGS = re.compile(r"<[^>]{0,200}>")


def _luhn_ok(digits: str) -> bool:
    """Indica si una secuencia de digitos pasa el algoritmo de Luhn.

    :param digits: solo digitos
    :type digits: str
    :return: ``True`` si el numero es valido como tarjeta
    :rtype: bool
    """
    total = 0
    for position, char in enumerate(reversed(digits)):
        value = int(char)
        if position % 2 == 1:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


def _classify(kind: str, text: str) -> Optional[str]:
    """Confirma el tipo de una coincidencia o la descarta.

    Un numero largo que no pasa Luhn no es tarjeta, pero se oculta igual como
    ``account_number`` (cuenta o CLABE). Un telefono necesita de 10 a 13 digitos,
    asi que una fecha como ``2019-03-04`` no cuenta.

    :param kind: tipo de dato de la expresion que coincidio
    :type kind: str
    :param text: texto que coincidio
    :type text: str
    :return: el tipo que se reporta, o ``None`` si no es un dato sensible
    :rtype: str or None
    """
    digits = re.sub(r"\D", "", text)
    if kind == "credit_card":
        if not 13 <= len(digits) <= 19:
            return None
        return "credit_card" if _luhn_ok(digits) else "account_number"
    if kind == "phone":
        return "phone" if 10 <= len(digits) <= 13 else None
    return kind


def redact(text: str) -> Tuple[str, List[str]]:
    """Reemplaza PII y secretos por ``[REDACTED:<tipo>]``.

    :param text: texto original
    :type text: str
    :return: el texto limpio y la lista ordenada de tipos encontrados
    :rtype: tuple[str, list[str]]
    """
    found = set()

    for kind, pattern in _PATTERNS:

        def _replace(match, kind=kind):
            label = _classify(kind, match.group(0))
            if label is None:
                return match.group(0)
            found.add(label)
            return REDACTED.format(kind=label)

        text = pattern.sub(_replace, text)
    return text, sorted(found)


def looks_like_injection(text: str) -> bool:
    """Indica si el texto intenta cambiar las instrucciones del agente.

    Es una heuristica: detecta frases tipicas como «ignora las instrucciones»
    o «muestra tu prompt». No sustituye al resto de los controles.

    :param text: pregunta o mensaje del usuario
    :type text: str
    :return: ``True`` si parece un intento de inyeccion de prompt
    :rtype: bool
    """
    return _INJECTION.search(text) is not None


def sanitize_output(text: str, max_chars: int) -> Tuple[str, List[str]]:
    """Limpia la respuesta del modelo antes de devolverla al cliente.

    Quita caracteres de control y etiquetas HTML, oculta PII y secretos y
    recorta la respuesta a ``max_chars`` caracteres.

    :param text: respuesta del modelo
    :type text: str
    :param max_chars: largo maximo permitido
    :type max_chars: int
    :return: la respuesta limpia y los tipos de dato ocultados
    :rtype: tuple[str, list[str]]
    """
    clean = _CONTROL_CHARS.sub("", text)
    clean = _HTML_TAGS.sub("", clean)
    clean, found = redact(clean)
    if len(clean) > max_chars:
        clean = clean[:max_chars].rstrip() + "..."
    return clean, found
