import asyncio
import random
import logging
from fastapi import FastAPI, HTTPException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("riot_stub")

app = FastAPI(title="Riot Games API Stub Server")

# Latency configuration parameters
LATENCY_MEAN_SECONDS = 0.12   # 120ms
LATENCY_STD_DEV_SECONDS = 0.03 # 30ms
LATENCY_MIN_SECONDS = 0.02     # 20ms

async def apply_simulated_latency():
    """
    Simulates network request latency using a normal distribution.
    """
    delay = random.normalvariate(LATENCY_MEAN_SECONDS, LATENCY_STD_DEV_SECONDS)
    delay = max(LATENCY_MIN_SECONDS, delay)
    logger.info(f"Simulating API latency of {delay * 1000:.1f}ms")
    await asyncio.sleep(delay)

@app.get("/lol/match/v5/matches/by-puuid/{puuid}/ids")
async def get_matches_by_puuid(puuid: str, start: int = 0, count: int = 1):
    await apply_simulated_latency()
    
    # Generate match ID matching the schema expected by the candidates service
    if puuid.startswith("puuid_user_"):
        return [f"match_{puuid}"]
    
    # Fallback to a mock match ID if puuid structure is different
    return ["NA1_5982385567"]

@app.get("/lol/match/v5/matches/{match_id}")
async def get_match_details(match_id: str):
    await apply_simulated_latency()
    
    # If it is a standard local simulated user match ID
    if match_id.startswith("match_puuid_user_"):
        try:
            # Parse user ID from match ID, e.g., "match_puuid_user_1" -> 1
            vu_id = int(match_id.split("_")[-1])
            is_user_a = (vu_id % 2 != 0)
            partner_id = vu_id + 1 if is_user_a else vu_id - 1
            
            return {
                "metadata": {"matchId": match_id},
                "info": {
                    "participants": [
                        {
                            "puuid": f"puuid_user_{vu_id}",
                            "riotIdGameName": f"User_{vu_id}",
                            "riotIdTagline": "NA1",
                            "championName": "Azir",
                            "kills": 12,
                            "deaths": 2,
                            "assists": 8,
                            "win": True,
                            "totalMinionsKilled": 200,
                            "neutralMinionsKilled": 40
                        },
                        {
                            "puuid": f"puuid_user_{partner_id}",
                            "riotIdGameName": f"User_{partner_id}",
                            "riotIdTagline": "NA1",
                            "championName": "LeBlanc",
                            "kills": 4,
                            "deaths": 6,
                            "assists": 5,
                            "win": False,
                            "totalMinionsKilled": 180,
                            "neutralMinionsKilled": 10
                        }
                    ]
                }
            }
        except Exception as e:
            logger.error(f"Failed parsing simulated user ID from match_id '{match_id}': {e}")
            raise HTTPException(status_code=400, detail="Malformed simulated match_id")
            
    # Default mock match response (fallback)
    if match_id == "NA1_5982385567":
        return {
            "metadata": {"matchId": "NA1_5982385567"},
            "info": {
                "participants": [
                    {
                        "puuid": "puuid_faker",
                        "riotIdGameName": "Faker",
                        "riotIdTagline": "KR1",
                        "championName": "Azir",
                        "kills": 12,
                        "deaths": 2,
                        "assists": 8,
                        "win": True,
                        "totalMinionsKilled": 200,
                        "neutralMinionsKilled": 40
                    },
                    {
                        "puuid": "puuid_caps",
                        "riotIdGameName": "Caps",
                        "riotIdTagline": "EUW1",
                        "championName": "LeBlanc",
                        "kills": 4,
                        "deaths": 6,
                        "assists": 5,
                        "win": False,
                        "totalMinionsKilled": 180,
                        "neutralMinionsKilled": 10
                    }
                ]
            }
        }

    raise HTTPException(status_code=404, detail="Match not found")
