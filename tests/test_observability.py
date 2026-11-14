"""Pruebas unitarias del log JSON y de las metricas."""
import json
import os
from datetime import datetime

from conftest import FixedClock, make_logger

from app.observability import Metrics, request_id_var

SLO_TARGET = 100


def test_log_line_has_utc_timestamp_service_event_and_request_id():
    clock = FixedClock()
    logger, stream = make_logger(clock, service="hr-test")
    token = request_id_var.set("req-42")
    try:
        logger.log("request", status=200)
    finally:
        request_id_var.reset(token)
    raw = stream.getvalue()
    assert raw.count("\n") == 1
    line = json.loads(raw)
    assert datetime.fromisoformat(line["ts"].replace("Z", "+00:00")) == clock.now()
    assert line["ts"].startswith("2026-03-01T12:00:00")
    assert (line["service"], line["event"]) == ("hr-test", "request")
    assert (line["request_id"], line["status"]) == ("req-42", 200)


def test_percentiles_use_the_nearest_rank_of_the_samples():
    metrics = Metrics()
    for latency in range(1, 21):
        metrics.record_request(latency, failed=False)
    latency = metrics.snapshot(SLO_TARGET)["latency_ms"]
    assert (latency["p50"], latency["p95"]) == (10, 19)


def test_metrics_without_data_report_zeros_and_meet_the_target():
    snapshot = Metrics().snapshot(SLO_TARGET)
    assert snapshot["pid"] == os.getpid()
    assert snapshot["requests"] == 0
    assert snapshot["error_rate"] == 0
    assert snapshot["latency_ms"] == {"p50": 0, "p95": 0}
    assert snapshot["tokens"] == {"input": 0, "output": 0}
    assert snapshot["slo"] == {"p95_ms_target": SLO_TARGET, "met": True}


def test_error_rate_and_tokens_are_accumulated():
    metrics = Metrics()
    for failed in (False, True, False, False):
        metrics.record_request(10, failed=failed)
    metrics.add_tokens(5, 2)
    metrics.add_tokens(7, 3)
    snapshot = metrics.snapshot(SLO_TARGET)
    assert snapshot["requests"] == 4
    assert snapshot["error_rate"] == 0.25
    assert snapshot["tokens"] == {"input": 12, "output": 5}


def test_slo_is_met_only_when_p95_is_strictly_below_the_target():
    metrics = Metrics()
    metrics.record_request(SLO_TARGET, failed=False)
    assert metrics.snapshot(SLO_TARGET)["slo"]["met"] is False
    assert metrics.snapshot(SLO_TARGET + 1)["slo"]["met"] is True


def test_latency_window_is_bounded_but_the_request_count_is_not():
    metrics = Metrics(max_samples=3)
    for latency in (1000, 1000, 10, 20, 30):
        metrics.record_request(latency, failed=False)
    snapshot = metrics.snapshot(SLO_TARGET)
    assert snapshot["requests"] == 5
    assert snapshot["latency_ms"]["p95"] == 30


def test_metrics_accumulate_the_cost_in_usd():
    metrics = Metrics()
    metrics.add_cost(0.25)
    metrics.add_cost(0.5)
    assert metrics.snapshot(SLO_TARGET)["cost_usd"] == 0.75
