"""
Phase 12 — Health Check Endpoints
Kubernetes probes + comprehensive service health
"""

from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db
import redis.asyncio as redis
import os

router = APIRouter(prefix="/health", tags=["health"])

@router.get("")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Comprehensive health check for monitoring."""
    status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0",
        "services": {}
    }

    # Database check
    try:
        await db.execute(text("SELECT 1"))
        status["services"]["database"] = {"status": "up", "latency_ms": 0}
    except Exception as e:
        status["services"]["database"] = {"status": "down", "error": str(e)}
        status["status"] = "degraded"

    # Redis check
    try:
        redis_client = redis.from_url(os.getenv("REDIS_URI", "redis://localhost:6379")
        await redis_client.ping()
        await redis_client.close()
        status["services"]["redis"] = {"status": "up"}
    except Exception as e:
        status["services"]["redis"] = {"status": "down", "error": str(e)}
        status["status"] = "degraded"

    # Celery check (optional)
    try:
        from app.core.celery_app import celery_app
        inspector = celery_app.control.inspect()
        active = inspector.active()
        status["services"]["celery"] = {"status": "up", "workers": len(active) if active else 0}
    except Exception as e:
        status["services"]["celery"] = {"status": "down", "error": str(e)}

    return status

@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Kubernetes readiness probe."""
    try:
        await db.execute(text("SELECT 1"))
        return {"ready": True}
    except:
        return {"ready": False}

@router.get("/live")
async def liveness_check():
    """Kubernetes liveness probe."""
    return {"alive": True}
