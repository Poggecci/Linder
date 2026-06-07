from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from aiocache import Cache
from app.config import settings
from app.db import Database
from app.repository import Repository
from app.services.auth import JWTService
from app.services.riot import RiotClient, ProductionRiotClient, MockRiotClient
from app.services.push import PushClient, ProductionPushClient, MockPushClient

# In-memory cache for match proposals (can be configured to use Redis in prod)
proposal_cache = Cache(Cache.MEMORY)

# Bearer token security scheme
security = HTTPBearer()

# Shared production singletons (instantiated lazily or as defaults)
_db = Database()
_repo = Repository(_db)
_jwt_service = JWTService()

# Conditionally choose production vs mock implementations based on settings/env
if settings.ENVIRONMENT == "testing" or not settings.RIOT_API_KEY:
    _riot_client = MockRiotClient()
else:
    _riot_client = ProductionRiotClient()

if settings.ENVIRONMENT == "testing" or not settings.VAPID_PRIVATE_KEY:
    _push_client = MockPushClient()
else:
    _push_client = ProductionPushClient()

# Dependency providers
def get_db_repo() -> Repository:
    return _repo

def get_jwt_service() -> JWTService:
    return _jwt_service

def get_riot_client() -> RiotClient:
    return _riot_client

def get_push_client() -> PushClient:
    return _push_client

def get_proposal_cache() -> Cache:
    return proposal_cache

async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    jwt_service: JWTService = Depends(get_jwt_service)
) -> str:
    """
    FastAPI dependency that extracts the Bearer token and decodes it to identify the user.
    """
    token = credentials.credentials
    user_id = jwt_service.decode_access_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id
