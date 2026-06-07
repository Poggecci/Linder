from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
import hashlib
from app.repository import Repository
from app.dependencies import get_db_repo, get_current_user_id

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])

class SubscriptionKeys(BaseModel):
    p256dh: str = Field(..., description="P256dh public key for encryption")
    auth: str = Field(..., description="Auth secret key")

class SubscribeRequest(BaseModel):
    endpoint: str = Field(..., description="Browser push service endpoint URL")
    keys: SubscriptionKeys

@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe(
    payload: SubscribeRequest,
    current_user_id: str = Depends(get_current_user_id),
    repo: Repository = Depends(get_db_repo)
):
    """
    Saves a W3C Web Push subscription payload for the current authenticated user.
    """
    # Validate payload structure
    if not payload.endpoint or not payload.keys.p256dh or not payload.keys.auth:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Web Push payload structure"
        )

    # Generate a unique deterministic subscription ID based on user and endpoint
    unique_str = f"{current_user_id}:{payload.endpoint}"
    subscription_id = f"sub_{hashlib.sha256(unique_str.encode()).hexdigest()[:16]}"
    
    await repo.save_push_subscription(
        subscription_id=subscription_id,
        user_id=current_user_id,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth
    )
    
    return {"message": "Subscription saved"}
