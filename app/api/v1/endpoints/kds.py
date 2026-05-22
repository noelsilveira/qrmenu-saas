import json
from datetime import datetime
from typing import Dict, Set
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import decode_token
from app.models import Order, OrderItem
from app.services.order_service import OrderService

router = APIRouter()


class KDSConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, merchant_id: str):
        await websocket.accept()
        if merchant_id not in self.active_connections:
            self.active_connections[merchant_id] = set()
        self.active_connections[merchant_id].add(websocket)

    def disconnect(self, websocket: WebSocket, merchant_id: str):
        if merchant_id in self.active_connections:
            self.active_connections[merchant_id].discard(websocket)
            if not self.active_connections[merchant_id]:
                del self.active_connections[merchant_id]

    async def broadcast_to_merchant(self, merchant_id: str, message: dict):
        if merchant_id not in self.active_connections:
            return

        dead_connections = set()
        for connection in self.active_connections[merchant_id]:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.add(connection)

        for conn in dead_connections:
            self.active_connections[merchant_id].discard(conn)


kds_manager = KDSConnectionManager()


@router.websocket("/ws/kds/{merchant_id}")
async def kds_websocket(
    websocket: WebSocket,
    merchant_id: str,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = decode_token(token)
        user_merchant_id = payload.get("merchant_id")
        if str(user_merchant_id) != merchant_id:
            await websocket.close(code=4001, reason="Unauthorized")
            return
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await kds_manager.connect(websocket, merchant_id)

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            order_id = data.get("order_id")
            item_id = data.get("item_id")

            service = OrderService(db)

            if action == "start_preparing":
                from app.schemas.orders import OrderStatus
                await service.update_status(
                    UUID(order_id), UUID(merchant_id), OrderStatus.preparing
                )
                await kds_manager.broadcast_to_merchant(merchant_id, {
                    "event": "order_updated",
                    "order_id": order_id,
                    "status": "preparing",
                    "timestamp": datetime.utcnow().isoformat()
                })

            elif action == "item_ready":
                await service.update_item_status(
                    UUID(order_id), UUID(merchant_id), UUID(item_id), "ready"
                )
                await kds_manager.broadcast_to_merchant(merchant_id, {
                    "event": "item_ready",
                    "order_id": order_id,
                    "item_id": item_id,
                    "timestamp": datetime.utcnow().isoformat()
                })

            elif action == "order_ready":
                from app.schemas.orders import OrderStatus
                await service.update_status(
                    UUID(order_id), UUID(merchant_id), OrderStatus.ready
                )
                await kds_manager.broadcast_to_merchant(merchant_id, {
                    "event": "order_ready",
                    "order_id": order_id,
                    "timestamp": datetime.utcnow().isoformat()
                })

            elif action == "bump":
                from app.schemas.orders import OrderStatus
                await service.update_status(
                    UUID(order_id), UUID(merchant_id), OrderStatus.served
                )
                await kds_manager.broadcast_to_merchant(merchant_id, {
                    "event": "order_served",
                    "order_id": order_id,
                    "timestamp": datetime.utcnow().isoformat()
                })

            elif action == "ping":
                await websocket.send_json({"event": "pong"})

    except WebSocketDisconnect:
        kds_manager.disconnect(websocket, merchant_id)
    except Exception:
        kds_manager.disconnect(websocket, merchant_id)


async def broadcast_new_order(merchant_id: str, order_data: dict):
    await kds_manager.broadcast_to_merchant(merchant_id, {
        "event": "new_order",
        "order": order_data,
        "timestamp": datetime.utcnow().isoformat()
    })


async def broadcast_order_update(merchant_id: str, order_id: str, status: str):
    await kds_manager.broadcast_to_merchant(merchant_id, {
        "event": "order_updated",
        "order_id": order_id,
        "status": status,
        "timestamp": datetime.utcnow().isoformat()
    })
