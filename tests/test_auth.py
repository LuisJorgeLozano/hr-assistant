"""Pruebas unitarias del acceso por clave."""
import pytest

from conftest import ACME_KEY, GLOBEX_KEY

INVALID = {"detail": "invalid or missing API key"}


@pytest.mark.parametrize(
    "key",
    ["", ACME_KEY[:-1] + "X", ACME_KEY + "extra", " " + ACME_KEY],
    ids=["empty", "same length", "longer", "leading space"],
)
def test_empty_or_nearly_right_keys_are_rejected(make_observed, key):
    observed = make_observed()
    response = observed.client.get("/metrics", headers={"X-API-Key": key})
    assert response.status_code == 401
    assert response.json() == INVALID
    assert observed.events("request")[0]["status"] == 401
    assert "client" not in observed.events("request")[0]


def test_the_key_of_another_client_identifies_that_client(make_observed):
    observed = make_observed()
    headers = {"X-API-Key": GLOBEX_KEY, "X-Request-ID": "globex-1"}
    response = observed.client.post("/ask", json={"question": "Hi"}, headers=headers)
    assert response.status_code == 200
    clients = {e["client"] for e in observed.events("request")}
    assert clients == {"globex"}
