"""Smoke tests that exercise the Celery pipeline with a real worker."""

from __future__ import annotations

import importlib
import os
import sys

import pytest
from celery import chain
from celery.contrib.testing.worker import start_worker


pytestmark = pytest.mark.heavy


def _load_isolated_celery_app():
    """Load `app.celery_app` with an isolated broker/backend configuration."""

    broker_url = os.environ.get("CELERY_TEST_BROKER_URL", "memory://")
    backend_url = os.environ.get("CELERY_TEST_BACKEND_URL", "cache+memory://")
    os.environ["CELERY_BROKER_URL"] = broker_url
    os.environ["CELERY_RESULT_BACKEND"] = backend_url

    if "app.celery_app" in sys.modules:
        del sys.modules["app.celery_app"]
    if "app.tasks.diagnostic_tasks" in sys.modules:
        del sys.modules["app.tasks.diagnostic_tasks"]

    celery_app_module = importlib.import_module("app.celery_app")
    celery_app = celery_app_module.celery_app
    celery_app.conf.task_always_eager = False
    return celery_app


def test_diagnostic_workflow_executes_through_worker():
    """The diagnostic chain should complete when a worker is available."""

    celery_app = _load_isolated_celery_app()

    with start_worker(celery_app, perform_ping_check=False, pool="solo"):
        workflow = chain(
            celery_app.signature(
                "app.tasks.diagnostic_tasks.generate_smoke_payload",
                args=(5,),
            ),
            celery_app.signature("app.tasks.diagnostic_tasks.evaluate_smoke_payload"),
        )
        result = workflow.delay()
        payload = result.get(timeout=10)

    assert payload["status"] == "ok"
    assert payload["total"] == 30
    assert payload["count"] == 3
    assert payload["seed"] == 5

