"""Pruebas unitarias de las trazas opcionales de LangSmith."""
from app import tracing
from app.config import load_config

SECRET_KEY = "ls-key-should-never-appear"


def test_tracing_is_off_without_the_key_or_the_flag():
    assert tracing.is_enabled({}) is False
    assert tracing.is_enabled({"LANGSMITH_TRACING": "true"}) is False
    assert tracing.is_enabled({"LANGSMITH_API_KEY": SECRET_KEY}) is False
    on = {"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": SECRET_KEY}
    assert tracing.is_enabled(on) is True


def test_disabled_tracing_leaves_the_function_untouched():
    def work(value):
        return value + 1

    assert tracing.traced("work", enabled=False)(work) is work
    assert work(1) == 2


def test_hiding_removes_the_data_sent_to_langsmith():
    data = {"question": "private text"}
    assert not tracing.make_hider(True)(data)
    assert tracing.make_hider(False)(data) == data


def test_the_api_key_is_never_printed_or_stored_in_the_config(capsys):
    env = {"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": SECRET_KEY}
    tracing.is_enabled(env)
    config = load_config(env)
    output = capsys.readouterr()
    assert SECRET_KEY not in output.out + output.err
    assert SECRET_KEY not in repr(config)
