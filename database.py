from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from tools.config import config_read

config = config_read("config.ini")


DATABASE_URL = f"" \
               f"postgresql+asyncpg://" \
               f"{config.get('DATABASE', 'user')}:" \
               f"{config.get('DATABASE', 'pass')}@" \
               f"{config.get('DATABASE', 'host')}:" \
               f"{config.get('DATABASE', 'port')}/" \
               f"{config.get('DATABASE', 'name')}"


engine = create_async_engine(DATABASE_URL)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
