"""Prometheus observability metrics module for FastAPI.

Provides request counter, latency histograms, active job gauges, and system status metrics
in standard Prometheus format (text/plain; version=0.0.4).
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any


class PrometheusMetrics:
    """Zero-dependency Prometheus metrics collector."""

    def __init__(self) -> None:
        self.request_counts: dict[tuple[str, str, int], int] = defaultdict(int)
        self.request_latencies: dict[tuple[str, str], list[float]] = defaultdict(list)
        self.active_jobs: int = 0
        self.model_inferences: dict[str, int] = defaultdict(int)

    def record_request(self, method: str, endpoint: str, status: int, duration_seconds: float) -> None:
        key = (method, endpoint, status)
        self.request_counts[key] += 1
        self.request_latencies[(method, endpoint)].append(duration_seconds)
        # Keep last 1000 latency samples
        if len(self.request_latencies[(method, endpoint)]) > 1000:
            self.request_latencies[(method, endpoint)].pop(0)

    def record_inference(self, model_name: str) -> None:
        self.model_inferences[model_name] += 1

    def generate_metrics_text(self, app_state: Any = None) -> str:
        lines = [
            "# HELP http_requests_total Total HTTP requests processed",
            "# TYPE http_requests_total counter",
        ]
        for (method, endpoint, status), count in self.request_counts.items():
            lines.append(f'http_requests_total{{method="{method}",endpoint="{endpoint}",status="{status}"}} {count}')

        lines.extend([
            "# HELP http_request_duration_seconds HTTP request latency in seconds",
            "# TYPE http_request_duration_seconds summary",
        ])
        for (method, endpoint), latencies in self.request_latencies.items():
            if latencies:
                avg_lat = sum(latencies) / len(latencies)
                lines.append(f'http_request_duration_seconds_sum{{method="{method}",endpoint="{endpoint}"}} {sum(latencies):.4f}')
                lines.append(f'http_request_duration_seconds_count{{method="{method}",endpoint="{endpoint}"}} {len(latencies)}')

        # Job and store status metrics
        active_jobs = getattr(app_state, "jobs", None)
        num_jobs = len(getattr(active_jobs, "jobs", {})) if active_jobs else 0
        lines.extend([
            "# HELP active_jobs_count Current active background jobs count",
            "# TYPE active_jobs_count gauge",
            f"active_jobs_count {num_jobs}",
        ])

        store = getattr(app_state, "store", None)
        num_alerts = len(getattr(store, "alerts", {})) if store else 0
        num_events = len(getattr(store, "events", {})) if store else 0

        lines.extend([
            "# HELP active_alerts_count Active weather anomaly alerts in system",
            "# TYPE active_alerts_count gauge",
            f"active_alerts_count {num_alerts}",
            "# HELP active_events_count Active weather anomaly events tracked",
            "# TYPE active_events_count gauge",
            f"active_events_count {num_events}",
        ])

        lines.extend([
            "# HELP model_inference_total Total model inference invocations",
            "# TYPE model_inference_total counter",
        ])
        for model_name, count in self.model_inferences.items():
            lines.append(f'model_inference_total{{model="{model_name}"}} {count}')

        return "\n".join(lines) + "\n"


metrics_collector = PrometheusMetrics()
