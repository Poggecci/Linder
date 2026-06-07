from typing import List, Optional, Dict, Any
import aiosqlite
import asyncio
import logging
from app.db import Database

logger = logging.getLogger("linder.repository")

class Repository:
    # Class-level lock to fully serialize writes to SQLite and prevent "database is locked" errors
    _write_lock = asyncio.Lock()

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    async def create_user(
        self, user_id: str, puuid: str, riot_id_name: str, riot_id_tag: str
    ) -> Dict[str, Any]:
        sql = """
            INSERT INTO users (id, puuid, riot_id_name, riot_id_tag)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(puuid) DO UPDATE SET
                riot_id_name=excluded.riot_id_name,
                riot_id_tag=excluded.riot_id_tag
            RETURNING id, puuid, riot_id_name, riot_id_tag, created_at;
        """
        async with self._write_lock:
            async for conn in self.db.get_db():
                async with conn.execute(sql, (user_id, puuid, riot_id_name, riot_id_tag)) as cursor:
                    row = await cursor.fetchone()
                    await conn.commit()
                    return dict(row) if row else {}

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        sql = "SELECT id, puuid, riot_id_name, riot_id_tag, created_at FROM users WHERE id = ?;"
        async for conn in self.db.get_db():
            async with conn.execute(sql, (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_user_by_puuid(self, puuid: str) -> Optional[Dict[str, Any]]:
        sql = "SELECT id, puuid, riot_id_name, riot_id_tag, created_at FROM users WHERE puuid = ?;"
        async for conn in self.db.get_db():
            async with conn.execute(sql, (puuid,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_user_by_riot_id(self, name: str, tag: str) -> Optional[Dict[str, Any]]:
        sql = """
            SELECT id, puuid, riot_id_name, riot_id_tag, created_at 
            FROM users 
            WHERE LOWER(riot_id_name) = LOWER(?) AND LOWER(riot_id_tag) = LOWER(?);
        """
        async for conn in self.db.get_db():
            async with conn.execute(sql, (name, tag)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_users_by_puuids(self, puuids: List[str]) -> List[Dict[str, Any]]:
        if not puuids:
            return []
        placeholders = ",".join("?" for _ in puuids)
        sql = f"SELECT id, puuid, riot_id_name, riot_id_tag, created_at FROM users WHERE puuid IN ({placeholders});"
        async for conn in self.db.get_db():
            async with conn.execute(sql, puuids) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def save_push_subscription(
        self, subscription_id: str, user_id: str, endpoint: str, p256dh: str, auth: str
    ) -> Dict[str, Any]:
        sql = """
            INSERT INTO push_subscriptions (id, user_id, endpoint, p256dh, auth)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                endpoint=excluded.endpoint,
                p256dh=excluded.p256dh,
                auth=excluded.auth
            RETURNING id, user_id, endpoint, p256dh, auth, created_at;
        """
        async with self._write_lock:
            async for conn in self.db.get_db():
                async with conn.execute(sql, (subscription_id, user_id, endpoint, p256dh, auth)) as cursor:
                    row = await cursor.fetchone()
                    await conn.commit()
                    return dict(row) if row else {}

    async def get_push_subscriptions_by_user_id(self, user_id: str) -> List[Dict[str, Any]]:
        sql = "SELECT id, user_id, endpoint, p256dh, auth, created_at FROM push_subscriptions WHERE user_id = ?;"
        async for conn in self.db.get_db():
            async with conn.execute(sql, (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def save_swipe(
        self, swipe_id: str, from_user_id: str, to_user_id: str, action: str
    ) -> Dict[str, Any]:
        sql = """
            INSERT INTO swipes (id, from_user_id, to_user_id, action)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(from_user_id, to_user_id) DO UPDATE SET
                action=excluded.action,
                created_at=CURRENT_TIMESTAMP
            RETURNING id, from_user_id, to_user_id, action, created_at;
        """
        async with self._write_lock:
            async for conn in self.db.get_db():
                async with conn.execute(sql, (swipe_id, from_user_id, to_user_id, action)) as cursor:
                    row = await cursor.fetchone()
                    await conn.commit()
                    return dict(row) if row else {}

    async def get_swipe(self, from_user_id: str, to_user_id: str) -> Optional[Dict[str, Any]]:
        sql = "SELECT id, from_user_id, to_user_id, action, created_at FROM swipes WHERE from_user_id = ? AND to_user_id = ?;"
        async for conn in self.db.get_db():
            async with conn.execute(sql, (from_user_id, to_user_id)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def create_lobby(self, lobby_id: str) -> Dict[str, Any]:
        sql = "INSERT INTO lobbies (id) VALUES (?) RETURNING id, created_at;"
        async with self._write_lock:
            async for conn in self.db.get_db():
                async with conn.execute(sql, (lobby_id,)) as cursor:
                    row = await cursor.fetchone()
                    await conn.commit()
                    return dict(row) if row else {}

    async def add_lobby_participant(self, lobby_id: str, user_id: str) -> None:
        sql = "INSERT OR IGNORE INTO lobby_participants (lobby_id, user_id) VALUES (?, ?);"
        async with self._write_lock:
            async for conn in self.db.get_db():
                await conn.execute(sql, (lobby_id, user_id))
                await conn.commit()

    async def create_message(
        self, message_id: str, lobby_id: str, sender_id: str, content: str
    ) -> Dict[str, Any]:
        sql = """
            INSERT INTO messages (id, lobby_id, sender_id, content)
            VALUES (?, ?, ?, ?)
            RETURNING id, lobby_id, sender_id, content, created_at;
        """
        async with self._write_lock:
            async for conn in self.db.get_db():
                async with conn.execute(sql, (message_id, lobby_id, sender_id, content)) as cursor:
                    row = await cursor.fetchone()
                    await conn.commit()
                    return dict(row) if row else {}

    async def get_lobby_participants(self, lobby_id: str) -> List[Dict[str, Any]]:
        sql = """
            SELECT u.id, u.puuid, u.riot_id_name, u.riot_id_tag, u.created_at 
            FROM lobby_participants lp
            JOIN users u ON lp.user_id = u.id
            WHERE lp.lobby_id = ?;
        """
        async for conn in self.db.get_db():
            async with conn.execute(sql, (lobby_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
