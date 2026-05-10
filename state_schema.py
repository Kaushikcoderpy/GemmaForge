import aiosqlite
import json
from typing import Dict, Any, List

DB_FILE = "gemmaforge.db"

async def init_db():
    """Initializes SQLite with WAL mode for high-concurrency ingestion."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute('''
            CREATE TABLE IF NOT EXISTS state_kv (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS execution_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT,
                payload TEXT
            )
        ''')
        await db.commit()

async def save_state_key(key: str, value: Any):
    """Updates a single key in the KV store. Atomic and efficient."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO state_kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value))
        )
        await db.commit()

async def save_state(state: Dict[str, Any]):
    """Bulk upsert of the entire state dictionary."""
    async with aiosqlite.connect(DB_FILE) as db:
        queries = [(k, json.dumps(v)) for k, v in state.items()]
        await db.executemany(
            "INSERT INTO state_kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            queries
        )
        await db.commit()

async def load_state() -> Dict[str, Any]:
    state = {"platforms": {}}
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT key, value FROM state_kv") as cursor:
                async for row in cursor:
                    state[row[0]] = json.loads(row[1])
    except Exception:
        pass
    return state

async def log_event(event_type: str, payload: Dict[str, Any]):
    """Append-only ledger for the 10-day history requirement."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO execution_ledger (event_type, payload) VALUES (?, ?)",
            (event_type, json.dumps(payload))
        )
        await db.commit()

async def get_historical_state(days: int = 10) -> List[Dict[str, Any]]:
    history = []
    async with aiosqlite.connect(DB_FILE) as db:
        query = "SELECT timestamp, event_type, payload FROM execution_ledger WHERE timestamp >= datetime('now', ?)"
        async with db.execute(query, (f'-{days} days',)) as cursor:
            async for row in cursor:
                history.append({"timestamp": row[0], "event_type": row[1], "payload": json.loads(row[2])})
    return history