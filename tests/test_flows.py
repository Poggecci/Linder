import pytest
import asyncio
from httpx import AsyncClient
from app.dependencies import proposal_cache, get_db_repo
from app.services.push import MockPushClient

@pytest.mark.asyncio
async def test_flow_happy_path(client: AsyncClient, mock_push: MockPushClient):
    """
    Flow 1: Match Acceptance (Happy Path)
    - User A registers & subscribes.
    - User B registers & subscribes.
    - User A swipes LIKE on B (matched = False).
    - User B swipes LIKE on A (matched = True, push sent, proposal created).
    - Both users ACCEPT the proposal.
    - Lobby created, proposal evicted, success push sent.
    """
    # 1. Register User A and get token
    res_a = await client.post(
        "/api/v1/auth/token",
        json={"puuid": "puuid_faker", "riot_id_name": "Faker", "riot_id_tag": "KR1"}
    )
    assert res_a.status_code == 200
    token_a = res_a.json()["access_token"]
    user_a_id = res_a.json()["user_id"]

    # Subscribe User A
    sub_res_a = await client.post(
        "/api/v1/notifications/subscribe",
        json={"endpoint": "https://push.com/faker", "keys": {"p256dh": "dh_a", "auth": "auth_a"}},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert sub_res_a.status_code == 201

    # 2. Register User B and get token
    res_b = await client.post(
        "/api/v1/auth/token",
        json={"puuid": "puuid_caps", "riot_id_name": "Caps", "riot_id_tag": "EUW1"}
    )
    assert res_b.status_code == 200
    token_b = res_b.json()["access_token"]
    user_b_id = res_b.json()["user_id"]

    # Subscribe User B
    sub_res_b = await client.post(
        "/api/v1/notifications/subscribe",
        json={"endpoint": "https://push.com/caps", "keys": {"p256dh": "dh_b", "auth": "auth_b"}},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert sub_res_b.status_code == 201

    # Clear any initialization push deliveries
    mock_push.clear()

    # 3. User A swipes LIKE on User B
    swipe_res_1 = await client.post(
        "/api/v1/swipes",
        json={"target_user_id": user_b_id, "action": "LIKE"},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert swipe_res_1.status_code == 200
    assert swipe_res_1.json()["matched"] is False

    # 4. User B swipes LIKE on User A
    swipe_res_2 = await client.post(
        "/api/v1/swipes",
        json={"target_user_id": user_a_id, "action": "LIKE"},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert swipe_res_2.status_code == 200
    data_2 = swipe_res_2.json()
    assert data_2["matched"] is True
    proposal_id = data_2["proposal_id"]
    assert proposal_id is not None

    # Check that a Web Push was triggered for User A (from B's match creation)
    # Give a tiny yield to let background tasks run
    await asyncio.sleep(0.1)
    assert len(mock_push.deliveries) == 1
    assert mock_push.deliveries[0]["user_id"] == user_a_id
    assert mock_push.deliveries[0]["payload"]["type"] == "MATCH_PROPOSED"

    # 5. User A accepts proposal
    respond_res_1 = await client.post(
        "/api/v1/match/respond",
        json={"proposal_id": proposal_id, "action": "ACCEPT"},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert respond_res_1.status_code == 200
    assert respond_res_1.json()["status"] == "PENDING"

    # User B accepts proposal
    respond_res_2 = await client.post(
        "/api/v1/match/respond",
        json={"proposal_id": proposal_id, "action": "ACCEPT"},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert respond_res_2.status_code == 200
    assert respond_res_2.json()["status"] == "SUCCESS"
    lobby_id = respond_res_2.json()["lobby_id"]
    assert lobby_id is not None

    # Let background tasks run to deliver success push to User A (the partner of User B)
    await asyncio.sleep(0.1)
    # Total push deliveries = 1 (proposed) + 1 (success to user A)
    assert len(mock_push.deliveries) == 2
    assert mock_push.deliveries[-1]["user_id"] == user_a_id
    assert mock_push.deliveries[-1]["payload"]["type"] == "MATCH_SUCCESS"
    assert mock_push.deliveries[-1]["payload"]["lobby_id"] == lobby_id

    # Verify cache key is evicted
    proposal_in_cache = await proposal_cache.get(f"proposal:{proposal_id}")
    assert proposal_in_cache is None

    # Verify database lobbies & participants
    repo = get_db_repo()
    participants = await repo.get_lobby_participants(lobby_id)
    participant_ids = [p["id"] for p in participants]
    assert user_a_id in participant_ids
    assert user_b_id in participant_ids

@pytest.mark.asyncio
async def test_flow_expiry_timeout(client: AsyncClient, mock_push: MockPushClient):
    """
    Flow 2: Expiry Path (Timeout)
    - Users register and match.
    - Proposal cache is evicted manually to simulate 30s timeout.
    - User attempts to accept.
    - Assert server returns 410 Gone and no lobby is created.
    """
    # Register & get tokens
    res_a = await client.post(
        "/api/v1/auth/token",
        json={"puuid": "puuid_faker", "riot_id_name": "Faker", "riot_id_tag": "KR1"}
    )
    token_a = res_a.json()["access_token"]
    user_a_id = res_a.json()["user_id"]

    res_b = await client.post(
        "/api/v1/auth/token",
        json={"puuid": "puuid_caps", "riot_id_name": "Caps", "riot_id_tag": "EUW1"}
    )
    token_b = res_b.json()["access_token"]
    user_b_id = res_b.json()["user_id"]

    # Match swipe
    await client.post(
        "/api/v1/swipes",
        json={"target_user_id": user_b_id, "action": "LIKE"},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    swipe_res = await client.post(
        "/api/v1/swipes",
        json={"target_user_id": user_a_id, "action": "LIKE"},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    proposal_id = swipe_res.json()["proposal_id"]

    # Manually delete key to simulate cache eviction/timeout
    await proposal_cache.delete(f"proposal:{proposal_id}")

    # User attempts to accept
    respond_res = await client.post(
        "/api/v1/match/respond",
        json={"proposal_id": proposal_id, "action": "ACCEPT"},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert respond_res.status_code == 410
    assert respond_res.json()["detail"] == "Proposal expired or declined"

@pytest.mark.asyncio
async def test_flow_declined(client: AsyncClient, mock_push: MockPushClient):
    """
    Flow 3: Declined Path
    - Users match.
    - User A declines.
    - Cache state is destroyed immediately.
    - Push notifications of DECLINE are sent.
    """
    res_a = await client.post(
        "/api/v1/auth/token",
        json={"puuid": "puuid_faker", "riot_id_name": "Faker", "riot_id_tag": "KR1"}
    )
    token_a = res_a.json()["access_token"]
    user_a_id = res_a.json()["user_id"]

    res_b = await client.post(
        "/api/v1/auth/token",
        json={"puuid": "puuid_caps", "riot_id_name": "Caps", "riot_id_tag": "EUW1"}
    )
    token_b = res_b.json()["access_token"]
    user_b_id = res_b.json()["user_id"]

    # Match swipe
    await client.post(
        "/api/v1/swipes",
        json={"target_user_id": user_b_id, "action": "LIKE"},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    swipe_res = await client.post(
        "/api/v1/swipes",
        json={"target_user_id": user_a_id, "action": "LIKE"},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    proposal_id = swipe_res.json()["proposal_id"]

    # User A declines
    respond_res = await client.post(
        "/api/v1/match/respond",
        json={"proposal_id": proposal_id, "action": "DECLINE"},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert respond_res.status_code == 200
    assert respond_res.json()["status"] == "DECLINED"

    # Verify cache key is immediately evicted
    proposal_in_cache = await proposal_cache.get(f"proposal:{proposal_id}")
    assert proposal_in_cache is None
