from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, horoscope, profile
from app.core.config import settings
from app.core.database import engine
from app.core.redis import redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # SECURITY: Validate critical configuration at startup
    if settings.JWT_SECRET_KEY in ("change-me-to-a-random-secret-key", "CHANGE_ME_MUST_BE_RANDOM", ""):
        raise RuntimeError(
            "CRITICAL: JWT_SECRET_KEY must be set to a strong random value in .env. "
            "Generate one with: openssl rand -hex 32"
        )
    if len(settings.JWT_SECRET_KEY) < 32:
        raise RuntimeError(
            "CRITICAL: JWT_SECRET_KEY is too short. Use at least 32 characters."
        )

    # Startup: verify connections
    # Redis ping
    await redis_client.ping()
    yield
    # Shutdown: close connections
    await redis_client.close()
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered personalized horoscope service",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(profile.router, prefix="/api/v1")
app.include_router(horoscope.router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }
