"""Agente con bucle acotado: el modelo pide herramientas o responde."""
import json
import re
from dataclasses import dataclass, field

from app.config import load_config
from app.directory import normalize
from app.llm import TOOL_RESULT_PREFIX
from app.observability import NullLogger
from app.router import choose_model

EMPLOYEE_ID_PATTERN = re.compile(r"EMP-\d{4}")
LIMIT_MESSAGE = "No pude completar la respuesta. Intenta con una pregunta más concreta."
SYSTEM_PROMPT = (
    "Eres el HR Assistant. Responde siempre con un único objeto JSON, sin texto "
    "adicional ni cercas de código. Formatos permitidos: "
    '{"tool": "<nombre>", "args": {...}} para pedir una herramienta, o '
    '{"answer": "<texto>"} para responder al usuario. '
    "Herramientas disponibles: "
    'get_employee(employee_id) busca un empleado por id (por ejemplo EMP-0001), '
    "y search_by_department(department) lista los empleados de un departamento. "
    f"Cuando recibas un mensaje que empiece con '{TOOL_RESULT_PREFIX}...', "
    "usa ese resultado para dar la respuesta final con "
    '{"answer": "..."}.'
)


@dataclass
class AgentResult:  # pylint: disable=too-many-instance-attributes
    """Resultado de una ejecucion del agente.

    :param answer: respuesta final
    :param steps: vueltas del bucle usadas
    :param tools_used: herramientas pedidas, en orden
    :param input_tokens: tokens de entrada acumulados
    :param output_tokens: tokens de salida acumulados
    :param model: modelo elegido por el enrutador
    :param route: motivo de la eleccion del enrutador
    :param cached_calls: llamadas respondidas desde la cache del gateway
    :param cost_usd: costo en USD de la respuesta
    """

    answer: str
    steps: int = 0
    tools_used: list = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    route: str = ""
    cached_calls: int = 0
    cost_usd: float = 0.0


class Agent:  # pylint: disable=too-many-instance-attributes
    """Agente con dos herramientas de solo lectura.

    :param model: objeto con ``complete(messages, model)``
    :param directory: directorio de empleados
    :param max_steps: tope de vueltas
    :param logger: objeto con ``log(event, **fields)`` (por omision, ninguno)
    :param tracer: funcion ``tracer(name)`` que devuelve un decorador de traza
    :param config: configuracion de las palancas (por omision, la de fabrica)
    :param prices: tabla de precios (por omision, el costo es 0)
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        model,
        directory,
        max_steps: int,
        logger=None,
        tracer=None,
        config=None,
        prices=None,
    ):
        self._directory = directory
        self._max_steps = max_steps
        self._logger = logger or NullLogger()
        self._config = config or load_config({})
        self._prices = prices
        trace = tracer or (lambda name: lambda func: func)

        def call_model(messages, model_name):
            return model.complete(messages, model_name)

        self._complete = trace("model_call")(call_model)
        get_employee = trace("tool:get_employee")(self._get_employee)
        search = trace("tool:search_by_department")(directory.search_by_department)
        self._tools = {
            "get_employee": ("employee_id", get_employee),
            "search_by_department": ("department", search),
        }
        self._traced_run = trace("agent_run")(self._run)

    def run(self, question: str, history=None) -> AgentResult:
        """Responde una pregunta.

        :param question: pregunta del usuario
        :param history: mensajes previos enviados por el cliente
        :return: el resultado con respuesta, pasos, herramientas y tokens
        """
        return self._traced_run(question, history)

    def _run(self, question: str, history) -> AgentResult:
        """Ejecuta el bucle acotado y registra el evento ``agent_run``.

        :param question: pregunta del usuario
        :param history: mensajes previos enviados por el cliente
        :return: el resultado con respuesta, pasos, herramientas y tokens
        """
        window = self._config.history_window
        kept = list(history or [])
        kept = kept[len(kept) - window:] if window < len(kept) else kept
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(dict(m) for m in kept)
        messages.append({"role": "user", "content": question})
        model_name, route = choose_model(question, self._config)
        result = AgentResult(answer=LIMIT_MESSAGE, model=model_name, route=route)
        stopped = True
        for _ in range(self._max_steps):
            completion = self._complete(messages, model_name)
            result.steps += 1
            result.input_tokens += completion.input_tokens
            result.output_tokens += completion.output_tokens
            self._add_cost(result, completion)
            reply = self._parse(completion.text)
            if isinstance(reply, dict) and isinstance(reply.get("answer"), str):
                result.answer = reply["answer"]
                stopped = False
                break
            feedback = self._use_tool(reply, result)
            messages.append({"role": "assistant", "content": completion.text})
            messages.append(
                {"role": "user", "content": TOOL_RESULT_PREFIX + feedback}
            )
        self._logger.log(
            "agent_run",
            question_chars=len(question),
            history_messages=len(history or []),
            steps=result.steps,
            tools=list(result.tools_used),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            stopped=stopped,
            model=result.model,
            route=result.route,
            cached_calls=result.cached_calls,
            cost_usd=result.cost_usd,
        )
        return result

    def _add_cost(self, result: AgentResult, completion) -> None:
        """Suma el costo de una llamada al modelo.

        :param result: resultado en curso
        :param completion: respuesta del modelo
        """
        if completion.cached:
            result.cached_calls += 1
        if self._prices is not None:
            result.cost_usd += self._prices.cost(
                result.model,
                completion.input_tokens,
                completion.output_tokens,
                completion.cached,
            )

    @staticmethod
    def _parse(text: str):
        """Interpreta el JSON del modelo.

        :param text: salida del modelo
        :return: el objeto o ``None`` si no es JSON valido
        """
        if not isinstance(text, str):
            return None
        decoder = json.JSONDecoder()
        position = text.find("{")
        while position != -1:
            try:
                value, _ = decoder.raw_decode(text, position)
            except ValueError:
                position = text.find("{", position + 1)
                continue
            if isinstance(value, dict):
                return value
            position = text.find("{", position + 1)
        try:
            return json.loads(text)
        except ValueError:
            return None

    def _use_tool(self, reply, result: AgentResult) -> str:
        """Ejecuta la herramienta pedida o describe el error.

        :param reply: objeto interpretado del modelo
        :param result: resultado en curso (registra la herramienta)
        :return: texto JSON con el resultado o el error
        """
        if not isinstance(reply, dict) or "tool" not in reply:
            return self._dump({"error": "Invalid model output"})
        name = reply["tool"]
        args = reply.get("args")
        if not isinstance(args, dict):
            args = {}
        if not isinstance(name, str) or name not in self._tools:
            return self._dump({"error": f"Unknown tool: {name}"})
        arg_key, tool = self._tools[name]
        value = args.get(arg_key)
        if not isinstance(value, str):
            return self._dump({"error": f"Invalid arguments for {name}"})
        self._audit(name, arg_key, value)
        try:
            output = tool(value)
        except (KeyError, TypeError, AttributeError):
            return self._dump({"error": f"Invalid arguments for {name}"})
        result.tools_used.append(name)
        return self._dump(output)

    def _audit(self, name: str, arg_key: str, value: str) -> None:
        """Deja constancia de una herramienta llamada.

        Solo registra el argumento si tiene la forma esperada (un id con el
        patron ``EMP-dddd`` o un departamento conocido); si no, solo el nombre.

        :param name: nombre de la herramienta
        :param arg_key: nombre del argumento de la herramienta
        :param value: argumento pedido por el modelo (nunca las salidas)
        """
        if self._is_expected(arg_key, value):
            fields = {"args": {arg_key: value}}
        else:
            fields = {}
        self._logger.log("audit", action="tool_call", tool=name, **fields)

    def _is_expected(self, arg_key: str, value: str) -> bool:
        """Dice si un argumento tiene la forma esperada y es seguro registrarlo.

        :param arg_key: nombre del argumento
        :param value: valor pedido por el modelo
        :return: ``True`` si es un id valido o un departamento conocido
        """
        if arg_key == "employee_id":
            return EMPLOYEE_ID_PATTERN.fullmatch(value) is not None
        known = {normalize(d) for d in self._directory.departments}
        return normalize(value) in known

    def _get_employee(self, employee_id):
        """Busca un empleado o describe que no existe.

        :param employee_id: id del empleado
        :return: el empleado o un diccionario de error
        """
        employee = self._directory.get_employee(employee_id)
        if employee is None:
            return {"error": f"Employee {employee_id} not found"}
        return employee

    @staticmethod
    def _dump(value) -> str:
        """Serializa a JSON conservando los acentos.

        :param value: valor serializable
        :return: texto JSON
        """
        return json.dumps(value, ensure_ascii=False)
