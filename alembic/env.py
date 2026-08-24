"""Alembic's runtime setup.

This file runs every time you use an `alembic` command. Its two jobs:

1. Tell Alembic WHERE the database is — we take the URL from our own settings
   (.env), so there is a single source of truth.
2. Tell Alembic what the schema SHOULD look like — that is `Base.metadata`,
   which knows about every model we've imported. Alembic compares this against
   the real database to auto-generate migrations.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Importing the app's settings and models. `app.models` imports every model,
# so Base.metadata is complete.
from app.config import settings
from app.models import Base

# Alembic's config object, and console logging from alembic.ini.
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Feed our real database URL in at runtime (not stored in alembic.ini).
config.set_main_option("sqlalchemy.url", settings.database_url)

# This is the "what the schema should be" reference Alembic diffs against.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL to a file without connecting to a database. Rarely used."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """The normal path: connect to Postgres and apply migrations."""
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
