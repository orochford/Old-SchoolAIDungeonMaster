from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import socketio
import logging
import traceback

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

logger = logging.getLogger(__name__)

from app.config import settings
from app.core.database import init_db

# Import all models to ensure relationships are registered
# This must happen before any database queries
from app.domains.campaigns import models as campaigns_models
from app.domains.characters import models as characters_models
from app.domains.sessions import models as sessions_models
from app.domains.combat import models as combat_models
from app.domains.npcs import models as npcs_models
from app.domains.inventory import models as inventory_models
from app.domains.sourcebooks import models as sourcebooks_models
from app.domains.journal import models as journal_models
from app.domains.spells import models as spells_models
from app.domains.adventures import models as adventures_models

# Socket.IO server
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    ping_interval=settings.ws_ping_interval,
    ping_timeout=settings.ws_ping_timeout,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown


app = FastAPI(
    title=settings.app_name,
    description="Solo RPG Platform with LLM Dungeon Master",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://192.168.1.100:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
    )


# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "app": settings.app_name}


# Settings endpoint for API keys
from pydantic import BaseModel
from typing import Optional

class APIKeysUpdate(BaseModel):
    openai_api_key: Optional[str] = None
    claude_api_key: Optional[str] = None
    # GM AI settings
    gm_provider: Optional[str] = None  # 'claude' or 'openai'
    gm_claude_model: Optional[str] = None
    gm_openai_model: Optional[str] = None
    # Processing AI settings
    processing_provider: Optional[str] = None  # 'claude' or 'openai'
    processing_claude_model: Optional[str] = None
    processing_openai_model: Optional[str] = None

@app.post(f"{settings.api_v1_prefix}/settings/keys")
async def update_api_keys(keys: APIKeysUpdate):
    """Update API keys and AI settings at runtime."""
    import app.config as config_module
    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"Updating settings - GM provider: {keys.gm_provider}, GM model: {keys.gm_openai_model or keys.gm_claude_model}")

    if keys.openai_api_key is not None:
        config_module.settings.openai_api_key = keys.openai_api_key
    if keys.claude_api_key is not None:
        config_module.settings.anthropic_api_key = keys.claude_api_key

    # GM AI settings
    if keys.gm_provider is not None:
        config_module.settings.gm_provider = keys.gm_provider
        logger.info(f"Set GM provider to: {config_module.settings.gm_provider}")
    if keys.gm_claude_model is not None:
        config_module.settings.gm_claude_model = keys.gm_claude_model
    if keys.gm_openai_model is not None:
        config_module.settings.gm_openai_model = keys.gm_openai_model

    # Processing AI settings
    if keys.processing_provider is not None:
        config_module.settings.processing_provider = keys.processing_provider
    if keys.processing_claude_model is not None:
        config_module.settings.processing_claude_model = keys.processing_claude_model
    if keys.processing_openai_model is not None:
        config_module.settings.processing_openai_model = keys.processing_openai_model

    return {"status": "updated"}

@app.get(f"{settings.api_v1_prefix}/settings/keys")
async def get_api_keys_status():
    """Check if API keys are configured (doesn't return actual keys)."""
    return {
        "openai_configured": bool(settings.openai_api_key),
        "claude_configured": bool(settings.anthropic_api_key),
    }

@app.get(f"{settings.api_v1_prefix}/settings/ai-config")
async def get_ai_config():
    """Get current AI configuration (for debugging)."""
    return {
        "gm_provider": settings.gm_provider,
        "gm_claude_model": settings.gm_claude_model,
        "gm_openai_model": settings.gm_openai_model,
        "processing_provider": settings.processing_provider,
        "processing_claude_model": settings.processing_claude_model,
        "processing_openai_model": settings.processing_openai_model,
    }

@app.post(f"{settings.api_v1_prefix}/settings/test-openai")
async def test_openai_key():
    """Test if OpenAI API key works."""
    import httpx
    if not settings.openai_api_key:
        return {"success": False, "error": "No API key configured"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                timeout=10.0,
            )
            if response.status_code == 200:
                return {"success": True}
            else:
                return {"success": False, "error": f"API returned {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post(f"{settings.api_v1_prefix}/settings/test-claude")
async def test_claude_key():
    """Test if Anthropic API key works."""
    import httpx
    if not settings.anthropic_api_key:
        return {"success": False, "error": "No API key configured"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                timeout=15.0,
            )
            if response.status_code == 200:
                return {"success": True}
            else:
                data = response.json()
                return {"success": False, "error": data.get("error", {}).get("message", f"API returned {response.status_code}")}
    except Exception as e:
        return {"success": False, "error": str(e)}


# Import and include routers
from app.domains.characters.router import router as characters_router
from app.domains.campaigns.router import router as campaigns_router
from app.domains.sessions.router import router as sessions_router
from app.domains.combat.router import router as combat_router
from app.domains.sourcebooks.router import router as sourcebooks_router
from app.domains.journal.router import router as journal_router
from app.domains.maps.router import router as maps_router
from app.domains.spells.router import router as spells_router
from app.domains.adventures.router import router as adventures_router

app.include_router(characters_router, prefix=f"{settings.api_v1_prefix}/characters", tags=["characters"])
app.include_router(campaigns_router, prefix=f"{settings.api_v1_prefix}/campaigns", tags=["campaigns"])
app.include_router(sessions_router, prefix=f"{settings.api_v1_prefix}/sessions", tags=["sessions"])
app.include_router(combat_router, prefix=f"{settings.api_v1_prefix}/combat", tags=["combat"])
app.include_router(sourcebooks_router, prefix=f"{settings.api_v1_prefix}/sourcebooks", tags=["sourcebooks"])
app.include_router(journal_router, prefix=f"{settings.api_v1_prefix}/journal", tags=["journal"])
app.include_router(maps_router, prefix=f"{settings.api_v1_prefix}/maps", tags=["maps"])
app.include_router(spells_router, prefix=f"{settings.api_v1_prefix}/spells", tags=["spells"])
app.include_router(adventures_router, prefix=f"{settings.api_v1_prefix}/adventures", tags=["adventures"])

# Mount Socket.IO
socket_app = socketio.ASGIApp(sio, app)


# Socket.IO event handlers
@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")


@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")


@sio.event
async def join_session(sid, data):
    session_id = data.get("session_id")
    if session_id:
        await sio.enter_room(sid, f"session_{session_id}")
        await sio.emit("session_joined", {"session_id": session_id}, to=sid)


@sio.event
async def leave_session(sid, data):
    session_id = data.get("session_id")
    if session_id:
        await sio.leave_room(sid, f"session_{session_id}")


# Application entry point for uvicorn
application = socket_app
