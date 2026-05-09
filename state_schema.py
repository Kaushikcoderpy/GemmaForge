import aiosqlite
import json
from typing import Dict, Any
from logger import get_logger

DB_FILE = "gemmaforge.db"

async def init_db():
    """Initializes the SQLite DB with WAL mode for high concurrency."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute('''
            CREATE TABLE IF NOT EXISTS state_kv (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        await db.commit()

async def load_state() -> Dict[str, Any]:
    """Loads the entire KV store into a dictionary for application logic."""
    await init_db()
    
    # Initialize default structure to prevent KeyError downstream
    state: Dict[str, Any] = {"platforms": {}}
    logger = await get_logger()
    
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT key, value FROM state_kv") as cursor:
                async for row in cursor:
                    state[row[0]] = json.loads(row[1])
    except Exception as e:
        await logger.error(f"SQLite Load Exception: {e}")
        
    return state

async def save_state(state: Dict[str, Any]) -> None:
    """Upserts the current state dictionary into the SQLite database."""
    logger = await get_logger()
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            
            # Using executemany for atomic, bulk writes
            queries = [(k, json.dumps(v)) for k, v in state.items()]
            await db.executemany(
                "INSERT INTO state_kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                queries
            )
            await db.commit()
    except Exception as e:
        await logger.error(f"SQLite Write Exception: {e}")
