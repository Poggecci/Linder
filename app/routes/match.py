from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field
import uuid
import time
from aiocache import Cache
from app.repository import Repository
from app.dependencies import get_db_repo, get_current_user_id, get_push_client, get_proposal_cache
from app.services.push import PushClient

router = APIRouter(prefix="/api/v1/match", tags=["match"])

class RespondRequest(BaseModel):
    proposal_id: str = Field(..., description="Unique proposal identifier from swipe match")
    action: str = Field(..., description="Action value, either 'ACCEPT' or 'DECLINE'")

class RespondResponse(BaseModel):
    status: str
    lobby_id: str | None = None

async def send_decline_push(user_ids: list[str], proposal_id: str, repo: Repository, push_client: PushClient):
    """
    Broadcasts MATCH_DECLINED push notification to both users.
    """
    for uid in user_ids:
        subscriptions = await repo.get_push_subscriptions_by_user_id(uid)
        for sub in subscriptions:
            await push_client.send_notification(
                sub,
                {"type": "MATCH_DECLINED", "proposal_id": proposal_id}
            )

async def send_success_push(target_user_id: str, lobby_id: str, repo: Repository, push_client: PushClient):
    """
    Notifies the other partner that the match was successfully accepted.
    """
    subscriptions = await repo.get_push_subscriptions_by_user_id(target_user_id)
    for sub in subscriptions:
        await push_client.send_notification(
            sub,
            {"type": "MATCH_SUCCESS", "lobby_id": lobby_id}
        )

@router.post("/respond", response_model=RespondResponse)
async def respond_to_proposal(
    payload: RespondRequest,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user_id),
    repo: Repository = Depends(get_db_repo),
    push_client: PushClient = Depends(get_push_client),
    cache: Cache = Depends(get_proposal_cache)
):
    """
    Responds to an active match proposal. If both accept, a chat lobby is generated.
    """
    if payload.action not in ("ACCEPT", "DECLINE"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action must be 'ACCEPT' or 'DECLINE'"
        )

    cache_key = f"proposal:{payload.proposal_id}"
    proposal = await cache.get(cache_key)

    # 1. Check if proposal exists
    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Proposal expired or declined"
        )

    user_a = proposal["user_a"]
    user_b = proposal["user_b"]

    # Ensure current user is part of the proposal
    if current_user_id not in (user_a, user_b):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized to respond to this proposal"
        )

    # 2. Handle DECLINE
    if payload.action == "DECLINE":
        await cache.delete(cache_key)
        # Notify both users of decline in background
        background_tasks.add_task(send_decline_push, [user_a, user_b], payload.proposal_id, repo, push_client)
        return RespondResponse(status="DECLINED")

    # 3. Handle ACCEPT
    if current_user_id == user_a:
        proposal["accepted_a"] = True
        partner_id = user_b
    else:
        proposal["accepted_b"] = True
        partner_id = user_a

    # Check if BOTH have accepted
    if proposal["accepted_a"] and proposal["accepted_b"]:
        # Success path: Create lobby and участников
        lobby_id = f"lob_{uuid.uuid4().hex[:12]}"
        await repo.create_lobby(lobby_id)
        await repo.add_lobby_participant(lobby_id, user_a)
        await repo.add_lobby_participant(lobby_id, user_b)
        
        # Evict from cache
        await cache.delete(cache_key)
        
        # Trigger success push notification to the partner in background
        background_tasks.add_task(send_success_push, partner_id, lobby_id, repo, push_client)
        
        return RespondResponse(status="SUCCESS", lobby_id=lobby_id)

    # If only one accepted, write back to cache keeping remaining TTL
    # To compute TTL, we must fetch how much time has passed.
    # However, since standard memory cache set overrides the TTL, we can store 
    # the exact absolute expiration timestamp when creating the proposal, 
    # or if it's not present, we default to 30 seconds from creation.
    # Let's add an absolute 'expires_at' field.
    now = time.time()
    if "expires_at" not in proposal:
        # If expires_at is not saved yet, calculate it (assume 30s TTL from swipe)
        proposal["expires_at"] = now + 30.0

    remaining_ttl = int(max(1.0, proposal["expires_at"] - now))
    await cache.set(cache_key, proposal, ttl=remaining_ttl)

    # 202 Accepted status code requires custom response injection or simply returning a PENDING status model
    # FastAPI parses the return schema. To return a HTTP 202 Accepted with a response body,
    # we can use the response status code setting but return the structure.
    return RespondResponse(status="PENDING")
