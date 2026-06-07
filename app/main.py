from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging
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

# Register routers
app.include_router(auth.router)
app.include_router(notifications.router)
app.include_router(candidates.router)
app.include_router(swipes.router)
app.include_router(match.router)

@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "healthy", "description": "Linder API is running"}
