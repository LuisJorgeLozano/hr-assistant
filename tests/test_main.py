"""Pruebas unitarias de la API: pagina, encabezado de id y metricas."""
import os
import uuid

import pytest


def test_every_response_carries_a_request_id_and_a_request_line(make_observed):
    observed = make_observed()
    invalid = observed.client.post("/ask", json={"question": ""})
    missing = observed.client.get("/nope")
    assert invalid.status_code == 422
    assert missing.status_code == 404
    for response in (invalid, missing):
        uuid.UUID(response.headers["X-Request-ID"])
    statuses = [e["status"] for e in observed.events("request")]
    assert statuses == [422, 404]


@pytest.mark.parametrize("hostile", ["x" * 300, "has spaces;and<tags>"])
def test_hostile_request_ids_are_replaced_by_a_uuid(make_observed, hostile):
    observed = make_observed()
    response = observed.client.get("/health", headers={"X-Request-ID": hostile})
    value = response.headers["X-Request-ID"]
    assert value != hostile
    uuid.UUID(value)
    assert hostile not in observed.stream.getvalue()


def test_metrics_endpoint_reports_the_process_and_its_target(make_observed):
    observed = make_observed(slo_p95_ms=1234)
    response = observed.client.get("/metrics")
    body = response.json()
    assert response.status_code == 200
    assert body["pid"] == os.getpid()
    assert set(body) == {
        "pid",
        "requests",
        "error_rate",
        "latency_ms",
        "tokens",
        "cost_usd",
        "slo",
    }
    assert body["slo"]["p95_ms_target"] == 1234
    assert "X-Request-ID" in response.headers


def test_home_page_never_uses_inner_html(make_client):
    page = make_client().get("/").text
    assert "innerHTML" not in page
    assert "textContent" in page
