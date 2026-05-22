"""
Phase 9 — WebSocket Connection Manager
Manages persistent WebSocket connections, rooms, and broadcast routing.
"""

import json
import asyncio
from typing import Dict, Set, Optional, List, Callable, Any
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
import logging

logger = logging.getLogger(__name__)

# ─── MESSAGE TYPES ─────────────────────────────────────────────────

class WSMessageType:
    # KDS
    ORDER_NEW = "order:new"
    ORDER_UPDATE = "order:update"
    ORDER_STATUS_CHANGE = "order:status_change"
    ORDER_READY = "order:ready"
    ORDER_BUMP = "order:bump"
    KDS_HEARTBEAT = "kds:heartbeat"
    KDS_STATS = "kds:stats"

    # Driver
    DRIVER_LOCATION = "driver:location"
    DRIVER_ASSIGN = "driver:assign"
    DRIVER_PICKUP = "driver:pickup"
    DRIVER_DELIVERED = "driver:delivered"
    DRIVER_OFFLINE = "driver:offline"

    # Fleet
    FLEET_MAP = "fleet:map"
    FLEET_ALERT = "fleet:alert"

    # System
    PING = "ping"
    PONG = "pong"
    AUTH = "auth"
    AUTH_SUCCESS = "auth:success"
    AUTH_FAILURE = "auth:failure"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    ERROR = "error"
    SYSTEM = "system"


class WSMessage:
    """Standardized WebSocket message envelope."""

    def __init__(
        self,
        msg_type: str,
        payload: Any,
        room: Optional[str] = None,
        merchant_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        message_id: Optional[str] = None
    ):
        self.type = msg_type
        self.payload = payload
        self.room = room
        self.merchant_id = merchant_id
        self.timestamp = timestamp or datetime.utcnow()
        self.id = message_id or f"ws-{datetime.utcnow().timestamp()}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "room": self.room,
            "merchant_id": self.merchant_id,
            "timestamp": self.timestamp.isoformat()
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: dict) -> "WSMessage":
        return cls(
            msg_type=data.get("type", WSMessageType.SYSTEM),
            payload=data.get("payload", {}),
            room=data.get("room"),
            merchant_id=data.get("merchant_id"),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else None,
            message_id=data.get("id")
        )


# ─── CONNECTION MANAGER ────────────────────────────────────────────

class ConnectionManager:
    """
    Production-grade WebSocket connection manager.

    Features:
    - Room-based pub/sub (merchant-scoped, KDS, driver, fleet)
    - Heartbeat/ping-pong health checks
    - Connection metadata tracking
    - Graceful disconnect handling
    - Rate limiting hooks
    """

    def __init__(self):
        # merchant_id -> {connection_id -> WebSocket}
        self._merchant_connections: Dict[str, Dict[str, WebSocket]] = {}

        # room_name -> {connection_id}
        self._rooms: Dict[str, Set[str]] = {}

        # connection_id -> metadata
        self._metadata: Dict[str, dict] = {}

        # connection_id -> merchant_id
        self._connection_merchant: Dict[str, str] = {}

        # connection_id -> subscribed rooms
        self._connection_rooms: Dict[str, Set[str]] = {}

        # message handlers by type
        self._handlers: Dict[str, List[Callable]] = {}

        self._lock = asyncio.Lock()

    # ─── Connection Lifecycle ──────────────────────────────────────

    async def connect(
        self,
        websocket: WebSocket,
        merchant_id: str,
        connection_id: str,
        client_type: str = "unknown",  # kds, driver, merchant, customer
        metadata: Optional[dict] = None
    ) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()

        async with self._lock:
            if merchant_id not in self._merchant_connections:
                self._merchant_connections[merchant_id] = {}

            self._merchant_connections[merchant_id][connection_id] = websocket
            self._connection_merchant[connection_id] = merchant_id
            self._connection_rooms[connection_id] = set()
            self._metadata[connection_id] = {
                "client_type": client_type,
                "connected_at": datetime.utcnow().isoformat(),
                "last_ping": datetime.utcnow().isoformat(),
                **(metadata or {})
            }

        logger.info(f"WS connect: {connection_id} ({client_type}) for merchant {merchant_id}")

    async def disconnect(self, connection_id: str) -> None:
        """Unregister and clean up a disconnected client."""
        async with self._lock:
            merchant_id = self._connection_merchant.pop(connection_id, None)

            if merchant_id and merchant_id in self._merchant_connections:
                self._merchant_connections[merchant_id].pop(connection_id, None)
                if not self._merchant_connections[merchant_id]:
                    del self._merchant_connections[merchant_id]

            # Unsubscribe from all rooms
            rooms = self._connection_rooms.pop(connection_id, set())
            for room in rooms:
                if room in self._rooms:
                    self._rooms[room].discard(connection_id)
                    if not self._rooms[room]:
                        del self._rooms[room]

            self._metadata.pop(connection_id, None)

        logger.info(f"WS disconnect: {connection_id}")

    # ─── Room Management ───────────────────────────────────────────

    async def subscribe(self, connection_id: str, room: str) -> None:
        """Subscribe a connection to a room."""
        async with self._lock:
            if room not in self._rooms:
                self._rooms[room] = set()
            self._rooms[room].add(connection_id)

            if connection_id in self._connection_rooms:
                self._connection_rooms[connection_id].add(room)

        logger.debug(f"WS subscribe: {connection_id} -> {room}")

    async def unsubscribe(self, connection_id: str, room: str) -> None:
        """Unsubscribe a connection from a room."""
        async with self._lock:
            if room in self._rooms:
                self._rooms[room].discard(connection_id)
                if not self._rooms[room]:
                    del self._rooms[room]

            if connection_id in self._connection_rooms:
                self._connection_rooms[connection_id].discard(room)

        logger.debug(f"WS unsubscribe: {connection_id} <- {room}")

    # ─── Broadcasting ──────────────────────────────────────────────

    async def send_to_connection(self, connection_id: str, message: WSMessage) -> bool:
        """Send a message to a single connection."""
        merchant_id = self._connection_merchant.get(connection_id)
        if not merchant_id:
            return False

        websocket = self._merchant_connections.get(merchant_id, {}).get(connection_id)
        if websocket is None:
            return False

        try:
            await websocket.send_text(message.to_json())
            return True
        except Exception as e:
            logger.warning(f"WS send failed to {connection_id}: {e}")
            return False

    async def broadcast_to_room(self, room: str, message: WSMessage, exclude: Optional[Set[str]] = None) -> int:
        """Broadcast a message to all connections in a room. Returns delivery count."""
        exclude = exclude or set()
        delivered = 0

        connection_ids = set()
        async with self._lock:
            if room in self._rooms:
                connection_ids = self._rooms[room] - exclude

        if not connection_ids:
            return 0

        # Send concurrently
        tasks = [
            self.send_to_connection(cid, message)
            for cid in connection_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        delivered = sum(1 for r in results if r is True)

        logger.debug(f"WS broadcast to {room}: {delivered}/{len(connection_ids)} delivered")
        return delivered

    async def broadcast_to_merchant(
        self,
        merchant_id: str,
        message: WSMessage,
        client_type: Optional[str] = None,
        exclude: Optional[Set[str]] = None
    ) -> int:
        """Broadcast to all connections for a merchant, optionally filtered by client type."""
        exclude = exclude or set()
        delivered = 0

        async with self._lock:
            connections = self._merchant_connections.get(merchant_id, {})
            target_ids = [
                cid for cid, ws in connections.items()
                if cid not in exclude
                and (client_type is None or self._metadata.get(cid, {}).get("client_type") == client_type)
            ]

        if not target_ids:
            return 0

        tasks = [self.send_to_connection(cid, message) for cid in target_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        delivered = sum(1 for r in results if r is True)

        logger.debug(f"WS broadcast to merchant {merchant_id}: {delivered}/{len(target_ids)} delivered")
        return delivered

    # ─── Room Helpers ──────────────────────────────────────────────

    @staticmethod
    def kds_room(merchant_id: str, branch_id: Optional[str] = None) -> str:
        """Room name for KDS displays."""
        if branch_id:
            return f"kds:{merchant_id}:{branch_id}"
        return f"kds:{merchant_id}"

    @staticmethod
    def driver_room(driver_id: str) -> str:
        """Room for a specific driver's updates."""
        return f"driver:{driver_id}"

    @staticmethod
    def fleet_room(merchant_id: str) -> str:
        """Room for fleet map (all active drivers)."""
        return f"fleet:{merchant_id}"

    @staticmethod
    def order_room(order_id: str) -> str:
        """Room for order-specific updates."""
        return f"order:{order_id}"

    @staticmethod
    def merchant_room(merchant_id: str) -> str:
        """General merchant broadcast room."""
        return f"merchant:{merchant_id}"

    # ─── Health & Stats ────────────────────────────────────────────

    async def ping_connection(self, connection_id: str) -> bool:
        """Send ping and update last_ping metadata."""
        msg = WSMessage(WSMessageType.PING, {"time": datetime.utcnow().isoformat()})
        success = await self.send_to_connection(connection_id, msg)

        if success:
            async with self._lock:
                if connection_id in self._metadata:
                    self._metadata[connection_id]["last_ping"] = datetime.utcnow().isoformat()

        return success

    def get_stats(self, merchant_id: Optional[str] = None) -> dict:
        """Get connection statistics."""
        if merchant_id:
            conns = self._merchant_connections.get(merchant_id, {})
            return {
                "merchant_id": merchant_id,
                "total_connections": len(conns),
                "by_type": {}
            }

        total = sum(len(c) for c in self._merchant_connections.values())
        by_merchant = {mid: len(conns) for mid, conns in self._merchant_connections.items()}

        return {
            "total_connections": total,
            "total_rooms": len(self._rooms),
            "by_merchant": by_merchant
        }

    def get_connection_info(self, connection_id: str) -> Optional[dict]:
        """Get metadata for a connection."""
        meta = self._metadata.get(connection_id)
        if not meta:
            return None

        merchant_id = self._connection_merchant.get(connection_id)
        rooms = list(self._connection_rooms.get(connection_id, set()))

        return {
            "connection_id": connection_id,
            "merchant_id": merchant_id,
            "rooms": rooms,
            **meta
        }


# ─── SINGLETON INSTANCE ────────────────────────────────────────────

ws_manager = ConnectionManager()
