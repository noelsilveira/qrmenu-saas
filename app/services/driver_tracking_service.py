"""
Phase 9 Service — Driver Tracking & Fleet Management
Real-time GPS tracking, driver assignment, and fleet map aggregation.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, and_, or_, func, desc, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Order, OrderStatus, Driver
from app.schemas.websocket import (
    DriverLocationUpdate, DriverLocationResponse, DriverStatus,
    GeoPoint, FleetMapData, DriverAssignRequest,
    DriverPickupConfirm, DriverDeliveryConfirm
)
from app.core.websocket_manager import ws_manager, WSMessage, WSMessageType

# ─── DRIVER TRACKING SERVICE ───────────────────────────────────────

class DriverTrackingService:
    """
    Real-time driver tracking and fleet management.

    Features:
    - GPS location ingestion from driver mobile apps
    - Driver status lifecycle management
    - Order assignment and handoff
    - Fleet map aggregation for merchant dashboard
    - ETA calculation (simplified; enhance with routing API)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        # In-memory cache of last known locations (fallback to DB)
        # In production, use Redis for this
        self._location_cache: Dict[str, dict] = {}

    # ─── Location Updates ──────────────────────────────────────────

    async def update_location(self, merchant_id: uuid.UUID, 
                              update: DriverLocationUpdate) -> DriverLocationResponse:
        """Process a driver GPS location update."""

        # Verify driver belongs to merchant
        result = await self.db.execute(
            select(Driver).where(
                Driver.id == update.driver_id,
                Driver.merchant_id == merchant_id
            )
        )
        driver = result.scalar_one_or_none()
        if not driver:
            raise ValueError(f"Driver {update.driver_id} not found for merchant {merchant_id}")

        # Update driver record
        driver.current_lat = update.location.lat
        driver.current_lng = update.location.lng
        driver.status = update.status.value
        driver.last_location_at = datetime.utcnow()
        driver.updated_at = datetime.utcnow()

        if update.battery_level is not None:
            driver.battery_level = update.battery_level

        if update.order_id:
            driver.current_order_id = update.order_id

        await self.db.flush()

        # Cache location
        self._location_cache[str(update.driver_id)] = {
            "lat": update.location.lat,
            "lng": update.location.lng,
            "status": update.status.value,
            "timestamp": datetime.utcnow().isoformat(),
            "order_id": str(update.order_id) if update.order_id else None
        }

        # Build response
        response = DriverLocationResponse(
            driver_id=update.driver_id,
            name=driver.name,
            phone=driver.phone,
            vehicle_type=driver.vehicle_type,
            status=update.status,
            location=update.location,
            last_updated=datetime.utcnow(),
            active_order_id=update.order_id,
            eta_seconds=None  # Calculated separately
        )

        # Broadcast to fleet room
        fleet_room = ws_manager.fleet_room(str(merchant_id))
        fleet_msg = WSMessage(
            WSMessageType.DRIVER_LOCATION,
            response.model_dump(),
            room=fleet_room,
            merchant_id=str(merchant_id)
        )
        await ws_manager.broadcast_to_room(fleet_room, fleet_msg)

        # Broadcast to driver-specific room
        driver_room = ws_manager.driver_room(str(update.driver_id))
        driver_msg = WSMessage(
            WSMessageType.DRIVER_LOCATION,
            response.model_dump(),
            room=driver_room,
            merchant_id=str(merchant_id)
        )
        await ws_manager.broadcast_to_room(driver_room, driver_msg)

        # If assigned to order, broadcast to order room too
        if update.order_id:
            order_room = ws_manager.order_room(str(update.order_id))
            order_msg = WSMessage(
                WSMessageType.DRIVER_LOCATION,
                {
                    "driver": response.model_dump(),
                    "order_id": str(update.order_id)
                },
                room=order_room,
                merchant_id=str(merchant_id)
            )
            await ws_manager.broadcast_to_room(order_room, order_msg)

        return response

    # ─── Driver Assignment ─────────────────────────────────────────

    async def assign_driver(
        self,
        merchant_id: uuid.UUID,
        request: DriverAssignRequest
    ) -> Optional[DriverLocationResponse]:
        """Assign a driver to an order."""

        # Verify order and driver
        order_result = await self.db.execute(
            select(Order).where(
                Order.id == request.order_id,
                Order.merchant_id == merchant_id
            )
        )
        order = order_result.scalar_one_or_none()
        if not order:
            raise ValueError("Order not found")

        driver_result = await self.db.execute(
            select(Driver).where(
                Driver.id == request.driver_id,
                Driver.merchant_id == merchant_id,
                Driver.status.in_(["available", "returning"])
            )
        )
        driver = driver_result.scalar_one_or_none()
        if not driver:
            raise ValueError("Driver not available")

        # Update order
        order.driver_id = request.driver_id
        order.status = OrderStatus.OUT_FOR_DELIVERY
        order.assigned_at = datetime.utcnow()
        order.estimated_pickup_time = request.estimated_pickup_time
        order.estimated_delivery_time = request.estimated_delivery_time
        order.updated_at = datetime.utcnow()

        # Update driver
        driver.status = "assigned"
        driver.current_order_id = request.order_id
        driver.updated_at = datetime.utcnow()

        await self.db.flush()

        # Build response
        response = DriverLocationResponse(
            driver_id=driver.id,
            name=driver.name,
            phone=driver.phone,
            vehicle_type=driver.vehicle_type,
            status=DriverStatus.ASSIGNED,
            location=GeoPoint(
                lat=driver.current_lat or 0,
                lng=driver.current_lng or 0,
                timestamp=datetime.utcnow()
            ),
            last_updated=datetime.utcnow(),
            active_order_id=request.order_id,
            eta_seconds=self._calculate_eta(driver, order)
        )

        # Broadcast assignment
        fleet_room = ws_manager.fleet_room(str(merchant_id))
        msg = WSMessage(
            WSMessageType.DRIVER_ASSIGN,
            {
                "driver": response.model_dump(),
                "order_id": str(request.order_id),
                "assigned_by": request.assigned_by,
                "estimated_pickup": request.estimated_pickup_time.isoformat() if request.estimated_pickup_time else None,
                "estimated_delivery": request.estimated_delivery_time.isoformat() if request.estimated_delivery_time else None
            },
            room=fleet_room,
            merchant_id=str(merchant_id)
        )
        await ws_manager.broadcast_to_room(fleet_room, msg)

        # Also broadcast to order room
        order_room = ws_manager.order_room(str(request.order_id))
        order_msg = WSMessage(
            WSMessageType.DRIVER_ASSIGN,
            {
                "driver": response.model_dump(),
                "order_id": str(request.order_id)
            },
            room=order_room,
            merchant_id=str(merchant_id)
        )
        await ws_manager.broadcast_to_room(order_room, order_msg)

        return response

    async def confirm_pickup(
        self,
        merchant_id: uuid.UUID,
        request: DriverPickupConfirm
    ) -> Optional[DriverLocationResponse]:
        """Driver confirms order pickup."""

        order_result = await self.db.execute(
            select(Order).where(
                Order.id == request.order_id,
                Order.merchant_id == merchant_id
            )
        )
        order = order_result.scalar_one_or_none()
        if not order:
            raise ValueError("Order not found")

        order.status = OrderStatus.OUT_FOR_DELIVERY
        order.picked_up_at = request.picked_up_at
        order.updated_at = datetime.utcnow()

        # Update driver status
        driver_result = await self.db.execute(
            select(Driver).where(Driver.id == request.driver_id)
        )
        driver = driver_result.scalar_one_or_none()
        if driver:
            driver.status = "en_route_delivery"
            driver.updated_at = datetime.utcnow()

        await self.db.flush()

        response = await self._build_driver_response(request.driver_id)

        # Broadcast
        fleet_room = ws_manager.fleet_room(str(merchant_id))
        msg = WSMessage(
            WSMessageType.DRIVER_PICKUP,
            {
                "driver": response.model_dump() if response else None,
                "order_id": str(request.order_id),
                "picked_up_at": request.picked_up_at.isoformat(),
                "items_verified": request.items_verified
            },
            room=fleet_room,
            merchant_id=str(merchant_id)
        )
        await ws_manager.broadcast_to_room(fleet_room, msg)

        return response

    async def confirm_delivery(
        self,
        merchant_id: uuid.UUID,
        request: DriverDeliveryConfirm
    ) -> Optional[DriverLocationResponse]:
        """Driver confirms order delivery."""

        order_result = await self.db.execute(
            select(Order).where(
                Order.id == request.order_id,
                Order.merchant_id == merchant_id
            )
        )
        order = order_result.scalar_one_or_none()
        if not order:
            raise ValueError("Order not found")

        order.status = OrderStatus.DELIVERED
        order.delivered_at = request.delivered_at
        order.delivery_notes = request.notes
        order.updated_at = datetime.utcnow()

        # Update driver
        driver_result = await self.db.execute(
            select(Driver).where(Driver.id == request.driver_id)
        )
        driver = driver_result.scalar_one_or_none()
        if driver:
            driver.status = "available"
            driver.current_order_id = None
            driver.updated_at = datetime.utcnow()

        await self.db.flush()

        response = await self._build_driver_response(request.driver_id)

        # Broadcast
        fleet_room = ws_manager.fleet_room(str(merchant_id))
        msg = WSMessage(
            WSMessageType.DRIVER_DELIVERED,
            {
                "driver": response.model_dump() if response else None,
                "order_id": str(request.order_id),
                "delivered_at": request.delivered_at.isoformat(),
                "delivered_to": request.delivered_to,
                "payment_collected": float(request.payment_collected) if request.payment_collected else None
            },
            room=fleet_room,
            merchant_id=str(merchant_id)
        )
        await ws_manager.broadcast_to_room(fleet_room, msg)

        return response

    # ─── Fleet Map ─────────────────────────────────────────────────

    async def get_fleet_map(self, merchant_id: uuid.UUID) -> FleetMapData:
        """Get current fleet map with all active drivers."""

        result = await self.db.execute(
            select(Driver).where(
                Driver.merchant_id == merchant_id,
                Driver.status.in_(["available", "assigned", "en_route_pickup", 
                                   "at_restaurant", "en_route_delivery", "returning"])
            )
        )
        drivers = result.scalars().all()

        driver_responses = []
        for driver in drivers:
            # Get active order if any
            active_order_id = None
            if driver.current_order_id:
                active_order_id = driver.current_order_id

            # Get ETA if assigned
            eta = None
            if active_order_id:
                order_result = await self.db.execute(
                    select(Order).where(Order.id == active_order_id)
                )
                order = order_result.scalar_one_or_none()
                if order:
                    eta = self._calculate_eta(driver, order)

            driver_responses.append(DriverLocationResponse(
                driver_id=driver.id,
                name=driver.name,
                phone=driver.phone,
                vehicle_type=driver.vehicle_type,
                status=DriverStatus(driver.status) if driver.status in [s.value for s in DriverStatus] else DriverStatus.OFFLINE,
                location=GeoPoint(
                    lat=driver.current_lat or 0,
                    lng=driver.current_lng or 0,
                    timestamp=driver.last_location_at or datetime.utcnow()
                ),
                last_updated=driver.last_location_at or datetime.utcnow(),
                active_order_id=active_order_id,
                eta_seconds=eta
            ))

        # Count active orders
        active_orders_result = await self.db.execute(
            select(func.count(Order.id)).where(
                Order.merchant_id == merchant_id,
                Order.status.in_([
                    OrderStatus.OUT_FOR_DELIVERY,
                    OrderStatus.READY
                ])
            )
        )
        active_orders = active_orders_result.scalar()

        return FleetMapData(
            merchant_id=merchant_id,
            drivers=driver_responses,
            active_orders=active_orders,
            total_drivers_online=len(drivers),
            avg_response_time_seconds=None,  # TODO: calculate from historical data
            updated_at=datetime.utcnow()
        )

    async def get_driver_location(
        self,
        merchant_id: uuid.UUID,
        driver_id: uuid.UUID
    ) -> Optional[DriverLocationResponse]:
        """Get a single driver's current location."""
        return await self._build_driver_response(driver_id)

    # ─── Helpers ───────────────────────────────────────────────────

    async def _build_driver_response(self, driver_id: uuid.UUID) -> Optional[DriverLocationResponse]:
        """Build a DriverLocationResponse from DB."""
        result = await self.db.execute(
            select(Driver).where(Driver.id == driver_id)
        )
        driver = result.scalar_one_or_none()
        if not driver:
            return None

        active_order_id = driver.current_order_id

        return DriverLocationResponse(
            driver_id=driver.id,
            name=driver.name,
            phone=driver.phone,
            vehicle_type=driver.vehicle_type,
            status=DriverStatus(driver.status) if driver.status in [s.value for s in DriverStatus] else DriverStatus.OFFLINE,
            location=GeoPoint(
                lat=driver.current_lat or 0,
                lng=driver.current_lng or 0,
                timestamp=driver.last_location_at or datetime.utcnow()
            ),
            last_updated=driver.last_location_at or datetime.utcnow(),
            active_order_id=active_order_id,
            eta_seconds=None
        )

    def _calculate_eta(self, driver: Driver, order: Order) -> Optional[int]:
        """Calculate estimated time of arrival in seconds."""
        # Simplified: assume 3 min per km at average speed
        # In production, integrate Google Maps / OSRM routing API

        if not driver.current_lat or not driver.current_lng:
            return None

        # Get delivery location from order
        delivery_lat = None
        delivery_lng = None
        if isinstance(order.delivery_address, dict):
            delivery_lat = order.delivery_address.get("lat")
            delivery_lng = order.delivery_address.get("lng")

        if not delivery_lat or not delivery_lng:
            return None

        # Haversine distance (approximate)
        from math import radians, sin, cos, sqrt, atan2

        R = 6371  # Earth radius in km
        lat1, lng1 = radians(float(driver.current_lat)), radians(float(driver.current_lng))
        lat2, lng2 = radians(float(delivery_lat)), radians(float(delivery_lng))

        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        distance_km = R * c

        # Assume 25 km/h average in city
        eta_seconds = int((distance_km / 25) * 3600)
        return max(eta_seconds, 60)  # Minimum 1 minute
