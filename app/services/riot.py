import logging
from typing import List, Dict, Any, Optional
import httpx
from aiocache import Cache
from app.config import settings

logger = logging.getLogger("linder.riot")

riot_cache = Cache(Cache.MEMORY)

class RiotClient:
    async def get_latest_match_id(self, puuid: str, region: str = settings.RIOT_REGION) -> Optional[str]:
        raise NotImplementedError()

    async def get_match_details(self, match_id: str, region: str = settings.RIOT_REGION) -> Optional[Dict[str, Any]]:
        raise NotImplementedError()

class ProductionRiotClient(RiotClient):
    def __init__(self, api_key: str = settings.RIOT_API_KEY):
        self.api_key = api_key
        self.http_client = httpx.AsyncClient()

    async def get_latest_match_id(self, puuid: str, region: str = settings.RIOT_REGION) -> Optional[str]:
        if not self.api_key:
            logger.error("Riot API Key is not configured.")
            return None
        
        cache_key = f"riot:latest_match:{puuid}"
        cached_match_id = await riot_cache.get(cache_key)
        if cached_match_id:
            logger.info(f"Latest match ID for PUUID {puuid} retrieved from cache.")
            return cached_match_id
        
        base_url = settings.RIOT_API_BASE_URL.format(region=region) if "{region}" in settings.RIOT_API_BASE_URL else settings.RIOT_API_BASE_URL
        url = f"{base_url}/lol/match/v5/matches/by-puuid/{puuid}/ids"
        headers = {"X-Riot-Token": self.api_key}
        params = {"start": 0, "count": 1}
        
        try:
            response = await self.http_client.get(url, headers=headers, params=params)
            response.raise_for_status()
            match_ids = response.json()
            if isinstance(match_ids, list) and len(match_ids) > 0:
                match_id = match_ids[0]
                await riot_cache.set(cache_key, match_id, ttl=60)
                return match_id
            return None
        except Exception as e:
            logger.error(f"Error fetching latest match ID for PUUID {puuid}: {e}")
            return None

    async def get_match_details(self, match_id: str, region: str = settings.RIOT_REGION) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            logger.error("Riot API Key is not configured.")
            return None

        cache_key = f"riot:match:{match_id}"
        cached_match = await riot_cache.get(cache_key)
        if cached_match:
            logger.info(f"Match {match_id} retrieved from cache.")
            return cached_match

        base_url = settings.RIOT_API_BASE_URL.format(region=region) if "{region}" in settings.RIOT_API_BASE_URL else settings.RIOT_API_BASE_URL
        url = f"{base_url}/lol/match/v5/matches/{match_id}"
        headers = {"X-Riot-Token": self.api_key}
        
        try:
            response = await self.http_client.get(url, headers=headers)
            response.raise_for_status()
            match_details = response.json()
            
            await riot_cache.set(cache_key, match_details, ttl=3600)
            return match_details
        except Exception as e:
            logger.error(f"Error fetching match details for match {match_id}: {e}")
            return None

class MockRiotClient(RiotClient):
    def __init__(self, mock_matches: Optional[Dict[str, Dict[str, Any]]] = None, mock_latest: Optional[Dict[str, str]] = None):
        self.mock_matches = mock_matches or {
            "NA1_5982385567": {
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
                        },
                        {
                            "puuid": "puuid_showmaker",
                            "riotIdGameName": "ShowMaker",
                            "riotIdTagline": "DK1",
                            "championName": "Syndra",
                            "kills": 8,
                            "deaths": 3,
                            "assists": 10,
                            "win": True,
                            "totalMinionsKilled": 210,
                            "neutralMinionsKilled": 15
                        }
                    ]
                }
            }
        }
        self.mock_latest = mock_latest or {
            "puuid_faker": "NA1_5982385567",
            "puuid_caps": "NA1_5982385567",
            "puuid_showmaker": "NA1_5982385567"
        }

    async def get_latest_match_id(self, puuid: str, region: str = settings.RIOT_REGION) -> Optional[str]:
        if puuid.startswith("puuid_user_"):
            return f"match_{puuid}"
        return self.mock_latest.get(puuid, "NA1_5982385567")

    async def get_match_details(self, match_id: str, region: str = settings.RIOT_REGION) -> Optional[Dict[str, Any]]:
        if match_id.startswith("match_puuid_user_"):
            try:
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
            except Exception:
                pass
        return self.mock_matches.get(match_id)
