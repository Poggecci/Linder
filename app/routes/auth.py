from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
import uuid
from app.repository import Repository
from app.dependencies import get_db_repo, get_jwt_service
from app.services.auth import JWTService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

class TokenRequest(BaseModel):
    puuid: str = Field(..., description="Persistent Riot identifier")
    riot_id_name: str = Field(..., description="Riot ID Name part, e.g. Faker")
    riot_id_tag: str = Field(..., description="Riot ID Tag part, e.g. KR1")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: str

@router.post("/token", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def get_token(
    payload: TokenRequest,
    repo: Repository = Depends(get_db_repo),
    jwt_service: JWTService = Depends(get_jwt_service)
):
    """
    Exchanges a Riot PUUID and Riot ID for a JWT token. Registers the user if they don't exist.
    """
    # Try fetching existing user by puuid
    user = await repo.get_user_by_puuid(payload.puuid)
    
    if not user:
        # Generate new application-specific user ID (deterministic for testing VUs)
        if payload.puuid.startswith("puuid_user_"):
            user_id = f"usr_{payload.puuid.split('_')[-1]}"
        else:
            user_id = f"usr_{uuid.uuid4().hex[:12]}"
        user = await repo.create_user(
            user_id=user_id,
            puuid=payload.puuid,
            riot_id_name=payload.riot_id_name,
            riot_id_tag=payload.riot_id_tag
        )
    else:
        # Update Riot name/tag in case they changed
        user = await repo.create_user(
            user_id=user["id"],
            puuid=payload.puuid,
            riot_id_name=payload.riot_id_name,
            riot_id_tag=payload.riot_id_tag
        )

    # Generate JWT
    token = jwt_service.create_access_token(user["id"])
    
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user["id"]
    )
