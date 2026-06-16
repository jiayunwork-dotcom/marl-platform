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


async def _migrate_batch_run_id_column():
    """Add batch_run_id column to experiments table if it doesn't exist (idempotent)."""
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'experiments' AND column_name = 'batch_run_id'")
            )
            row = result.fetchone()
            if row is None:
                await conn.execute(
                    text("ALTER TABLE experiments ADD COLUMN batch_run_id INTEGER REFERENCES batch_runs(id)")
                )
                print("  [migrate] Added 'batch_run_id' column to experiments table")
            else:
                print("  [migrate] 'batch_run_id' column already exists, skipping")
    except Exception as e:
        print(f"  [migrate] Warning: Could not migrate batch_run_id column: {e}")


async def _migrate_batch_run_parallel_columns():
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'batch_runs' AND column_name = 'max_parallel'")
            )
            row = result.fetchone()
            if row is None:
                await conn.execute(
                    text("ALTER TABLE batch_runs ADD COLUMN max_parallel INTEGER DEFAULT 1 NOT NULL")
                )
                print("  [migrate] Added 'max_parallel' column to batch_runs table")
            else:
                print("  [migrate] 'max_parallel' column already exists, skipping")

            result = await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'batch_runs' AND column_name = 'template_version'")
            )
            row = result.fetchone()
            if row is None:
                await conn.execute(
                    text("ALTER TABLE batch_runs ADD COLUMN template_version INTEGER DEFAULT 1 NOT NULL")
                )
                print("  [migrate] Added 'template_version' column to batch_runs table")
            else:
                print("  [migrate] 'template_version' column already exists, skipping")

            result = await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'batch_runs' AND column_name = 'last_progress_at'")
            )
            row = result.fetchone()
            if row is None:
                await conn.execute(
                    text("ALTER TABLE batch_runs ADD COLUMN last_progress_at TIMESTAMP DEFAULT NULL")
                )
                print("  [migrate] Added 'last_progress_at' column to batch_runs table")
            else:
                print("  [migrate] 'last_progress_at' column already exists, skipping")
    except Exception as e:
        print(f"  [migrate] Warning: Could not migrate batch run parallel columns: {e}")


async def _migrate_template_tags_and_version():
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'experiment_templates' AND column_name = 'tags'")
            )
            row = result.fetchone()
            if row is None:
                await conn.execute(
                    text("ALTER TABLE experiment_templates ADD COLUMN tags JSONB DEFAULT '[]'::jsonb NOT NULL")
                )
                print("  [migrate] Added 'tags' column to experiment_templates table")
            else:
                print("  [migrate] 'tags' column already exists, skipping")

            result = await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'experiment_templates' AND column_name = 'version_number'")
            )
            row = result.fetchone()
            if row is None:
                await conn.execute(
                    text("ALTER TABLE experiment_templates ADD COLUMN version_number INTEGER DEFAULT 1 NOT NULL")
                )
                print("  [migrate] Added 'version_number' column to experiment_templates table")
            else:
                print("  [migrate] 'version_number' column already exists, skipping")

            result = await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'experiment_templates' AND column_name = 'is_current_version'")
            )
            row = result.fetchone()
            if row is None:
                await conn.execute(
                    text("ALTER TABLE experiment_templates ADD COLUMN is_current_version BOOLEAN DEFAULT TRUE NOT NULL")
                )
                print("  [migrate] Added 'is_current_version' column to experiment_templates table")
            else:
                print("  [migrate] 'is_current_version' column already exists, skipping")

            result = await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'experiment_templates' AND column_name = 'parent_template_id'")
            )
            row = result.fetchone()
            if row is None:
                await conn.execute(
                    text("ALTER TABLE experiment_templates ADD COLUMN parent_template_id INTEGER DEFAULT NULL REFERENCES experiment_templates(id)")
                )
                print("  [migrate] Added 'parent_template_id' column to experiment_templates table")
            else:
                print("  [migrate] 'parent_template_id' column already exists, skipping")
    except Exception as e:
        print(f"  [migrate] Warning: Could not migrate template tags and version columns: {e}")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_summary_column()
    await _migrate_policy_version_column()
    await _migrate_batch_run_id_column()
    await _migrate_batch_run_parallel_columns()
    await _migrate_template_tags_and_version()
