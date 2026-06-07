import os
import aiosqlite
import logging
from app.config import settings

logger = logging.getLogger("linder.db")

SCHEMA = """
-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(255) PRIMARY KEY,
    puuid VARCHAR(255) UNIQUE NOT NULL,
    riot_id_name VARCHAR(100) NOT NULL,
    riot_id_tag VARCHAR(10) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Push Subscriptions Table
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    endpoint TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON push_subscriptions(user_id);

-- 3. Persistent Swipes Table
CREATE TABLE IF NOT EXISTS swipes (
    id VARCHAR(255) PRIMARY KEY,
    from_user_id VARCHAR(255) NOT NULL,
    to_user_id VARCHAR(255) NOT NULL,
    action VARCHAR(10) NOT NULL, -- 'LIKE' or 'PASS'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (from_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (to_user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(from_user_id, to_user_id)
);

-- 4. Chat Lobbies
CREATE TABLE IF NOT EXISTS lobbies (
    id VARCHAR(255) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Lobby Participants
CREATE TABLE IF NOT EXISTS lobby_participants (
    lobby_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    PRIMARY KEY (lobby_id, user_id),
    FOREIGN KEY (lobby_id) REFERENCES lobbies(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 6. Messages
CREATE TABLE IF NOT EXISTS messages (
    id VARCHAR(255) PRIMARY KEY,
    lobby_id VARCHAR(255) NOT NULL,
    sender_id VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lobby_id) REFERENCES lobbies(id) ON DELETE CASCADE,
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

class Database:
    # Single shared persistent connection to eliminate connection opening/closing overhead
    _conn = None

    def __init__(self, db_path: str = settings.DATABASE_PATH):
        self.db_path = db_path

    async def connect(self) -> aiosqlite.Connection:
        if Database._conn is None:
            logger.info(f"Opening persistent SQLite connection to {self.db_path}")
            Database._conn = await aiosqlite.connect(self.db_path)
            await Database._conn.execute("PRAGMA journal_mode=WAL;")
            await Database._conn.execute("PRAGMA synchronous=NORMAL;")
            await Database._conn.execute("PRAGMA busy_timeout=5000;")
            await Database._conn.execute("PRAGMA foreign_keys=ON;")
            Database._conn.row_factory = aiosqlite.Row
        return Database._conn

    async def close(self):
        if Database._conn is not None:
            logger.info(f"Closing persistent SQLite connection to {self.db_path}")
            await Database._conn.close()
            Database._conn = None

    async def get_db(self):
        """
        Async generator yielding the shared connection.
        """
        conn = await self.connect()
        yield conn

    async def init_db(self):
        """
        Executes schema creation SQL on the target database path.
        """
        logger.info(f"Initializing database at path: {self.db_path}")
        async for conn in self.get_db():
            async with conn.cursor() as cursor:
                await cursor.executescript(SCHEMA)
            await conn.commit()
            break
        logger.info("Database schema initialized successfully.")
