from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit
from typing import Any

DEFAULT_ASYNC_DATABASE_URL = "postgresql+asyncpg://panoptique:panoptique@localhost:5432/panoptique"
DEFAULT_SYNC_DATABASE_URL = "postgresql://panoptique:panoptique@localhost:5432/panoptique"


def get_database_url(*, required: bool = True) -> str:
    url = os.environ.get("PANOPTIQUE_DATABASE_URL")
    if url:
        return url
    if required:
        raise RuntimeError(
            "PANOPTIQUE_DATABASE_URL is required for Panoptique DB writes; "
            "copy infra/panoptique/.env.example for local development."
        )
    return DEFAULT_ASYNC_DATABASE_URL


def get_sync_database_url(*, required: bool = False) -> str:
    url = os.environ.get("PANOPTIQUE_SYNC_DATABASE_URL")
    if url:
        return url
    async_url = os.environ.get("PANOPTIQUE_DATABASE_URL")
    if async_url:
        return async_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if required:
        raise RuntimeError("PANOPTIQUE_SYNC_DATABASE_URL is required for sync DB operations")
    return DEFAULT_SYNC_DATABASE_URL


def mask_database_url(url: str) -> str:
    parts = urlsplit(url)
    if "@" not in parts.netloc or ":" not in parts.netloc.split("@", 1)[0]:
        return url
    userinfo, hostinfo = parts.netloc.rsplit("@", 1)
    username = userinfo.split(":", 1)[0]
    return urlunsplit((parts.scheme, f"{username}:***@{hostinfo}", parts.path, parts.query, parts.fragment))


def create_async_engine(url: str | None = None, **kwargs: Any) -> Any:
    try:
        from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine
    except ImportError as exc:
        raise RuntimeError("SQLAlchemy is required for async Panoptique DB engines") from exc
    return _create_async_engine(url or get_database_url(), **kwargs)


def create_sync_engine(url: str | None = None, **kwargs: Any) -> Any:
    try:
        from sqlalchemy import create_engine as _create_engine
    except ImportError as exc:
        raise RuntimeError("SQLAlchemy is required for Panoptique DB engines") from exc
    return _create_engine(url or get_sync_database_url(), **kwargs)
