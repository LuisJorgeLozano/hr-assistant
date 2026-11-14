"""Pruebas unitarias de la tabla de precios."""
import pytest

from conftest import LARGE, PRICES_FILE, SMALL

from app.config import ConfigError
from app.main import create_app
from app.pricing import load_prices


def test_cost_is_priced_per_million_tokens():
    prices = load_prices(PRICES_FILE)
    assert prices.cost(SMALL, 1_000_000, 1_000_000) == pytest.approx(0.045 + 0.384)
    assert prices.cost(LARGE, 500_000, 0) == pytest.approx(0.1465)
    assert prices.cost("fake", 1_000_000, 1_000_000) == 0


def test_cached_call_costs_nothing():
    prices = load_prices(PRICES_FILE)
    assert prices.cost(LARGE, 1_000_000, 1_000_000, cached=True) == 0


def test_unpriced_model_prevents_startup(make_config, directory):
    config = make_config(model_small="no-such-model")
    with pytest.raises(ConfigError, match="no-such-model"):
        create_app(config, directory=directory)
