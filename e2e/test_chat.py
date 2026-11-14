"""Pruebas de punta a punta del chat, con el modelo simulado y con clave."""

import os
import re

import pytest
from playwright.sync_api import Page, expect

FIRST_QUESTION = "How many vacation days does Ana have?"
SECOND_QUESTION = "And what is her email?"
WRONG_KEY = "this-key-is-not-valid"


def ask(page: Page, question: str) -> None:
    """Escribe una pregunta y la envia con el boton."""
    page.get_by_test_id("question").fill(question)
    page.get_by_test_id("send").click()


@pytest.fixture(name="chat")
def chat_fixture(page: Page) -> Page:
    """Abre la pagina y escribe la clave que pone la verificacion."""
    page.goto("/")
    page.get_by_test_id("api-key").fill(os.environ["E2E_API_KEY"])
    return page


def test_question_and_answer_are_shown_after_sending(chat: Page):
    ask(chat, FIRST_QUESTION)
    expect(chat.get_by_test_id("answer")).to_contain_text(FIRST_QUESTION)
    expect(chat.get_by_test_id("answer")).to_contain_text("Herramientas usadas")


def test_request_id_is_shown_after_an_answer(chat: Page):
    expect(chat.get_by_test_id("request-id")).to_have_text("-")
    ask(chat, FIRST_QUESTION)
    expect(chat.get_by_test_id("request-id")).not_to_have_text("-")
    expect(chat.get_by_test_id("request-id")).to_have_text(re.compile(r"\S{8,}"))


def test_input_is_cleared_after_sending(chat: Page):
    ask(chat, FIRST_QUESTION)
    expect(chat.get_by_test_id("question")).to_have_value("")


def test_empty_question_shows_an_error_message_in_spanish(chat: Page):
    ask(chat, "")
    expect(chat.get_by_test_id("error")).to_be_visible()
    expect(chat.get_by_test_id("error")).to_contain_text("pregunta")


def test_second_question_keeps_the_previous_conversation(chat: Page):
    ask(chat, FIRST_QUESTION)
    expect(chat.get_by_test_id("request-id")).not_to_have_text("-")
    first_id = chat.get_by_test_id("request-id").inner_text()
    ask(chat, SECOND_QUESTION)
    expect(chat.get_by_test_id("request-id")).not_to_have_text(first_id)
    expect(chat.get_by_test_id("answer")).to_contain_text(FIRST_QUESTION)
    expect(chat.get_by_test_id("answer")).to_contain_text(SECOND_QUESTION)


def test_wrong_api_key_shows_invalid_key_message(page: Page):
    page.goto("/")
    page.get_by_test_id("api-key").fill(WRONG_KEY)
    ask(page, FIRST_QUESTION)
    expect(page.get_by_test_id("error")).to_contain_text("Clave inválida")
