from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from pydantic import BaseModel
from app.repository import Repository
from app.dependencies import get_db_repo, get_current_user_id, get_riot_client
from app.services.riot import RiotClient

router = APIRouter(prefix="/api/v1/candidates", tags=["candidates"])

class Candidate(BaseModel):
    user_id: str
    riot_id: str
    champion_name: str
    kills: int
    deaths: int
    assists: int
    win: bool
    cs: int

class CandidatesResponse(BaseModel):
    match_id: str
    candidates: List[Candidate]

@router.get("", response_model=CandidatesResponse)
async def get_candidates(
    current_user_id: str = Depends(get_current_user_id),
    repo: Repository = Depends(get_db_repo),
    riot_client: RiotClient = Depends(get_riot_client)
):
    """
    Retrieves candidates from the current user's latest League of Legends match who are also Linder users.
    """
    # 1. Look up the current user
    user = await repo.get_user_by_id(current_user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found"
        )
    
    # 2. Get latest match ID from Riot API
    match_id = await riot_client.get_latest_match_id(user["puuid"])
    if not match_id:
        return CandidatesResponse(match_id="", candidates=[])

    # 3. Get match details
    match_details = await riot_client.get_match_details(match_id)
    if not match_details or "info" not in match_details or "participants" not in match_details["info"]:
        return CandidatesResponse(match_id=match_id, candidates=[])

    participants = match_details["info"]["participants"]
    
    # 4. Extract PUUIDs of all other participants
    other_puuids = [
        p["puuid"] for p in participants 
        if p.get("puuid") and p["puuid"] != user["puuid"]
    ]
    
    if not other_puuids:
        return CandidatesResponse(match_id=match_id, candidates=[])

    # 5. Retrieve registered Linder users matching these PUUIDs
    registered_users = await repo.get_users_by_puuids(other_puuids)
    if not registered_users:
        return CandidatesResponse(match_id=match_id, candidates=[])

    # Map puuid to user info
    puuid_to_user = {u["puuid"]: u for u in registered_users}

    # 6. Optional but recommended: Filter out users the current user has already swiped on
    # Let's check which candidates have already been swiped on
    candidates_list = []
    for p in participants:
        p_puuid = p.get("puuid")
        if p_puuid in puuid_to_user:
            candidate_user = puuid_to_user[p_puuid]
            candidate_user_id = candidate_user["id"]
            
            # Check if swipe already exists
            existing_swipe = await repo.get_swipe(current_user_id, candidate_user_id)
            if existing_swipe:
                continue # Skip already swiped candidates

            # CS = totalMinionsKilled + neutralMinionsKilled
            total_cs = p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0)
            
            # Form Riot ID (Name#Tag)
            riot_id = f"{candidate_user['riot_id_name']}#{candidate_user['riot_id_tag']}"
            
            candidates_list.append(
                Candidate(
                    user_id=candidate_user_id,
                    riot_id=riot_id,
                    champion_name=p.get("championName", "Unknown"),
                    kills=p.get("kills", 0),
                    deaths=p.get("deaths", 0),
                    assists=p.get("assists", 0),
                    win=p.get("win", False),
                    cs=total_cs
                )
            )

    return CandidatesResponse(match_id=match_id, candidates=candidates_list)
