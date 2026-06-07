import asyncio
import time
import httpx
import subprocess
import os
import random

BASE_URL = "http://localhost:8085/api/v1"

async def register_user(client: httpx.AsyncClient, vu_id: int, sem: asyncio.Semaphore):
    """
    Registers a single user in the database.
    """
    async with sem:
        try:
            res = await client.post(
                f"{BASE_URL}/auth/token",
                json={
                    "puuid": f"puuid_user_{vu_id}",
                    "riot_id_name": f"User_{vu_id}",
                    "riot_id_tag": "NA1"
                }
            )
            return res.status_code == 200
        except Exception:
            return False

async def run_pair_match_flow(client: httpx.AsyncClient, vu_a_id: int, latencies: list):
    """
    Simulates the full matching handshake for a pair (vu_a_id and vu_b_id):
    1. User A queries candidates (sees User B)
    2. User A swipes LIKE on User B (matched = False)
    3. User B queries candidates (sees User A)
    4. User B swipes LIKE on User A (matched = True, returns proposal_id)
    5. User B responds ACCEPT (status = PENDING)
    6. User A responds ACCEPT (status = SUCCESS, lobby created)
    """
    vu_b_id = vu_a_id + 1
    
    headers_a = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer mock_token_user_usr_{vu_a_id}"
    }
    
    headers_b = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer mock_token_user_usr_{vu_b_id}"
    }

    try:
        # Introduce a small initial stagger to distribute requests
        await asyncio.sleep(random.uniform(0.0, 5.0))

        # --- USER A SWIPE ---
        # 1. User A checks candidates
        t0 = time.perf_counter()
        res = await client.get(f"{BASE_URL}/candidates", headers=headers_a)
        latencies.append(time.perf_counter() - t0)
        if res.status_code != 200:
            return False, f"cand_a_fail_{res.status_code}"
            
        cands = res.json().get("candidates", [])
        if not cands:
            return False, "cand_a_empty"
        partner_b_db_id = cands[0]["user_id"]

        # 2. User A swipes LIKE on User B
        t0 = time.perf_counter()
        res = await client.post(
            f"{BASE_URL}/swipes",
            json={"target_user_id": partner_b_db_id, "action": "LIKE"},
            headers=headers_a
        )
        latencies.append(time.perf_counter() - t0)
        if res.status_code != 200:
            return False, f"swipe_a_fail_{res.status_code}"
        assert res.json()["matched"] is False

        # --- USER B SWIPE ---
        # 3. User B checks candidates
        t0 = time.perf_counter()
        res = await client.get(f"{BASE_URL}/candidates", headers=headers_b)
        latencies.append(time.perf_counter() - t0)
        if res.status_code != 200:
            return False, f"cand_b_fail_{res.status_code}"
            
        cands = res.json().get("candidates", [])
        if not cands:
            return False, "cand_b_empty"
        partner_a_db_id = cands[0]["user_id"]

        # 4. User B swipes LIKE on User A (triggers match)
        t0 = time.perf_counter()
        res = await client.post(
            f"{BASE_URL}/swipes",
            json={"target_user_id": partner_a_db_id, "action": "LIKE"},
            headers=headers_b
        )
        latencies.append(time.perf_counter() - t0)
        if res.status_code != 200:
            return False, f"swipe_b_fail_{res.status_code}"
            
        swipe_data = res.json()
        if not swipe_data.get("matched"):
            return False, "no_match_triggered"
        proposal_id = swipe_data.get("proposal_id")

        # --- HANDSHAKE ---
        # 5. User B responds ACCEPT
        t0 = time.perf_counter()
        res = await client.post(
            f"{BASE_URL}/match/respond",
            json={"proposal_id": proposal_id, "action": "ACCEPT"},
            headers=headers_b
        )
        latencies.append(time.perf_counter() - t0)
        if res.status_code not in (200, 202):
            return False, f"respond_b_fail_{res.status_code}"

        # 6. User A responds ACCEPT (completes match)
        t0 = time.perf_counter()
        res = await client.post(
            f"{BASE_URL}/match/respond",
            json={"proposal_id": proposal_id, "action": "ACCEPT"},
            headers=headers_a
        )
        latencies.append(time.perf_counter() - t0)
        if res.status_code not in (200, 202):
            return False, f"respond_a_fail_{res.status_code}"

        return True, "success"

    except Exception as e:
        return False, f"exception: {type(e).__name__} - {str(e)}"

async def main():
    print("Starting Linder Local Stress Test...")
    
    # 1. Clean persistent database files from previous runs
    for db_file in ["linder.db", "linder.db-wal", "linder.db-shm"]:
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except Exception:
                pass
                
    print("Spawning FastAPI server in background...")
    log_file = open("uvicorn_stress.log", "w")
    server_process = subprocess.Popen(
        [r".venv\Scripts\python.exe", "-m", "uvicorn", "app.main:app", "--port", "8085", "--log-level", "info"],
        stdout=log_file,
        stderr=log_file
    )
    
    # Wait for server to boot up
    time.sleep(3)
    
    # Setup HTTPX client
    limits = httpx.Limits(max_keepalive_connections=200, max_connections=300)
    async with httpx.AsyncClient(limits=limits, timeout=30.0) as client:
        
        # --- PHASE 1: REGISTER ALL USERS ---
        print("PHASE 1: Registering 200 users sequentially/semi-concurrently...")
        sem = asyncio.Semaphore(15) # rate limit registrations to prevent socket queue clog
        reg_tasks = [register_user(client, i, sem) for i in range(1, 201)]
        t_reg_start = time.perf_counter()
        reg_results = await asyncio.gather(*reg_tasks)
        t_reg_end = time.perf_counter()
        
        failed_regs = len([r for r in reg_results if not r])
        print(f"Phase 1 complete in {t_reg_end - t_reg_start:.2f}s. Failed registrations: {failed_regs}")
        
        # Give database a brief moment to settle
        await asyncio.sleep(1.0)

        # --- PHASE 2: RUN MATCH FLOW FOR 100 PAIRS ---
        print("PHASE 2: Running matching flow for 100 pairs concurrently...")
        latencies = []
        # Run pairs (1 & 2), (3 & 4), ..., (199 & 200)
        tasks = [run_pair_match_flow(client, i, latencies) for i in range(1, 201, 2)]
        
        t_match_start = time.perf_counter()
        match_results = await asyncio.gather(*tasks)
        t_match_end = time.perf_counter()
        
    # Terminate server process
    server_process.terminate()
    server_process.wait()
    log_file.close()
    
    total_time = t_match_end - t_match_start
    print("\nStress Test Results:")
    print(f"Total simulated pairs: 100")
    print(f"Total time elapsed: {total_time:.2f} seconds")
    
    success_count = 0
    errors = {}
    for ok, err_type in match_results:
        if ok:
            success_count += 1
        else:
            errors[err_type] = errors.get(err_type, 0) + 1
            
    print(f"Successful pairs matched: {success_count} / 100")
    if errors:
        print(f"Errors: {errors}")
        
    if latencies:
        latencies_ms = sorted([l * 1000 for l in latencies])
        n = len(latencies_ms)
        p95 = latencies_ms[int(n * 0.95)]
        p99 = latencies_ms[int(n * 0.99)]
        avg = sum(latencies_ms) / n
        print(f"Average request latency: {avg:.2f}ms")
        print(f"p95 request latency: {p95:.2f}ms")
        print(f"p99 request latency: {p99:.2f}ms")
        
        # Verify success metrics (p95 request latency remains < 150ms during peak load)
        if p95 < 150.0 and success_count == 100 and failed_regs == 0:
            print("\nSUCCESS: Target metrics hit! p95 latency is under 150ms, error rate is 0%, and all handshakes succeeded.")
        else:
            print("\nWARNING: Target metrics not fully met. Check log/output above.")

if __name__ == "__main__":
    asyncio.run(main())
