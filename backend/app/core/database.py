from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


async def _migrate_summary_column():
    """Add summary column to experiments table if it doesn't exist (idempotent)."""
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'experiments' AND column_name = 'summary'")
            )
            row = result.fetchone()
            if row is None:
                await conn.execute(
                    text("ALTER TABLE experiments ADD COLUMN summary JSONB DEFAULT NULL")
                )
                print("  [migrate] Added 'summary' column to experiments table")
            else:
                print("  [migrate] 'summary' column already exists, skipping")
    except Exception as e:
        print(f"  [migrate] Warning: Could not migrate summary column: {e}")


async def _migrate_policy_version_column():
    """Add version column to policy_services table if it doesn't exist (idempotent)."""
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'policy_services' AND column_name = 'version'")
            )
            row = result.fetchone()
            if row is None:
                await conn.execute(
                    text("ALTER TABLE policy_services ADD COLUMN version INTEGER DEFAULT 1 NOT NULL")
                )
                print("  [migrate] Added 'version' column to policy_services table")
            else:
                print("  [migrate] 'version' column already exists, skipping")
    except Exception as e:
        print(f"  [migrate] Warning: Could not migrate policy version column: {e}")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_summary_column()
    await _migrate_policy_version_column()
