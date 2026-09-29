"""Create the configured project database if it does not already exist."""

from __future__ import annotations

import os

import psycopg
from psycopg import sql

from db_connection import load_env_file


def main() -> int:
    load_env_file()
    target_database = os.getenv("PGDATABASE")
    if not target_database:
        raise RuntimeError("PGDATABASE must be configured in .env")

    maintenance_database = os.getenv("PGMAINTENANCE", "postgres")
    with psycopg.connect("", dbname=maintenance_database, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_database,))
            if cur.fetchone():
                print(f"Database {target_database} already exists")
                return 0
            cur.execute(
                sql.SQL("CREATE DATABASE {} WITH ENCODING 'UTF8' TEMPLATE template0").format(
                    sql.Identifier(target_database)
                )
            )
    print(f"Database {target_database} created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
