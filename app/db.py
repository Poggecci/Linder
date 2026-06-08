import os
import aiosqlite
import logging
import asyncio
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
CREATE INDEX IF NOT EXISTS idx_users_riot_id_lower ON users(LOWER(riot_id_name), LOWER(riot_id_tag));

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

class ConnectionPool:
    def __init__(self, db_path: str, max_size: int = 10):
        self.db_path = db_path
        self.max_size = max_size
        self._pool = asyncio.Queue()
        self._allocated = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> aiosqlite.Connection:
        async with self._lock:
            # 1. If there's an available connection in the pool, return it
            if not self._pool.empty():
                return self._pool.get_nowait()
            
            # 2. If we haven't reached max_size, create a new connection
            if self._allocated < self.max_size:
                logger.info(f"Opening new SQLite connection in pool for {self.db_path} ({self._allocated + 1}/{self.max_size})")
                conn = await aiosqlite.connect(self.db_path)
                await conn.execute("PRAGMA journal_mode=WAL;")
                await conn.execute("PRAGMA synchronous=NORMAL;")
                await conn.execute("PRAGMA busy_timeout=5000;")
                await conn.execute("PRAGMA foreign_keys=ON;")
                conn.row_factory = aiosqlite.Row
                self._allocated += 1
                return conn

        # 3. Otherwise, wait for an available connection from the pool
        return await self._pool.get()

    async def release(self, conn: aiosqlite.Connection):
        await self._pool.put(conn)

    async def close_all(self):
        async with self._lock:
            logger.info(f"Closing all {self._allocated} connections in pool for {self.db_path}")
            while not self._pool.empty():
                conn = self._pool.get_nowait()
                await conn.close()
            self._allocated = 0


class Database:
    # Class-level pool shared across all contexts
    _pool = None

    def __init__(self, db_path: str = settings.DATABASE_PATH):
        self.db_path = db_path

    async def get_pool(self) -> ConnectionPool:
        if Database._pool is None:
            logger.info(f"Creating connection pool for {self.db_path}")
            Database._pool = ConnectionPool(self.db_path)
        return Database._pool

    async def connect(self) -> aiosqlite.Connection:
        pool = await self.get_pool()
        return await pool.acquire()

    async def close(self):
        if Database._pool is not None:
            logger.info(f"Closing persistent SQLite connection pool for {self.db_path}")
            await Database._pool.close_all()
            Database._pool = None

    async def get_db(self):
        """
        Async generator yielding a connection checked out from the pool,
        and returning it back to the pool afterward.
        """
        pool = await self.get_pool()
        conn = await pool.acquire()
        try:
            yield conn
        finally:
            await pool.release(conn)

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
