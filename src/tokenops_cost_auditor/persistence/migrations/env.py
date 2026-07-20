"""Alembic environment. Migrations are ADDITIVE-ONLY in v1 (runbook §2 rollback
policy): no dropped tables/columns; down-revisions exist but are never relied on."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from tokenops_cost_auditor.config import get_settings
from tokenops_cost_auditor.persistence.models import Base

config = context.config

# Runbook §2 step 5 (`alembic upgrade head`) printed NOTHING during the V-D10
# deploy rehearsal: alembic.ini carries a full logging section but nothing ever
# applied it, so every "Running upgrade X -> Y" line was discarded. On the
# riskiest step of a production deploy the operator could not tell seven
# applied revisions from a silent no-op.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

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
