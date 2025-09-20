#!/usr/bin/env python
"""Execute the diagnostic Celery workflow against the configured broker.

This helper is intended for operators who want to verify that the broker,
backend, and workers are correctly configured after deploying a new
environment. It reuses the same diagnostic tasks leveraged by the automated
smoke tests so it remains dependency-light.
"""

from __future__ import annotations

import os
import sys

from celery import chain


def load_celery_app():
    broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    backend_url = os.getenv("CELERY_RESULT_BACKEND", broker_url)
    os.environ["CELERY_BROKER_URL"] = broker_url
    os.environ["CELERY_RESULT_BACKEND"] = backend_url

    if "app.celery_app" in sys.modules:
        del sys.modules["app.celery_app"]
    if "app.tasks.diagnostic_tasks" in sys.modules:
        del sys.modules["app.tasks.diagnostic_tasks"]

    celery_app = __import__("app.celery_app", fromlist=["celery_app"]).celery_app
    celery_app.conf.task_always_eager = False
    return celery_app


def configure_runtime() -> None:
    # Intentionally left for backwards compatibility; the actual broker is
    # configured in :func:`load_celery_app`.
    return None


def main() -> int:
    configure_runtime()
    celery_app = load_celery_app()
    workflow = chain(
        celery_app.signature("app.tasks.diagnostic_tasks.generate_smoke_payload", args=(21,)),
        celery_app.signature("app.tasks.diagnostic_tasks.evaluate_smoke_payload"),
    )

    try:
        result = workflow.delay()
        payload = result.get(timeout=int(os.getenv("CELERY_SMOKE_TIMEOUT", "30")))
    except Exception as exc:  # pragma: no cover - operational script
        print(f"Celery smoke test failed: {exc}", file=sys.stderr)
        return 1

    if payload.get("status") != "ok":  # pragma: no cover - operational script
        print(f"Celery smoke test returned unhealthy payload: {payload}", file=sys.stderr)
        return 2

    print("Celery smoke test succeeded:", payload)
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())

