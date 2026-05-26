"""Instance-level key-value config model with data-access class methods."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, Text, select
from sqlalchemy.dialects.sqlite import JSON

from cptr.models.base import Base
from cptr.utils.db import get_db


class Config(Base):
    """Instance-level key-value config. Managed by admins.

    Keys use dot-notation: auth.signup_enabled, ai.default_model, etc.
    Values are JSON (booleans, strings, numbers, objects, arrays).
    """
    __tablename__ = "config"

    key = Column(Text, primary_key=True)
    value = Column(JSON, nullable=False)
    updated_at = Column(BigInteger, nullable=True)

    # ── Class methods ────────────────────────────────────────

    @staticmethod
    async def get(key: str) -> object | None:
        """Get a config value by key. Returns None if not set."""
        async with await get_db() as db:
            row = await db.get(Config, key)
            return row.value if row else None

    @staticmethod
    async def get_all() -> dict:
        """Get all config as {key: value}."""
        async with await get_db() as db:
            result = await db.execute(select(Config))
            return {row.key: row.value for row in result.scalars().all()}

    @staticmethod
    async def get_namespace(namespace: str) -> dict:
        """Get all config keys under a namespace (e.g. 'auth' → 'auth.*')."""
        async with await get_db() as db:
            result = await db.execute(
                select(Config).where(Config.key.like(f"{namespace}.%"))
            )
            return {row.key: row.value for row in result.scalars().all()}

    @staticmethod
    async def upsert(updates: dict) -> None:
        """Upsert multiple config key-value pairs."""
        async with await get_db() as db:
            for key, value in updates.items():
                existing = await db.get(Config, key)
                if existing:
                    existing.value = value
                else:
                    db.add(Config(key=key, value=value))
            await db.commit()
