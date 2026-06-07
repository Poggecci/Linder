import pytest
import asyncio
import os
import httpx
from typing import AsyncGenerator
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Set testing environment before any config loading
os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_PATH"] = "linder_test.db"

from app.main import app
from app.db import Database
from app.repository import Repository
from app.dependencies import (
    get_db_repo,
    get_jwt_service,
    get_riot_client,
    get_push_client,
    get_proposal_cache,
    proposal_cache
)
from app.services.auth import JWTService
from app.services.riot import MockRiotClient
from app.services.push import MockPushClient

# In pytest-asyncio, configure the event loop
@pytest.fixture(autouse=True)
async def setup_db():
    """
    Ensures a clean database is initialized for each test.
    """
    db_path = "linder_test.db"
    db = Database(db_path)
    await db.close() # Ensure closed if leftover from previous crashed runs
    # Remove old test DB if it exists
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass
        
    await db.init_db()
    yield
    # Cleanup after test
    await db.close()
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass

@pytest.fixture(autouse=True)
async def clean_database(setup_db):
    """
    Cleans database records between individual tests.
    """
    db_path = "linder_test.db"
    db = Database(db_path)
    async for conn in db.get_db():
        await conn.execute("DELETE FROM messages;")
        await conn.execute("DELETE FROM lobby_participants;")
        await conn.execute("DELETE FROM lobbies;")
        await conn.execute("DELETE FROM swipes;")
        await conn.execute("DELETE FROM push_subscriptions;")
        await conn.execute("DELETE FROM users;")
        await conn.commit()
        break
    yield

@pytest.fixture(autouse=True)
async def clear_cache():
    """
    Clears the memory cache between tests.
    """
    await proposal_cache.clear()
    yield

@pytest.fixture
def mock_riot() -> MockRiotClient:
    return MockRiotClient()

@pytest.fixture
def mock_push() -> MockPushClient:
    return MockPushClient()

@pytest.fixture
def test_repo() -> Repository:
    return Repository(Database("linder_test.db"))

@pytest.fixture
def jwt_service() -> JWTService:
    return JWTService(allow_mock=True)

@pytest.fixture
async def client(
    mock_riot: MockRiotClient,
    mock_push: MockPushClient,
    test_repo: Repository,
    jwt_service: JWTService
) -> AsyncGenerator[AsyncClient, None]:
    """
    Yields an async test client with dependency overrides registered.
    """
    app.dependency_overrides[get_db_repo] = lambda: test_repo
    app.dependency_overrides[get_riot_client] = lambda: mock_riot
    app.dependency_overrides[get_push_client] = lambda: mock_push
    app.dependency_overrides[get_jwt_service] = lambda: jwt_service
    app.dependency_overrides[get_proposal_cache] = lambda: proposal_cache
    
    async with AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
        
    # Clean overrides
    app.dependency_overrides.clear()
