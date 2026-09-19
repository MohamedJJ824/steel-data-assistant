"""SQLAlchemy engines for the two database roles.

Two engines, deliberately: ``app_engine`` for everything the service owns, and
``assistant_engine`` for generated SQL only. The split is the first of the two
layers that keep the agent read-only, the SQL guard being the second.
"""

from __future__ import annotations

import functools
import os

from sqlalchemy import Engine, create_engine

from steel_assistant.config import get_settings


def _password(env_var: str) -> str:
    """Read a role password from the environment, failing loudly if unset."""
    value = os.environ.get(env_var)
    if not value:
        raise RuntimeError(f"{env_var} is not set. Copy .env.example to .env and fill it in.")
    return value


def _url(user: str, password: str) -> str:
    """Build a psycopg 3 connection URL for a role."""
    db = get_settings().db
    return f"postgresql+psycopg://{user}:{password}@{db.host}:{db.port}/{db.name}"


@functools.lru_cache(maxsize=1)
def app_engine() -> Engine:
    """Engine for the API: reads ``rag``, writes ``app``, reads ``plant``."""
    settings = get_settings()
    return create_engine(
        _url(settings.db.app_user, _password("APP_RW_PASSWORD")),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )


@functools.lru_cache(maxsize=1)
def assistant_engine() -> Engine:
    """Engine for generated SQL. Read-only role, ``plant`` schema only.

    ``postgresql_readonly`` puts every transaction in read-only mode on top of
    the role's own ``default_transaction_read_only``, so a write attempt fails
    even if the guard and the role grants were both somehow bypassed.
    """
    settings = get_settings()
    engine = create_engine(
        _url(settings.db.assistant_user, _password("ASSISTANT_RO_PASSWORD")),
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        execution_options={"postgresql_readonly": True},
    )
    return engine


@functools.lru_cache(maxsize=1)
def superuser_engine() -> Engine:
    """Engine for seed scripts only. Never used to serve a request."""
    user = os.environ.get("POSTGRES_USER", "postgres")
    return create_engine(_url(user, _password("POSTGRES_PASSWORD")), pool_pre_ping=True)
