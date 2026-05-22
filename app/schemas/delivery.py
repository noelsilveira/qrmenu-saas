from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from enum import Enum


class DeliveryStatus(str, Enum):
    pending = "pending"
    assigned = "assigned"
    picked_up = "picked_up"
    en_route = "en_route"
    arrived = "arrived"
    delivered = "delivered"
    cancelled = "cancelled"
    returned = "returned"


class DriverStatus(str, Enum):
    offline = "offline"
    available = "available"
    busy = "busy"
    on_break = "on_break"


class VehicleType(str, Enum):
    bicycle = "bicycle"
    motorcycle = "motorcycle"
    car = "car"
    van = "van"


# ---------------------------------------------------------------------------
# Delivery Zone Schemas
# ---------------------------------------------------------------------------
class ZoneBoundary(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)


class DeliveryZoneCreate(BaseModel):
    name: str
    boundaries: List[ZoneBoundary] = Field(..., min_length=3)
    base_fee: Decimal = Decimal("1.000")
    per_km_fee: Decimal = Decimal("0.500")
    min_order_value: Decimal = Decimal("5.000")
    free_delivery_threshold: Optional[Decimal] = None
    max_delivery_distance_km: Decimal = Decimal("15.0")
    estimated_delivery_min: int = 30
    is_active: bool = True


class DeliveryZoneUpdate(BaseModel):
    name: Optional[str] = None
    boundaries: Optional[List[ZoneBoundary]] = None
    base_fee: Optional[Decimal] = None
    per_km_fee: Optional[Decimal] = None
    min_order_value: Optional[Decimal] = None
    free_delivery_threshold: Optional[Decimal] = None
    max_delivery_distance_km: Optional[Decimal] = None
    estimated_delivery_min: Optional[int] = None
    is_active: Optional[bool] = None


class DeliveryZoneResponse(BaseModel):
    id: UUID
    merchant_id: UUID
    name: str
    boundaries: List[ZoneBoundary]
    base_fee: Decimal
    per_km_fee: Decimal
    min_order_value: Decimal
    free_delivery_threshold: Optional[Decimal]
    max_delivery_distance_km: Decimal
    estimated_delivery_min: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ZoneMatchRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    order_value: Optional[Decimal] = None


class ZoneMatchResponse(BaseModel):
    zone_id: Optional[UUID] = None
    zone_name: Optional[str] = None
    deliverable: bool
    base_fee: Decimal = Decimal("0.000")
    distance_km: Optional[Decimal] = None
    estimated_min: int = 0
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Driver Schemas
# ---------------------------------------------------------------------------
class DriverCreate(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    vehicle_type: VehicleType = VehicleType.motorcycle
    vehicle_plate: Optional[str] = None
    max_orders_per_run: int = Field(3, ge=1, le=10)


class DriverUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    vehicle_type: Optional[VehicleType] = None
    vehicle_plate: Optional[str] = None
    max_orders_per_run: Optional[int] = None
    status: Optional[DriverStatus] = None


class DriverLocationUpdate(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = None
    heading: Optional[float] = None
    speed: Optional[float] = None


class DriverResponse(BaseModel):
    id: UUID
    merchant_id: UUID
    name: str
    phone: str
    email: Optional[str]
    vehicle_type: VehicleType
    vehicle_plate: Optional[str]
    status: DriverStatus
    max_orders_per_run: int
    current_lat: Optional[float]
    current_lng: Optional[float]
    last_location_at: Optional[datetime]
    total_deliveries: int
    rating: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


class DriverLocationResponse(BaseModel):
    driver_id: UUID
    name: str
    lat: float
    lng: float
    accuracy: Optional[float]
    heading: Optional[float]
    speed: Optional[float]
    status: DriverStatus
    updated_at: datetime


# ---------------------------------------------------------------------------
# Delivery Assignment Schemas
# ---------------------------------------------------------------------------
class DeliveryAssignmentCreate(BaseModel):
    order_id: UUID
    driver_id: UUID
    pickup_address: Optional[Dict[str, Any]] = None
    delivery_address: Dict[str, Any]
    notes: Optional[str] = None


class DeliveryAssignmentResponse(BaseModel):
    id: UUID
    order_id: UUID
    driver_id: UUID
    driver_name: str
    status: DeliveryStatus
    pickup_address: Optional[dict]
    delivery_address: dict
    estimated_pickup_at: Optional[datetime]
    estimated_delivery_at: Optional[datetime]
    actual_pickup_at: Optional[datetime]
    actual_delivery_at: Optional[datetime]
    delivery_fee: Decimal
    distance_km: Optional[Decimal]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DeliveryStatusUpdate(BaseModel):
    status: DeliveryStatus
    lat: Optional[float] = None
    lng: Optional[float] = None
    notes: Optional[str] = None


class BulkAssignRequest(BaseModel):
    order_ids: List[UUID]
    driver_id: UUID


class AutoAssignRequest(BaseModel):
    order_id: UUID
    strategy: str = "nearest"  # nearest, round_robin, load_balanced


class AutoAssignResponse(BaseModel):
    order_id: UUID
    driver_id: Optional[UUID] = None
    driver_name: Optional[str] = None
    distance_km: Optional[Decimal] = None
    eta_minutes: Optional[int] = None
    assigned: bool
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# GPS Tracking Schemas
# ---------------------------------------------------------------------------
class GPSTrackPoint(BaseModel):
    lat: float
    lng: float
    timestamp: datetime
    accuracy: Optional[float] = None


class DeliveryTrackingResponse(BaseModel):
    delivery_id: UUID
    order_id: UUID
    driver_id: UUID
    driver_name: str
    driver_phone: str
    status: DeliveryStatus
    current_lat: Optional[float]
    current_lng: Optional[float]
    route: List[GPSTrackPoint] = []
    estimated_delivery_at: Optional[datetime]
    actual_delivery_at: Optional[datetime]
    customer_address: dict
    distance_remaining_km: Optional[Decimal] = None


class FleetStatusResponse(BaseModel):
    total_drivers: int
    available_drivers: int
    busy_drivers: int
    offline_drivers: int
    active_deliveries: int
    pending_assignments: int
    avg_delivery_time_min: Optional[int] = None
