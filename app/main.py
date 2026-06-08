from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import logging
import os
import time
import asyncio
from pyinstrument import Profiler
from app.config import settings
from app.db import Database
from app.routes import auth, notifications, candidates, swipes, match

logger = logging.getLogger("linder.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan handler to initialize the database schema on server startup.
    """
    logger.info("Server starting up...")
    db = Database()
    await db.init_db()
    yield
    logger.info("Server shutting down...")

app = FastAPI(
    title="Linder Prototype API",
    description="Stateless Backend API for the League of Legends Matchmaking/Dating Client MVP",
    version="1.0.0",
    lifespan=lifespan
)

@app.middleware("http")
async def profile_request(request: Request, call_next):
    # Determine if request profiling is enabled
    profile_param = request.query_params.get("profile")
    should_profile = False
    
    if settings.PROFILING_SECRET:
        should_profile = (profile_param == settings.PROFILING_SECRET)
    else:
        # Fallback to simple query param in dev if no secret is configured
        should_profile = (profile_param == "true")
        
    if should_profile:
        profiler = Profiler(async_mode="enabled")
        profiler.start()
        
        response = await call_next(request)
        
        profiler.stop()
        
        profile_dir = os.getenv("PROFILE_DIR")
        if profile_dir:
            os.makedirs(profile_dir, exist_ok=True)
            # Create a safe filename (e.g. GET_api_v1_candidates_1717800000)
            safe_path = request.url.path.strip("/").replace("/", "_") or "root"
            timestamp = int(time.time() * 1000)
            filename = f"{request.method}_{safe_path}_{timestamp}"
            
            # Offload CPU-bound profiling text and HTML generation to thread pool
            html_content = await asyncio.to_thread(profiler.output_html)
            text_content = await asyncio.to_thread(profiler.output_text)
            
            # Write HTML report
            html_path = os.path.join(profile_dir, f"{filename}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
                
            # Write text report for parsing/analysis
            text_path = os.path.join(profile_dir, f"{filename}.txt")
            with open(text_path, "w", encoding="utf-8") as f:
                f.write(text_content)
                
            return response
        else:
            # Return an interactive HTML report directly in the browser
            html_content = await asyncio.to_thread(profiler.output_html)
            return HTMLResponse(html_content)
    
    return await call_next(request)

from fastapi.middleware.cors import CORSMiddleware

# Register CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(notifications.router)
app.include_router(candidates.router)
app.include_router(swipes.router)
app.include_router(match.router)

@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "healthy", "description": "Linder API is running"}
