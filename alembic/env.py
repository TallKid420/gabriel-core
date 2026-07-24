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
import gabriel.document.orm  # noqa: E402, F401  # registers DocumentORM
import gabriel.knowledge.chunk_orm  # noqa: E402, F401  # registers DocumentChunkORM
import gabriel.knowledge.source_orm  # noqa: E402, F401  # registers KnowledgeSourceORM
import gabriel.conversation.orm  # noqa: E402, F401  # registers ConversationORM
import gabriel.conversation.message_orm  # noqa: E402, F401  # registers MessageORM
import gabriel.notification.orm  # noqa: E402, F401  # registers NotificationORM
import gabriel.memory.layer_orm  # noqa: E402, F401  # registers MemoryLayerEntryORM

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


def _get_alembic_url() -> str:
    """Resolve database URL for alembic (sync driver required).
    
    Alembic requires a synchronous database URL. If GABRIEL_DATABASE_URL is set
    and uses async drivers (sqlite+aiosqlite, postgresql+asyncpg), convert to sync.
    """
    url = os.getenv("GABRIEL_DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    if not url:
        # Default to SQLite for local dev
        return "sqlite:///./.gabriel/gabriel.db"
    
    # Convert async drivers to sync for alembic compatibility
    # sqlite+aiosqlite:///path -> sqlite:///path (remove "+aiosqlite" only)
    url = url.replace("sqlite+aiosqlite://", "sqlite://")
    url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = _get_alembic_url()
    
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=False,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Required for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Resolve URL (with sync driver conversion if needed)
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_alembic_url()
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Enable batch mode for SQLite compatibility
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=False,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
