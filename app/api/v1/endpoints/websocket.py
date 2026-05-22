"""
Phase 9 API Endpoints — WebSocket KDS, Driver Tracking, Fleet Map
"""

import uuid
import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.auth import get_current_user
from app.core.websocket_manager import ws_manager, WSMessage, WSMessageType
from app.schemas.websocket import (
    WSAuthPayload, WSSubscribePayload,
    DriverLocationUpdate, DriverAssignRequest,
    DriverPickupConfirm, DriverDeliveryConfirm,
    KDSBumpRequest, KDSUpdateRequest, KDSFilterParams,
    KDSDisplayConfig
)
from app.services.kds_service import KDSService
from app.services.driver_tracking_service import DriverTrackingService

router = APIRouter(tags=["websocket"])

# ─── WEBSOCKET HANDLER ───────────────────────────────────────────

async def handle_ws_message(
    websocket: WebSocket,
    connection_id: str,
    merchant_id: str,
    raw_message: str,
    db: AsyncSession
) -> None:
    """Route incoming WebSocket messages to appropriate handlers."""

    try:
        data = json.loads(raw_message)
        msg_type = data.get("type", "")
        payload = data.get("payload", {})
        request_id = data.get("request_id")
    except json.JSONDecodeError:
        await websocket.send_text(json.dumps({
            "type": WSMessageType.ERROR,
            "payload": {"error": "Invalid JSON"},
            "request_id": None
        }))
        return

    # ─── AUTH ────────────────────────────────────────────────────
    if msg_type == WSMessageType.AUTH:
        auth_payload = WSAuthPayload(**payload)
        # Validate token (simplified; integrate with your JWT auth)
        # TODO: verify auth_payload.token against your auth system
        await websocket.send_text(json.dumps({
            "type": WSMessageType.AUTH_SUCCESS,
            "payload": {"client_type": auth_payload.client_type, "connection_id": connection_id},
            "request_id": request_id
        }))
        return

    # ─── PING/PONG ───────────────────────────────────────────────
    if msg_type == WSMessageType.PING:
        await websocket.send_text(json.dumps({
            "type": WSMessageType.PONG,
            "payload": {"time": datetime.utcnow().isoformat(), "connection_id": connection_id},
            "request_id": request_id
        }))
        return

    # ─── SUBSCRIBE ───────────────────────────────────────────────
    if msg_type == WSMessageType.SUBSCRIBE:
        sub_payload = WSSubscribePayload(**payload)
        for room in sub_payload.rooms:
            await ws_manager.subscribe(connection_id, room)
        await websocket.send_text(json.dumps({
            "type": WSMessageType.SUBSCRIBE,
            "payload": {"subscribed_to": sub_payload.rooms},
            "request_id": request_id
        }))
        return

    # ─── UNSUBSCRIBE ─────────────────────────────────────────────
    if msg_type == WSMessageType.UNSUBSCRIBE:
        rooms = payload.get("rooms", [])
        for room in rooms:
            await ws_manager.unsubscribe(connection_id, room)
        await websocket.send_text(json.dumps({
            "type": WSMessageType.UNSUBSCRIBE,
            "payload": {"unsubscribed_from": rooms},
            "request_id": request_id
        }))
        return

    # ─── DRIVER LOCATION ─────────────────────────────────────────
    if msg_type == WSMessageType.DRIVER_LOCATION:
        driver_update = DriverLocationUpdate(**payload)
        driver_service = DriverTrackingService(db)

        try:
            response = await driver_service.update_location(
                uuid.UUID(merchant_id), driver_update
            )
            await websocket.send_text(json.dumps({
                "type": WSMessageType.DRIVER_LOCATION,
                "payload": response.model_dump(),
                "request_id": request_id
            }))
        except ValueError as e:
            await websocket.send_text(json.dumps({
                "type": WSMessageType.ERROR,
                "payload": {"error": str(e)},
                "request_id": request_id
            }))
        return

    # ─── KDS BUMP ────────────────────────────────────────────────
    if msg_type == WSMessageType.ORDER_BUMP:
        bump_request = KDSBumpRequest(**payload)
        kds_service = KDSService(db)

        result = await kds_service.bump_order(
            uuid.UUID(merchant_id), bump_request
        )
        await websocket.send_text(json.dumps({
            "type": WSMessageType.ORDER_BUMP,
            "payload": {"bumped": result is not None, "order": result.model_dump() if result else None},
            "request_id": request_id
        }))
        return

    # ─── KDS UPDATE ──────────────────────────────────────────────
    if msg_type == WSMessageType.ORDER_STATUS_CHANGE:
        update_request = KDSUpdateRequest(**payload)
        kds_service = KDSService(db)

        result = await kds_service.update_order_status(
            uuid.UUID(merchant_id), update_request
        )
        await websocket.send_text(json.dumps({
            "type": WSMessageType.ORDER_STATUS_CHANGE,
            "payload": {"updated": result is not None, "order": result.model_dump() if result else None},
            "request_id": request_id
        }))
        return

    # ─── UNKNOWN ─────────────────────────────────────────────────
    await websocket.send_text(json.dumps({
        "type": WSMessageType.ERROR,
        "payload": {"error": f"Unknown message type: {msg_type}"},
        "request_id": request_id
    }))


# ─── WEBSOCKET ENDPOINTS ─────────────────────────────────────────

@router.websocket("/kds/{merchant_id}")
async def kds_websocket(
    websocket: WebSocket,
    merchant_id: str,
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for Kitchen Display System screens.

    Connection flow:
    1. Client connects
    2. Client sends AUTH with token
    3. Client subscribes to kds:{merchant_id}[:{branch_id}] room
    4. Server pushes ORDER_NEW, ORDER_UPDATE, ORDER_READY, ORDER_BUMP
    """
    connection_id = f"kds-{merchant_id}-{datetime.utcnow().timestamp()}"

    await ws_manager.connect(
        websocket,
        merchant_id=merchant_id,
        connection_id=connection_id,
        client_type="kds",
        metadata={"branch_id": branch_id}
    )

    # Auto-subscribe to KDS room
    kds_room = ws_manager.kds_room(merchant_id, branch_id)
    await ws_manager.subscribe(connection_id, kds_room)

    # Send initial stats
    kds_service = KDSService(db)
    stats = await kds_service.get_stats(
        uuid.UUID(merchant_id),
        uuid.UUID(branch_id) if branch_id else None
    )
    await websocket.send_text(json.dumps({
        "type": WSMessageType.KDS_STATS,
        "payload": stats.model_dump(),
        "room": kds_room
    }))

    try:
        while True:
            raw_message = await websocket.receive_text()
            await handle_ws_message(websocket, connection_id, merchant_id, raw_message, db)
    except WebSocketDisconnect:
        await ws_manager.disconnect(connection_id)
    except Exception as e:
        await ws_manager.disconnect(connection_id)
        raise


@router.websocket("/driver/{merchant_id}")
async def driver_websocket(
    websocket: WebSocket,
    merchant_id: str,
    driver_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for driver mobile apps.

    Connection flow:
    1. Driver app connects with driver_id
    2. Sends AUTH + periodic DRIVER_LOCATION updates
    3. Receives DRIVER_ASSIGN, order updates
    """
    connection_id = f"driver-{driver_id}-{datetime.utcnow().timestamp()}"

    await ws_manager.connect(
        websocket,
        merchant_id=merchant_id,
        connection_id=connection_id,
        client_type="driver",
        metadata={"driver_id": driver_id}
    )

    # Subscribe to driver-specific room and fleet room
    driver_room = ws_manager.driver_room(driver_id)
    fleet_room = ws_manager.fleet_room(merchant_id)
    await ws_manager.subscribe(connection_id, driver_room)
    await ws_manager.subscribe(connection_id, fleet_room)

    try:
        while True:
            raw_message = await websocket.receive_text()
            await handle_ws_message(websocket, connection_id, merchant_id, raw_message, db)
    except WebSocketDisconnect:
        # Mark driver offline
        driver_service = DriverTrackingService(db)
        # TODO: update driver status to offline in DB
        await ws_manager.disconnect(connection_id)
    except Exception as e:
        await ws_manager.disconnect(connection_id)
        raise


@router.websocket("/merchant/{merchant_id}")
async def merchant_websocket(
    websocket: WebSocket,
    merchant_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for merchant dashboard / admin.

    Receives:
    - Fleet map updates
    - Order notifications
    - System alerts
    """
    connection_id = f"merchant-{merchant_id}-{datetime.utcnow().timestamp()}"

    await ws_manager.connect(
        websocket,
        merchant_id=merchant_id,
        connection_id=connection_id,
        client_type="merchant",
        metadata={}
    )

    # Subscribe to merchant room and fleet room
    merchant_room = ws_manager.merchant_room(merchant_id)
    fleet_room = ws_manager.fleet_room(merchant_id)
    await ws_manager.subscribe(connection_id, merchant_room)
    await ws_manager.subscribe(connection_id, fleet_room)

    try:
        while True:
            raw_message = await websocket.receive_text()
            await handle_ws_message(websocket, connection_id, merchant_id, raw_message, db)
    except WebSocketDisconnect:
        await ws_manager.disconnect(connection_id)
    except Exception as e:
        await ws_manager.disconnect(connection_id)
        raise


@router.websocket("/customer/{order_id}")
async def customer_websocket(
    websocket: WebSocket,
    order_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for customer order tracking.

    Customer connects with order_id to receive:
    - Order status updates
    - Driver location (if delivery)
    - ETA updates
    """
    # Verify order exists
    from sqlalchemy import select
    from app.models.models import Order

    result = await db.execute(select(Order).where(Order.id == uuid.UUID(order_id)))
    order = result.scalar_one_or_none()
    if not order:
        await websocket.close(code=4004, reason="Order not found")
        return

    merchant_id = str(order.merchant_id)
    connection_id = f"customer-{order_id}-{datetime.utcnow().timestamp()}"

    await ws_manager.connect(
        websocket,
        merchant_id=merchant_id,
        connection_id=connection_id,
        client_type="customer",
        metadata={"order_id": order_id}
    )

    # Subscribe to order-specific room
    order_room = ws_manager.order_room(order_id)
    await ws_manager.subscribe(connection_id, order_room)

    # Send initial order state
    kds_service = KDSService(db)
    kds_order = await kds_service.order_to_kds(order)
    await websocket.send_text(json.dumps({
        "type": WSMessageType.ORDER_UPDATE,
        "payload": {"order": kds_order.model_dump(), "event": "connected"},
        "room": order_room
    }))

    try:
        while True:
            raw_message = await websocket.receive_text()
            await handle_ws_message(websocket, connection_id, merchant_id, raw_message, db)
    except WebSocketDisconnect:
        await ws_manager.disconnect(connection_id)
    except Exception as e:
        await ws_manager.disconnect(connection_id)
        raise


# ─── REST ENDPOINTS FOR INITIAL LOAD ─────────────────────────────

@router.get("/kds/orders")
async def get_kds_orders(
    status: Optional[str] = Query(None),
    station: Optional[str] = Query(None),
    order_type: Optional[str] = Query(None),
    priority_only: bool = Query(False),
    delayed_only: bool = Query(False),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current KDS orders (REST fallback for initial load)."""
    kds_service = KDSService(db)

    params = KDSFilterParams(
        status=status.split(",") if status else None,
        station=station,
        order_type=order_type,
        priority_only=priority_only,
        delayed_only=delayed_only,
        search=search,
        page=page,
        page_size=page_size
    )

    orders, total = await kds_service.get_active_orders(current_user.merchant_id, None, params)
    return {
        "orders": [o.model_dump() for o in orders],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/kds/stats")
async def get_kds_stats(
    branch_id: Optional[uuid.UUID] = Query(None),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get KDS real-time statistics."""
    kds_service = KDSService(db)
    stats = await kds_service.get_stats(current_user.merchant_id, branch_id)
    return stats.model_dump()


@router.post("/kds/bump")
async def bump_kds_order(
    request: KDSBumpRequest,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Bump (complete) an order from KDS."""
    kds_service = KDSService(db)
    result = await kds_service.bump_order(current_user.merchant_id, request)
    if not result:
        raise HTTPException(status_code=404, detail="Order not found")
    return result


@router.patch("/kds/orders/{order_id}")
async def update_kds_order(
    order_id: uuid.UUID,
    request: KDSUpdateRequest,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update order status from KDS."""
    request.order_id = order_id
    kds_service = KDSService(db)
    result = await kds_service.update_order_status(current_user.merchant_id, request)
    if not result:
        raise HTTPException(status_code=404, detail="Order not found")
    return result


@router.get("/fleet/map")
async def get_fleet_map(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current fleet map data (REST fallback)."""
    driver_service = DriverTrackingService(db)
    fleet = await driver_service.get_fleet_map(current_user.merchant_id)
    return fleet.model_dump()


@router.get("/fleet/drivers/{driver_id}/location")
async def get_driver_location(
    driver_id: uuid.UUID,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a driver's current location."""
    driver_service = DriverTrackingService(db)
    location = await driver_service.get_driver_location(current_user.merchant_id, driver_id)
    if not location:
        raise HTTPException(status_code=404, detail="Driver not found")
    return location.model_dump()


@router.post("/fleet/drivers/{driver_id}/assign")
async def assign_driver(
    driver_id: uuid.UUID,
    request: DriverAssignRequest,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Assign a driver to an order."""
    request.driver_id = driver_id
    driver_service = DriverTrackingService(db)
    result = await driver_service.assign_driver(current_user.merchant_id, request)
    if not result:
        raise HTTPException(status_code=400, detail="Assignment failed")
    return result.model_dump()


@router.post("/fleet/drivers/{driver_id}/pickup")
async def confirm_driver_pickup(
    driver_id: uuid.UUID,
    request: DriverPickupConfirm,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Confirm driver pickup."""
    request.driver_id = driver_id
    driver_service = DriverTrackingService(db)
    result = await driver_service.confirm_pickup(current_user.merchant_id, request)
    if not result:
        raise HTTPException(status_code=400, detail="Pickup confirmation failed")
    return result.model_dump()


@router.post("/fleet/drivers/{driver_id}/deliver")
async def confirm_driver_delivery(
    driver_id: uuid.UUID,
    request: DriverDeliveryConfirm,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Confirm driver delivery."""
    request.driver_id = driver_id
    driver_service = DriverTrackingService(db)
    result = await driver_service.confirm_delivery(current_user.merchant_id, request)
    if not result:
        raise HTTPException(status_code=400, detail="Delivery confirmation failed")
    return result.model_dump()


# ─── WEBSOCKET STATS ─────────────────────────────────────────────

@router.get("/ws/stats")
async def get_websocket_stats(
    current_user = Depends(get_current_user)
):
    """Get WebSocket connection statistics."""
    return ws_manager.get_stats(str(current_user.merchant_id))
