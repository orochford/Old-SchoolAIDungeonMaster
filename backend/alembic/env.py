import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import all models to ensure they're registered with Base
from app.core.database import Base
from app.domains.campaigns.models import RPGSystem, Campaign
from app.domains.characters.models import Character, CharacterLevelHistory
from app.domains.sessions.models import Session, ConversationMessage
from app.domains.combat.models import CombatEncounter, CombatParticipant, ConditionTemplate, ActiveCondition
from app.domains.npcs.models import NPCDetails, NPCRelationship, DispositionHistory
from app.domains.inventory.models import ItemTemplate, CharacterInventory
from app.domains.sourcebooks.models import PDFDocument, PDFChunk
from app.domains.adventures.models import (
    AdventureModule, AdventureLocation, AdventureNPC,
    AdventureEncounter, AdventureItem, AdventureStoryBeat
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
