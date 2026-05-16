"""
App-wide settings stored in a singleton key/value table.

Used for runtime configuration that needs to outlive a container restart
without requiring redeploys — currently the global model override.

The module-level cache means LLM entrypoints can call `get` cheaply on
every request. The cache is invalidated whenever `set_value` writes.
"""
import json
from sqlalchemy import text

from app.database import engine

_cache: dict = {}
_loaded = False


async def _load() -> None:
    global _loaded
    async with engine.begin() as conn:
        rows = await conn.execute(text("SELECT key, value FROM app_settings"))
        for row in rows.mappings():
            v = row["value"]
            _cache[row["key"]] = json.loads(v) if isinstance(v, str) else v
    _loaded = True


async def get(key: str, default=None):
    if not _loaded:
        await _load()
    return _cache.get(key, default)


async def set_value(key: str, value) -> None:
    payload = json.dumps(value)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO app_settings (key, value) VALUES (:k, CAST(:v AS jsonb)) "
                "ON CONFLICT (key) DO UPDATE SET value = CAST(:v AS jsonb), updated_at = now()"
            ),
            {"k": key, "v": payload},
        )
    _cache[key] = value


async def delete(key: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM app_settings WHERE key = :k"), {"k": key})
    _cache.pop(key, None)
