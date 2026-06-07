from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field
import uuid
import time
from aiocache import Cache
from app.repository import Repository
from app.dependencies import get_db_repo, get_current_user_id, get_push_client, get_proposal_cache
from app.services.push import PushClient

router = APIRouter(prefix="/api/v1/swipes", tags=["swipes"])

class SwipeRequest(BaseModel):
    target_user_id: str = Field(..., description="The user ID being swiped on")
    action: str = Field(..., description="Action value, either 'LIKE' or 'PASS'")

class SwipeResponse(BaseModel):
    matched: bool
    proposal_id: str | None = None
    expires_in_seconds: int | None = None

async def send_match_proposal_push(
    target_user_id: str,
    proposal_id: str,
    repo: Repository,
    push_client: PushClient
):
    """
    Background worker that fetches target user's subscriptions and triggers Web Push.
    """
    subscriptions = await repo.get_push_subscriptions_by_user_id(target_user_id)
    if not subscriptions:
        return

    payload = {
        "type": "MATCH_PROPOSED",
        "proposal_id": proposal_id,
        "expires_in": 30
    }
    
    # Send push to all active subscriptions
    for sub in subscriptions:
        await push_client.send_notification(sub, payload)

@router.post("", response_model=SwipeResponse)
async def post_swipe(
    payload: SwipeRequest,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user_id),
    repo: Repository = Depends(get_db_repo),
    push_client: PushClient = Depends(get_push_client),
    cache: Cache = Depends(get_proposal_cache)
):
    """
    Registers a swipe action from the current user onto the target user.
    If both LIKE each other, creates a match proposal cached for 30 seconds.
    """
    if payload.action not in ("LIKE", "PASS"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action must be 'LIKE' or 'PASS'"
        )

    if current_user_id == payload.target_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot swipe on yourself"
        )

    # 1. Write Swipe to database
    swipe_id = f"swp_{uuid.uuid4().hex[:12]}"
    await repo.save_swipe(
        swipe_id=swipe_id,
        from_user_id=current_user_id,
        to_user_id=payload.target_user_id,
        action=payload.action
    )

    # If action is not LIKE, we can exit early since no match is possible
    if payload.action != "LIKE":
        return SwipeResponse(matched=False)

    # 2. Check if reverse record exists
    reverse_swipe = await repo.get_swipe(
        from_user_id=payload.target_user_id,
        to_user_id=current_user_id
    )

    # 3. Check if both are LIKE
    if reverse_swipe and reverse_swipe["action"] == "LIKE":
        proposal_id = str(uuid.uuid4())
        
        # Cache the proposal structure in memory (TTL 30 seconds)
        proposal_data = {
            "user_a": current_user_id,
            "user_b": payload.target_user_id,
            "accepted_a": False,
            "accepted_b": False,
            "expires_at": time.time() + 30.0
        }
        
        cache_key = f"proposal:{proposal_id}"
        await cache.set(cache_key, proposal_data, ttl=30)
        
        # 4. Trigger W3C Web Push in background thread/task
        background_tasks.add_task(
            send_match_proposal_push,
            target_user_id=payload.target_user_id,
            proposal_id=proposal_id,
            repo=repo,
            push_client=push_client
        )
        
        return SwipeResponse(
            matched=True,
            proposal_id=proposal_id,
            expires_in_seconds=30
        )

    return SwipeResponse(matched=False)
