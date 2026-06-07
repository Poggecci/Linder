import os
import sys
import time
import httpx
import subprocess
import shutil
import ctypes

LINDER_PORT = 8085
STUB_PORT = 8086
LINDER_URL = f"http://localhost:{LINDER_PORT}"
STUB_URL = f"http://localhost:{STUB_PORT}"

def set_affinity(pid: int, mask: int):
    """
    Applies a processor affinity mask to a process on Windows using ctypes.
    """
    if sys.platform != "win32":
        return
        
    PROCESS_SET_INFORMATION = 0x0200
    PROCESS_QUERY_INFORMATION = 0x0400
    
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_SET_INFORMATION | PROCESS_QUERY_INFORMATION, 
        False, 
        pid
    )
    if handle:
        try:
            success = ctypes.windll.kernel32.SetProcessAffinityMask(handle, mask)
            if success:
                print(f"[Orchestrator] Bound PID {pid} to affinity mask {mask} (binary: {bin(mask)})")
            else:
                print(f"[Orchestrator] Warning: Failed to set affinity mask on PID {pid}")
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    else:
        print(f"[Orchestrator] Warning: Could not open process handle for PID {pid}")

def cleanup_db():
    print("[Orchestrator] Cleaning up existing SQLite files...")
    for db_file in ["linder.db", "linder.db-wal", "linder.db-shm"]:
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
                print(f"[Orchestrator] Removed {db_file}")
            except Exception as e:
                print(f"[Orchestrator] Warning: Could not remove {db_file}: {e}")

def wait_for_server(url: str, name: str, timeout: int = 10):
    print(f"[Orchestrator] Waiting for {name} ({url}) to respond...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            res = httpx.get(url, timeout=1.0)
            if res.status_code < 500:
                print(f"[Orchestrator] {name} is ready!")
                return True
        except httpx.RequestError:
            pass
        time.sleep(0.5)
    print(f"[Orchestrator] Error: Timeout waiting for {name} after {timeout} seconds.")
    return False

def analyze_profiles(profile_dir: str):
    print("\n" + "="*50)
    print("[Orchestrator] ANALYZING PROFILED REQUESTS...")
    print("="*50)
    
    if not os.path.exists(profile_dir):
        print("No profiles directory found.")
        return
        
    txt_files = [f for f in os.listdir(profile_dir) if f.endswith(".txt")]
    if not txt_files:
        print("No profile data was generated. Make sure load_test.js passes '?profile=true' query parameters.")
        return
        
    profiles = []
    for filename in txt_files:
        filepath = os.path.join(profile_dir, filename)
        # Reconstruct method and path from filename: {method}_{safe_path}_{timestamp}.txt
        parts = filename.replace(".txt", "").split("_")
        method = parts[0]
        path = "/" + "/".join(parts[1:-1])
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            duration = None
            for line in content.splitlines():
                if "Duration:" in line:
                    parts_line = line.split()
                    try:
                        idx = parts_line.index("Duration:")
                        duration = float(parts_line[idx+1])
                    except (ValueError, IndexError):
                        pass
                    break
            
            if duration is not None:
                profiles.append({
                    "filename": filename,
                    "filepath": filepath,
                    "method": method,
                    "path": path,
                    "duration": duration,
                    "content": content
                })
        except Exception as e:
            print(f"Error parsing profile {filename}: {e}")
            
    if not profiles:
        print("Could not parse durations from any profile files.")
        return
        
    # Sort by duration descending
    profiles.sort(key=lambda x: x["duration"], reverse=True)
    
    print(f"Analyzed {len(profiles)} profiled requests.")
    print(f"Slowest request: {profiles[0]['method']} {profiles[0]['path']} ({profiles[0]['duration'] * 1000:.1f}ms)")
    
    # Print Top 3 Slowest Requests
    top_n = min(3, len(profiles))
    print(f"\n--- TOP {top_n} SLOWEST REQUEST BREAKDOWNS (CALL TREE) ---")
    for i in range(top_n):
        p = profiles[i]
        print(f"\n[{i+1}] {p['method']} {p['path']} | Duration: {p['duration'] * 1000:.1f}ms")
        print(f"Profile file: {os.path.abspath(os.path.join(profile_dir, p['filename'].replace('.txt', '.html')))}")
        print("Execution Path (Call Tree):")
        print("-" * 50)
        
        # Print first 15 lines of call tree starting at the root call (first line with a float prefix)
        lines = p["content"].splitlines()
        call_tree_started = False
        printed_lines = 0
        for line in lines:
            if not call_tree_started:
                parts_tree = line.strip().split()
                if parts_tree:
                    try:
                        float(parts_tree[0])
                        call_tree_started = True
                    except ValueError:
                        pass
            
            if call_tree_started:
                print(line)
                printed_lines += 1
                if printed_lines >= 15:
                    break
        print("-" * 50)
        
    print(f"\n[Orchestrator] Detailed HTML flame graphs are saved in the '{profile_dir}' directory.")
    print("Open any of the .html files in your browser to inspect the interactive flame graph.")

def main():
    cleanup_db()

    # Load profiling secret from .env file
    from dotenv import dotenv_values
    env_config = dotenv_values(".env")
    profiling_secret = env_config.get("PROFILING_SECRET", "744cdb529cf834d96d4ed61aea0b58d0")

    # Clear and setup profiles directory
    profile_dir = "profiles"
    if os.path.exists(profile_dir):
        shutil.rmtree(profile_dir)
    os.makedirs(profile_dir, exist_ok=True)

    # Determine CPU core count and affinity applicability
    num_cores = os.cpu_count() or 1
    apply_affinity = (sys.platform == "win32" and num_cores >= 3)
    
    if apply_affinity:
        print(f"[Orchestrator] Detected {num_cores} cores. Core affinity mapping is ENABLED.")
    else:
        print(f"[Orchestrator] Core affinity mapping is DISABLED (OS: {sys.platform}, Cores: {num_cores}).")

    linder_log = open("linder_server.log", "w")
    stub_log = open("riot_stub_server.log", "w")

    # 1. Spawn Riot API Stub Server on Port 8086
    print(f"[Orchestrator] Spawning Riot API Stub Server on port {STUB_PORT}...")
    stub_proc = subprocess.Popen(
        ["uv", "run", "python", "-m", "uvicorn", "riot_stub:app", "--port", str(STUB_PORT), "--log-level", "info"],
        stdout=stub_log,
        stderr=stub_log
    )
    if apply_affinity:
        set_affinity(stub_proc.pid, 4)  # Core 2

    # 2. Spawn Linder API Server on Port 8085 (single process)
    env = os.environ.copy()
    env["ENVIRONMENT"] = "development"
    env["DATABASE_PATH"] = "linder.db"
    env["RIOT_API_KEY"] = "dummy_loadtest_key"
    env["RIOT_API_BASE_URL"] = STUB_URL
    env["VAPID_PRIVATE_KEY"] = ""  # Force MockPushClient
    env["PROFILE_DIR"] = profile_dir  # Save profiles here
    env["PROFILING_SECRET"] = profiling_secret
    
    print(f"[Orchestrator] Spawning Linder API Server on port {LINDER_PORT}...")
    linder_proc = subprocess.Popen(
        ["uv", "run", "python", "-m", "uvicorn", "app.main:app", "--port", str(LINDER_PORT), "--log-level", "info"],
        stdout=linder_log,
        stderr=linder_log,
        env=env
    )
    if apply_affinity:
        set_affinity(linder_proc.pid, 1)  # Core 0

    try:
        # 3. Wait for endpoints to respond
        stub_ready = wait_for_server(f"{STUB_URL}/openapi.json", "Riot API Stub Server")
        linder_ready = wait_for_server(f"{LINDER_URL}/health", "Linder API Server")

        if not (stub_ready and linder_ready):
            print("[Orchestrator] Error: One or more servers failed to boot. Aborting test.")
            return

        # 4. Check for k6 CLI
        k6_path = shutil.which("k6")
        if not k6_path:
            default_path = r"C:\Program Files\k6\k6.exe"
            if os.path.exists(default_path):
                k6_path = default_path
                print(f"[Orchestrator] Found k6 at default path: {k6_path}")
            else:
                print("\n[Orchestrator] ERROR: 'k6' CLI tool was not found on your system.")
                print("[Orchestrator] Please install k6 to run load tests. On Windows, you can run:")
                print("[Orchestrator]     winget install GrafanaLabs.k6")
                print("[Orchestrator] (Note: You may need to reopen the terminal after installation)\n")
                return

        # 5. Execute k6
        print("[Orchestrator] Running k6 load test script 'load_test.js'...")
        k6_cmd = [k6_path, "run", "load_test.js"]
        
        k6_env = os.environ.copy()
        k6_env["PROFILING_SECRET"] = profiling_secret
        k6_proc = subprocess.Popen(k6_cmd, env=k6_env)
        if apply_affinity:
            set_affinity(k6_proc.pid, 2)  # Core 1
            
        k6_returncode = k6_proc.wait()
        print(f"[Orchestrator] k6 run finished with exit code {k6_returncode}")

        # 6. Analyze profiles if generated
        analyze_profiles(profile_dir)

    except KeyboardInterrupt:
        print("[Orchestrator] Execution interrupted by user. Stopping servers...")
    finally:
        # 7. Tear down servers
        print("[Orchestrator] Shutting down servers...")
        linder_proc.terminate()
        stub_proc.terminate()
        
        linder_proc.wait()
        stub_proc.wait()
        
        linder_log.close()
        stub_log.close()
        print("[Orchestrator] Servers shut down successfully.")

if __name__ == "__main__":
    main()
