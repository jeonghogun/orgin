"""Integration test configuration and opt-in guards."""

import os
from contextlib import closing
from urllib.parse import urlparse

import psycopg2
import pytest
import redis


_TRUE_VALUES = {"1", "true", "yes", "on"}


def _is_truthy(value: str) -> bool:
    return value.lower() in _TRUE_VALUES if value else False


def _build_database_url() -> str:
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url

    host = os.getenv("TEST_DB_HOST", "localhost")
    port = os.getenv("TEST_DB_PORT", "5433")
    user = os.getenv("POSTGRES_USER", "test_user")
    password = os.getenv("POSTGRES_PASSWORD", "test_password")
    database = os.getenv("POSTGRES_DB", "test_origin_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def _build_redis_url() -> str:
    env_url = os.getenv("REDIS_URL")
    if env_url:
        return env_url

    host = os.getenv("TEST_REDIS_HOST", "localhost")
    port = os.getenv("TEST_REDIS_PORT", "6379")
    return f"redis://{host}:{port}/0"


def _describe_endpoint(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or ""
    return f"{host}:{port}" if port else host


def _assert_postgres_available() -> None:
    database_url = _build_database_url()
    try:
        with closing(
            psycopg2.connect(database_url, connect_timeout=3)
        ):
            return
    except psycopg2.Error as exc:  # pragma: no cover - connectivity guard only
        raise Exception(
            "PostgreSQL is not reachable at"
            f" {_describe_endpoint(database_url)}."
            " Start the database service or export DATABASE_URL before rerunning"
            " integration tests."
        ) from exc


def _assert_redis_available() -> None:
    redis_url = _build_redis_url()
    try:
        client = redis.Redis.from_url(
            redis_url,
            socket_timeout=3,
            socket_connect_timeout=3,
        )
        client.ping()
    except redis.RedisError as exc:  # pragma: no cover - connectivity guard only
        raise Exception(
            "Redis is not reachable at"
            f" {_describe_endpoint(redis_url)}."
            " Start the Redis service or export REDIS_URL before rerunning"
            " integration tests."
        ) from exc
    finally:
        try:
            client.close()
        except Exception:  # pragma: no cover - best effort cleanup
            pass


def pytest_collection_modifyitems(config, items):
    if not items:
        return

    if not _is_truthy(os.getenv("RUN_INTEGRATION_TESTS", "0")):
        skip_marker = pytest.mark.skip(
            reason=(
                "Integration tests skipped by default. Set RUN_INTEGRATION_TESTS=1 to"
                " opt in once PostgreSQL and Redis are running."
            )
        )
        for item in items:
            item.add_marker(skip_marker)
        return

    try:
        _assert_postgres_available()
        _assert_redis_available()
    except Exception as skip_exc:
        skip_marker = pytest.mark.skip(reason=str(skip_exc))
        for item in items:
            item.add_marker(skip_marker)
