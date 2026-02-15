import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import QueuePool

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/motogp_db")

# QueuePool to handle concurrent requests during race weekends.
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for debugging SQL queries during development
    pool_size=20,  # Max number of permanent connections
    max_overflow=10, # Temporary connections allowed during spikes
    pool_pre_ping=True # Ensures the connection is alive before using it
)

# Generates new AsyncSession objects for our FastAPI dependencies.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False, # Essential for async; prevents errors when accessing attributes after commit
    autoflush=False
)

# All models in src/models/models.py will inherit from this.
class Base(DeclarativeBase):
    pass

# Dependency injection for FastAPI
async def get_db():
    """
    Dependency that yields a database session and ensures it's closed after use.
    Used in FastAPI: def get_rider(db: AsyncSession = Depends(get_db)):
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()