"""Pruebas unitarias del enrutador de modelos."""
import pytest

from conftest import LARGE, SMALL

from app.router import choose_model


@pytest.mark.parametrize(
    "question",
    [
        "Compara Ventas con Finanzas",
        "Resume el equipo de Ventas",
        "Explica quien es EMP-0001",
        "Por qué Ventas es grande?",
        "por que Ventas es grande?",
        "ANALIZA Finanzas",
        "Lista a todos en Ventas",
    ],
)
def test_keywords_send_the_question_to_the_large_model(make_config, question):
    model, route = choose_model(question, make_config())
    assert model == LARGE
    assert route.startswith("keyword:")


def test_keyword_inside_another_word_is_ignored(make_config):
    assert choose_model("Is Todosantos in Ventas?", make_config()) == (
        SMALL,
        "simple",
    )


def test_question_length_limit_is_inclusive(make_config):
    config = make_config(router_max_chars=20)
    assert choose_model("a" * 20, config) == (SMALL, "simple")
    assert choose_model("a" * 21, config) == (LARGE, "too_long")


def test_routing_off_always_uses_the_large_model(make_config):
    config = make_config(routing=False)
    assert choose_model("Hola", config) == (LARGE, "routing_off")
