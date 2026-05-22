from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.events import startup_event, shutdown_event
from app.websocket.manager import sio, socketio

@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup_event()
    yield
    await shutdown_event()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount Socket.IO
app.mount("/ws", socketio.ASGIApp(sio))

# ─── FRONTEND SPA ROUTES ───────────────────────────────────────────

@app.get("/menu/{merchant_id}")
async def customer_pwa(merchant_id: str):
    """Customer PWA — QR scan menu, cart, checkout, order tracking."""
    return FileResponse("static/customer-pwa/index.html")

@app.get("/portal")
async def merchant_portal():
    """Merchant Portal — dashboard, orders, menu, analytics, fleet."""
    return FileResponse("static/merchant-portal/index.html")

@app.get("/kds")
async def kds_display():
    """KDS Display — real-time kitchen order cards with timers."""
    return FileResponse("static/kds-display/index.html")

@app.get("/driver")
async def driver_app():
    """Driver Mobile App — GPS tracking, active orders, earnings."""
    return FileResponse("static/driver-app/index.html")

# Health checks are served via api_router at /api/v1/health/*
