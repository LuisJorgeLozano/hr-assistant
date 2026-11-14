"""Pruebas unitarias del modelo simulado."""
import json

import pytest
from conftest import DEPARTMENTS

from app.llm import FakeModel, create_model


def ask(text):
    model = FakeModel(DEPARTMENTS)
    completion = model.complete([{"role": "user", "content": text}])
    return json.loads(completion.text)


def test_employee_id_requests_get_employee():
    assert ask("What is EMP-0002 doing?") == {
        "tool": "get_employee",
        "args": {"employee_id": "EMP-0002"},
    }


def test_employee_id_wins_over_department():
    assert ask("EMP-0001 or Ventas?")["tool"] == "get_employee"


def test_department_requests_search_by_department():
    reply = ask("Who is in Finanzas?")
    assert reply["tool"] == "search_by_department"
    assert reply["args"]["department"] == "Finanzas"


def test_tool_result_is_turned_into_an_answer():
    reply = ask("Resultado de la herramienta: {}")
    assert reply == {"answer": "Según el directorio: {}"}


@pytest.mark.parametrize("text", ["hello", "EMP-12", "EMP-ABCD"])
def test_malformed_id_falls_back_to_guidance(text):
    expected = "Pregúntame por un empleado (EMP-0001) o un departamento."
    assert ask(text) == {"answer": expected}


def test_tokens_are_counted_as_words():
    model = FakeModel(DEPARTMENTS)
    messages = [
        {"role": "user", "content": "one two"},
        {"role": "assistant", "content": "three"},
        {"role": "user", "content": "hello"},
    ]
    completion = model.complete(messages)
    assert completion.input_tokens == 4
    answer = json.loads(completion.text)["answer"]
    assert completion.output_tokens == len(answer.split())


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="nope"):
        create_model("nope", DEPARTMENTS)
