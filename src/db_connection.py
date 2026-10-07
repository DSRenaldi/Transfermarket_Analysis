"""Shared, secret-safe PostgreSQL connection configuration."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg


ALLOWED_KEYS = {
    "DATABASE_URL",
    "PGHOST",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGPASSWORD",
    "PGSSLMODE",
}


def load_env_file(path: Path = Path(".env")) -> None:
    """Load supported keys from an ignored local .env file if it exists."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in ALLOWED_KEYS:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def connect(**kwargs: object) -> psycopg.Connection:
    load_env_file()
    return psycopg.connect(os.getenv("DATABASE_URL", ""), **kwargs)
