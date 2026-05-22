"""
Phase 9 Schemas — WebSocket, KDS, Driver Tracking
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum

# ─── KDS SCHEMAS ───────────────────────────────────────────────────

class KDSOrderStatus(str, Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    READY = "ready"
    SERVED = "served"
    DELAYED = "delayed"
    CANCELLED = "cancelled"

class KDSItemStatus(str, Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    READY = "ready"
    SERVED = "served"

class KDSItem(BaseModel):
    item_id: UUID
    name: str
    quantity: int
    modifiers: Optional[List[str]] = Field(default_factory=list)
    special_instructions: Optional[str] = None
    status: KDSItemStatus = KDSItemStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    station: Optional[str] = None  # grill, salad, drinks, etc.

class KDSOrder(BaseModel):
    order_id: UUID
    order_number: str
    external_order_id: Optional[str] = None
    status: KDSOrderStatus
    items: List[KDSItem]
    table_number: Optional[str] = None
    order_type: str  # dine_in, takeaway, delivery
    priority: int = Field(default=0, ge=0, le=10)  # 0=normal, 10=urgent
    created_at: datetime
    promised_time: Optional[datetime] = None
    elapsed_seconds: int = 0
    customer_name: Optional[str] = None
    delivery_address: Optional[str] = None
    driver_name: Optional[str] = None
    notes: Optional[str] = None
    color_tag: Optional[str] = None  # red, yellow, green for SLA

class KDSStats(BaseModel):
    total_active: int
    total_preparing: int
    total_ready: int
    total_delayed: int
    avg_prep_time_seconds: int
    longest_wait_seconds: int
    orders_per_hour: float

class KDSBumpRequest(BaseModel):
    order_id: UUID
    bumped_by: str = Field(..., max_length=100)
    station: Optional[str] = None

class KDSUpdateRequest(BaseModel):
    order_id: UUID
    status: Optional[KDSOrderStatus] = None
    item_updates: Optional[List[Dict[str, Any]]] = None  # [{"item_id": "...", "status": "ready"}]
    notes: Optional[str] = None

# ─── DRIVER TRACKING SCHEMAS ───────────────────────────────────────

class DriverStatus(str, Enum):
    OFFLINE = "offline"
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    EN_ROUTE_PICKUP = "en_route_pickup"
    AT_RESTAURANT = "at_restaurant"
    EN_ROUTE_DELIVERY = "en_route_delivery"
    ARRIVED = "arrived"
    DELIVERED = "delivered"
    RETURNING = "returning"

class GeoPoint(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = None  # meters
    heading: Optional[float] = None   # degrees
    speed: Optional[float] = None     # km/h
    timestamp: datetime

class DriverLocationUpdate(BaseModel):
    driver_id: UUID
    location: GeoPoint
    status: DriverStatus
    battery_level: Optional[int] = Field(None, ge=0, le=100)
    order_id: Optional[UUID] = None

class DriverLocationResponse(BaseModel):
    driver_id: UUID
    name: Optional[str] = None
    phone: Optional[str] = None
    vehicle_type: Optional[str] = None
    status: DriverStatus
    location: GeoPoint
    last_updated: datetime
    active_order_id: Optional[UUID] = None
    eta_seconds: Optional[int] = None

class FleetMapData(BaseModel):
    merchant_id: UUID
    drivers: List[DriverLocationResponse]
    active_orders: int
    total_drivers_online: int
    avg_response_time_seconds: Optional[int] = None
    updated_at: datetime

class DriverAssignRequest(BaseModel):
    order_id: UUID
    driver_id: UUID
    assigned_by: str = Field(..., max_length=100)
    estimated_pickup_time: Optional[datetime] = None
    estimated_delivery_time: Optional[datetime] = None
    notes: Optional[str] = None

class DriverPickupConfirm(BaseModel):
    order_id: UUID
    driver_id: UUID
    picked_up_at: datetime
    items_verified: bool = True
    photos: Optional[List[str]] = Field(default_factory=list)

class DriverDeliveryConfirm(BaseModel):
    order_id: UUID
    driver_id: UUID
    delivered_at: datetime
    delivered_to: Optional[str] = None
    signature_url: Optional[str] = None
    photo_url: Optional[str] = None
    notes: Optional[str] = None
    payment_collected: Optional[Decimal] = None

# ─── WEBSOCKET MESSAGE SCHEMAS ─────────────────────────────────────

class WSAuthPayload(BaseModel):
    token: str
    client_type: str = Field(..., pattern="^(kds|driver|merchant|customer)$")
    device_id: Optional[str] = None
    branch_id: Optional[UUID] = None

class WSSubscribePayload(BaseModel):
    rooms: List[str]

class WSOrderPayload(BaseModel):
    order: KDSOrder
    event: str = "new"  # new, update, status_change, ready, bump

class WSDriverPayload(BaseModel):
    driver_id: UUID
    location: GeoPoint
    status: DriverStatus
    order_id: Optional[UUID] = None

class WSFleetPayload(BaseModel):
    merchant_id: UUID
    drivers: List[DriverLocationResponse]
    alerts: Optional[List[str]] = None

class WSHeartbeatPayload(BaseModel):
    connection_id: str
    timestamp: datetime
    latency_ms: Optional[int] = None

class WSIncomingMessage(BaseModel):
    type: str
    payload: Dict[str, Any]
    room: Optional[str] = None
    request_id: Optional[str] = None

class WSOutgoingMessage(BaseModel):
    id: str
    type: str
    payload: Dict[str, Any]
    room: Optional[str] = None
    timestamp: datetime
    request_id: Optional[str] = None

# ─── KDS DISPLAY CONFIG ────────────────────────────────────────────

class KDSDisplayConfig(BaseModel):
    merchant_id: UUID
    branch_id: Optional[UUID] = None
    stations: List[str] = Field(default_factory=list)  # ["grill", "fryer", "salad", "drinks"]
    sound_enabled: bool = True
    auto_bump_seconds: Optional[int] = None  # Auto-bump after N seconds when ready
    sla_warning_seconds: int = 600  # 10 min
    sla_critical_seconds: int = 900  # 15 min
    show_customer_name: bool = True
    show_delivery_address: bool = True
    theme: str = "dark"  # dark, light
    layout: str = "grid"  # grid, list, station

class KDSFilterParams(BaseModel):
    status: Optional[List[KDSOrderStatus]] = None
    station: Optional[str] = None
    order_type: Optional[str] = None
    priority_only: bool = False
    delayed_only: bool = False
    search: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
