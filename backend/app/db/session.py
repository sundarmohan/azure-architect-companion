import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
DATABASE_URL=os.getenv("DATABASE_URL","postgresql+asyncpg://monitorai:monitorai_dev@localhost:55432/monitorai")
engine=create_async_engine(DATABASE_URL,pool_pre_ping=True)
SessionLocal=async_sessionmaker(engine,class_=AsyncSession,expire_on_commit=False)
