import socketio
from app.core.config import settings

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.CORS_ORIGINS,
    client_manager=socketio.AsyncRedisManager(settings.REDIS_URI)
)

class WebSocketManager:
    async def emit_to_merchant_kitchen(self, merchant_id: str, event: str, data: dict):
        await sio.emit(event, data, room=f"merchant:{merchant_id}:kitchen")

    async def emit_to_order_tracking(self, order_id: str, event: str, data: dict):
        await sio.emit(event, data, room=f"order:{order_id}:tracking")

    async def emit_to_driver(self, driver_id: str, event: str, data: dict):
        await sio.emit(event, data, room=f"driver:{driver_id}")

    async def emit_to_fleet(self, merchant_id: str, event: str, data: dict):
        await sio.emit(event, data, room=f"merchant:{merchant_id}:fleet")

ws_manager = WebSocketManager()
