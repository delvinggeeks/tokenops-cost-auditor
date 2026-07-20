"""Alembic environment. Migrations are ADDITIVE-ONLY in v1 (runbook §2 rollback
policy): no dropped tables/columns; down-revisions exist but are never relied on."""

import logging
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

from tokenops_cost_auditor.config import get_settings
from tokenops_cost_auditor.persistence.models import Base

config = context.config


def _make_alembic_audible() -> None:
    """Runbook §2 step 5 (`alembic upgrade head`) printed NOTHING during the
    V-D10 deploy rehearsal: alembic.ini carries a logging section but nothing
    ever applied it, so every "Running upgrade X -> Y" line was discarded. On
    the riskiest step of a production deploy the operator could not tell seven
    applied revisions from a silent no-op.

    We deliberately do NOT use logging.config.fileConfig here, which is the
    stock alembic template. fileConfig rebuilds every logger named in the ini
    file INCLUDING the root logger, and disable_existing_loggers=False does not
    protect root. Alembic is also driven in-process (tests/test_runner.py calls
    alembic.command.upgrade in the same interpreter as pytest), so the stock
    template would tear the JSON handler off root mid-process and leave it torn
    for the rest of that process's life. Configuring only the `alembic` logger
    gets the operator the same visibility and cannot touch anyone else's
    logging. propagate=False keeps these lines from being duplicated into a
    host application's root handler. (V-D10 ops gate f.1.)
    """
    log = logging.getLogger("alembic")
    # NOT `if log.handlers` — the alembic package installs a NullHandler on its
    # own logger as library hygiene, so that test is always true and silently
    # skips the whole function. Ask whether anything actually EMITS.
    has_real_handler = any(not isinstance(h, logging.NullHandler) for h in log.handlers)
    if not has_real_handler:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)-5.5s [%(name)s] %(message)s"))
        log.addHandler(handler)
        log.propagate = False  # our handler is the only one; don't double-print
    if log.getEffectiveLevel() > logging.INFO:
        # A host application may have attached its own handler but left the
        # level too high to show "Running upgrade" — raise it either way.
        log.setLevel(logging.INFO)


_make_alembic_audible()

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
