"""Thin repositories (docs/03-LLD.md §1). At D1: engine/session factory only;
per-table repositories arrive with their tables (D6+)."""

from sqlalchemy import Engine, create_engine


def make_engine(database_url: str) -> Engine:
    connect_args: dict[str, int] = {}
    if database_url.startswith("postgresql"):
        # Bounded connect wait so /healthz degrades fast instead of hanging (NFR-05).
        connect_args["connect_timeout"] = 2
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
