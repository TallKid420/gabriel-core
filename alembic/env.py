import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Make the src/ directory importable so gabriel modules resolve.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Import all ORM models so their tables are registered on Base.metadata.
from gabriel.database.base import Base  # noqa: E402
import gabriel.identity.orm  # noqa: E402, F401  # registers PrincipalORM
import gabriel.organization.orm  # noqa: E402, F401  # registers OrganizationORM
import gabriel.agent.orm  # noqa: E402, F401  # registers AgentORM
import gabriel.policy.orm  # noqa: E402, F401  # registers PolicyORM
import gabriel.tool.orm  # noqa: E402, F401  # registers ToolORM
import gabriel.events.orm  # noqa: E402, F401  # registers EventORM
import gabriel.events.projections.audit_projection  # noqa: E402, F401  # registers AuditLogORM
import gabriel.resource.read_model_orm  # noqa: E402, F401  # registers ResourceReadModelORM
import gabriel.memory.orm  # noqa: E402, F401  # registers MemoryEntryORM
import gabriel.integration.orm  # noqa: E402, F401  # registers ExternalIntegrationORM
import gabriel.user.orm  # noqa: E402, F401  # registers UserORM
import gabriel.organization.membership_orm  # noqa: E402, F401  # registers OrgMembershipORM
import gabriel.identity.refresh  # noqa: E402, F401  # registers RefreshTokenORM

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=False,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=False,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
