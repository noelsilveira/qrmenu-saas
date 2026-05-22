import math
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Order, Merchant, DeliveryZone, Driver, DeliveryAssignment,
)
from app.schemas.delivery import (
    DeliveryStatus, DriverStatus, VehicleType,
    ZoneBoundary, ZoneMatchRequest, ZoneMatchResponse,
    DriverLocationUpdate, AutoAssignResponse,
    GPSTrackPoint, DeliveryTrackingResponse,
)
from app.services.order_service import OrderService
from app.core.cache import cache_get, cache_set, cache_delete


class GeoUtils:
    """Geographic calculation utilities."""

    @staticmethod
    def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate distance between two points in kilometers."""
        R = 6371  # Earth radius in km
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlng / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    @staticmethod
    def point_in_polygon(lat: float, lng: float, boundaries: List[ZoneBoundary]) -> bool:
        """Ray-casting algorithm to check if point is inside polygon."""
        n = len(boundaries)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = boundaries[i].lng, boundaries[i].lat
            xj, yj = boundaries[j].lng, boundaries[j].lat
            if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside

    @staticmethod
    def polygon_centroid(boundaries: List[ZoneBoundary]) -> Tuple[float, float]:
        """Calculate centroid of polygon."""
        lats = [b.lat for b in boundaries]
        lngs = [b.lng for b in boundaries]
        return sum(lats) / len(lats), sum(lngs) / len(lngs)


class ZoneService:
    """Delivery zone management and matching."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_zone(self, merchant_id: UUID, data: Dict[str, Any]) -> DeliveryZone:
        zone = DeliveryZone(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            name=data["name"],
            boundaries=[{"lat": b["lat"], "lng": b["lng"]} for b in data["boundaries"]],
            base_fee=data.get("base_fee", Decimal("1.000")),
            per_km_fee=data.get("per_km_fee", Decimal("0.500")),
            min_order_value=data.get("min_order_value", Decimal("5.000")),
            free_delivery_threshold=data.get("free_delivery_threshold"),
            max_delivery_distance_km=data.get("max_delivery_distance_km", Decimal("15.0")),
            estimated_delivery_min=data.get("estimated_delivery_min", 30),
            is_active=data.get("is_active", True),
        )
        self.db.add(zone)
        await self.db.flush()
        await self.db.refresh(zone)
        return zone

    async def list_zones(self, merchant_id: UUID) -> List[DeliveryZone]:
        result = await self.db.execute(
            select(DeliveryZone)
            .where(DeliveryZone.merchant_id == merchant_id)
            .order_by(DeliveryZone.name)
        )
        return result.scalars().all()

    async def get_zone(self, zone_id: UUID, merchant_id: UUID) -> Optional[DeliveryZone]:
        result = await self.db.execute(
            select(DeliveryZone).where(
                DeliveryZone.id == zone_id,
                DeliveryZone.merchant_id == merchant_id
            )
        )
        return result.scalar_one_or_none()

    async def match_zone(self, merchant_id: UUID, request: ZoneMatchRequest) -> ZoneMatchResponse:
        """Find which zone covers the given coordinates."""
        zones_result = await self.db.execute(
            select(DeliveryZone)
            .where(
                DeliveryZone.merchant_id == merchant_id,
                DeliveryZone.is_active == True
            )
        )
        zones = zones_result.scalars().all()

        for zone in zones:
            boundaries = [ZoneBoundary(lat=b["lat"], lng=b["lng"]) for b in (zone.boundaries or [])]
            if GeoUtils.point_in_polygon(request.lat, request.lng, boundaries):
                # Calculate distance from zone centroid to delivery point
                centroid_lat, centroid_lng = GeoUtils.polygon_centroid(boundaries)
                distance = GeoUtils.haversine_distance(centroid_lat, centroid_lng, request.lat, request.lng)

                # Check max distance
                if distance > float(zone.max_delivery_distance_km):
                    continue

                # Check min order value
                fee = zone.base_fee + Decimal(str(distance)) * zone.per_km_fee
                if request.order_value and request.order_value < zone.min_order_value:
                    return ZoneMatchResponse(
                        zone_id=zone.id,
                        zone_name=zone.name,
                        deliverable=False,
                        base_fee=fee,
                        distance_km=Decimal(str(round(distance, 2))),
                        estimated_min=zone.estimated_delivery_min,
                        reason=f"Minimum order value is BHD {zone.min_order_value}"
                    )

                # Check free delivery threshold
                if zone.free_delivery_threshold and request.order_value and request.order_value >= zone.free_delivery_threshold:
                    fee = Decimal("0.000")

                return ZoneMatchResponse(
                    zone_id=zone.id,
                    zone_name=zone.name,
                    deliverable=True,
                    base_fee=fee.quantize(Decimal("0.001")),
                    distance_km=Decimal(str(round(distance, 2))),
                    estimated_min=zone.estimated_delivery_min
                )

        return ZoneMatchResponse(
            deliverable=False,
            base_fee=Decimal("0.000"),
            reason="No delivery zone covers this location"
        )

    async def delete_zone(self, zone_id: UUID, merchant_id: UUID) -> bool:
        zone = await self.get_zone(zone_id, merchant_id)
        if not zone:
            return False
        await self.db.delete(zone)
        await self.db.flush()
        return True


class DriverService:
    """Driver management and location tracking."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_driver(self, merchant_id: UUID, data: Dict[str, Any]) -> Driver:
        driver = Driver(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            name=data["name"],
            phone=data["phone"],
            email=data.get("email"),
            vehicle_type=data.get("vehicle_type", VehicleType.motorcycle),
            vehicle_plate=data.get("vehicle_plate"),
            status=DriverStatus.available,
            max_orders_per_run=data.get("max_orders_per_run", 3),
            total_deliveries=0,
            rating=Decimal("5.0"),
        )
        self.db.add(driver)
        await self.db.flush()
        await self.db.refresh(driver)
        return driver

    async def list_drivers(self, merchant_id: UUID, status: Optional[DriverStatus] = None) -> List[Driver]:
        conditions = [Driver.merchant_id == merchant_id]
        if status:
            conditions.append(Driver.status == status)

        result = await self.db.execute(
            select(Driver).where(and_(*conditions)).order_by(Driver.name)
        )
        return result.scalars().all()

    async def get_driver(self, driver_id: UUID, merchant_id: UUID) -> Optional[Driver]:
        result = await self.db.execute(
            select(Driver).where(
                Driver.id == driver_id,
                Driver.merchant_id == merchant_id
            )
        )
        return result.scalar_one_or_none()

    async def update_location(self, driver_id: UUID, merchant_id: UUID, data: DriverLocationUpdate) -> Optional[Driver]:
        driver = await self.get_driver(driver_id, merchant_id)
        if not driver:
            return None

        driver.current_lat = data.lat
        driver.current_lng = data.lng
        driver.last_location_at = datetime.utcnow()
        await self.db.flush()

        # Cache location for real-time tracking
        await cache_set(
            f"driver:location:{driver_id}",
            {
                "lat": data.lat,
                "lng": data.lng,
                "accuracy": data.accuracy,
                "heading": data.heading,
                "speed": data.speed,
                "timestamp": datetime.utcnow().isoformat(),
            },
            ttl_seconds=300
        )

        return driver

    async def update_status(self, driver_id: UUID, merchant_id: UUID, status: DriverStatus) -> Optional[Driver]:
        driver = await self.get_driver(driver_id, merchant_id)
        if not driver:
            return None
        driver.status = status
        await self.db.flush()
        return driver

    async def get_location(self, driver_id: UUID) -> Optional[Dict[str, Any]]:
        """Get cached location or fall back to DB."""
        cached = await cache_get(f"driver:location:{driver_id}")
        if cached:
            return cached

        driver = await self.db.execute(
            select(Driver).where(Driver.id == driver_id)
        )
        driver = driver.scalar_one_or_none()
        if driver and driver.current_lat and driver.current_lng:
            return {
                "lat": driver.current_lat,
                "lng": driver.current_lng,
                "timestamp": driver.last_location_at.isoformat() if driver.last_location_at else None,
            }
        return None

    async def get_fleet_status(self, merchant_id: UUID) -> Dict[str, Any]:
        """Get overall fleet status."""
        result = await self.db.execute(
            select(Driver).where(Driver.merchant_id == merchant_id)
        )
        drivers = result.scalars().all()

        active_deliveries = await self.db.execute(
            select(DeliveryAssignment).where(
                DeliveryAssignment.merchant_id == merchant_id,
                DeliveryAssignment.status.in_([
                    DeliveryStatus.picked_up,
                    DeliveryStatus.en_route,
                    DeliveryStatus.arrived
                ])
            )
        )
        active_count = len(active_deliveries.scalars().all())

        pending = await self.db.execute(
            select(DeliveryAssignment).where(
                DeliveryAssignment.merchant_id == merchant_id,
                DeliveryAssignment.status == DeliveryStatus.pending
            )
        )
        pending_count = len(pending.scalars().all())

        return {
            "total_drivers": len(drivers),
            "available_drivers": sum(1 for d in drivers if d.status == DriverStatus.available),
            "busy_drivers": sum(1 for d in drivers if d.status == DriverStatus.busy),
            "offline_drivers": sum(1 for d in drivers if d.status == DriverStatus.offline),
            "active_deliveries": active_count,
            "pending_assignments": pending_count,
        }


class DeliveryAssignmentService:
    """Delivery assignment, tracking, and status management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_assignment(
        self, merchant_id: UUID, order_id: UUID, driver_id: UUID,
        pickup_address: Optional[dict], delivery_address: dict,
        delivery_fee: Decimal, distance_km: Optional[Decimal], notes: Optional[str]
    ) -> DeliveryAssignment:
        # Get driver name
        driver_result = await self.db.execute(
            select(Driver).where(Driver.id == driver_id)
        )
        driver = driver_result.scalar_one_or_none()
        driver_name = driver.name if driver else "Unknown"

        assignment = DeliveryAssignment(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            order_id=order_id,
            driver_id=driver_id,
            driver_name=driver_name,
            status=DeliveryStatus.assigned,
            pickup_address=pickup_address,
            delivery_address=delivery_address,
            estimated_pickup_at=datetime.utcnow() + timedelta(minutes=10),
            estimated_delivery_at=datetime.utcnow() + timedelta(minutes=30),
            delivery_fee=delivery_fee,
            distance_km=distance_km,
            notes=notes,
        )
        self.db.add(assignment)

        # Update driver status
        if driver:
            driver.status = DriverStatus.busy

        await self.db.flush()
        await self.db.refresh(assignment)
        return assignment

    async def get_assignment(self, assignment_id: UUID, merchant_id: UUID) -> Optional[DeliveryAssignment]:
        result = await self.db.execute(
            select(DeliveryAssignment).where(
                DeliveryAssignment.id == assignment_id,
                DeliveryAssignment.merchant_id == merchant_id
            )
        )
        return result.scalar_one_or_none()

    async def get_assignment_by_order(self, order_id: UUID, merchant_id: UUID) -> Optional[DeliveryAssignment]:
        result = await self.db.execute(
            select(DeliveryAssignment).where(
                DeliveryAssignment.order_id == order_id,
                DeliveryAssignment.merchant_id == merchant_id
            )
        )
        return result.scalar_one_or_none()

    async def update_status(
        self, assignment_id: UUID, merchant_id: UUID,
        status: DeliveryStatus, lat: Optional[float], lng: Optional[float],
        notes: Optional[str]
    ) -> Optional[DeliveryAssignment]:
        assignment = await self.get_assignment(assignment_id, merchant_id)
        if not assignment:
            return None

        assignment.status = status
        if notes:
            assignment.notes = notes

        if status == DeliveryStatus.picked_up:
            assignment.actual_pickup_at = datetime.utcnow()
        elif status == DeliveryStatus.delivered:
            assignment.actual_delivery_at = datetime.utcnow()
            # Free up driver
            driver_result = await self.db.execute(
                select(Driver).where(Driver.id == assignment.driver_id)
            )
            driver = driver_result.scalar_one_or_none()
            if driver:
                driver.status = DriverStatus.available
                driver.total_deliveries += 1
        elif status == DeliveryStatus.cancelled:
            driver_result = await self.db.execute(
                select(Driver).where(Driver.id == assignment.driver_id)
            )
            driver = driver_result.scalar_one_or_none()
            if driver:
                driver.status = DriverStatus.available

        await self.db.flush()

        # Cache tracking update
        if lat and lng:
            await cache_set(
                f"delivery:track:{assignment_id}",
                {
                    "lat": lat,
                    "lng": lng,
                    "status": status.value,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                ttl_seconds=300
            )

        return assignment

    async def auto_assign(self, merchant_id: UUID, order_id: UUID, strategy: str = "nearest") -> AutoAssignResponse:
        """Automatically assign the best available driver."""
        # Get order details
        order_result = await self.db.execute(
            select(Order).where(
                Order.id == order_id,
                Order.merchant_id == merchant_id
            )
        )
        order = order_result.scalar_one_or_none()
        if not order:
            return AutoAssignResponse(
                order_id=order_id,
                assigned=False,
                reason="Order not found"
            )

        # Get delivery address coordinates
        delivery_address = order.delivery_address or {}
        if not delivery_address or "lat" not in delivery_address:
            return AutoAssignResponse(
                order_id=order_id,
                assigned=False,
                reason="Delivery address has no coordinates"
            )

        dest_lat = delivery_address["lat"]
        dest_lng = delivery_address["lng"]

        # Get available drivers
        drivers_result = await self.db.execute(
            select(Driver).where(
                Driver.merchant_id == merchant_id,
                Driver.status == DriverStatus.available
            )
        )
        drivers = drivers_result.scalars().all()

        if not drivers:
            return AutoAssignResponse(
                order_id=order_id,
                assigned=False,
                reason="No available drivers"
            )

        # Find best driver based on strategy
        best_driver = None
        best_distance = float('inf')

        for driver in drivers:
            if not driver.current_lat or not driver.current_lng:
                continue

            # Check driver load
            active_count = await self.db.execute(
                select(DeliveryAssignment).where(
                    DeliveryAssignment.driver_id == driver.id,
                    DeliveryAssignment.status.in_([
                        DeliveryStatus.assigned,
                        DeliveryStatus.picked_up,
                        DeliveryStatus.en_route
                    ])
                )
            )
            active = len(active_count.scalars().all())
            if active >= driver.max_orders_per_run:
                continue

            distance = GeoUtils.haversine_distance(
                driver.current_lat, driver.current_lng, dest_lat, dest_lng
            )

            if strategy == "nearest" and distance < best_distance:
                best_driver = driver
                best_distance = distance
            elif strategy == "round_robin":
                # Simple round-robin: pick driver with fewest deliveries today
                if best_driver is None or driver.total_deliveries < best_driver.total_deliveries:
                    best_driver = driver
                    best_distance = distance
            elif strategy == "load_balanced":
                # Pick driver with lowest active load
                if best_driver is None or active < best_driver.max_orders_per_run:
                    best_driver = driver
                    best_distance = distance

        if not best_driver:
            return AutoAssignResponse(
                order_id=order_id,
                assigned=False,
                reason="No suitable driver found"
            )

        # Create assignment
        zone_service = ZoneService(self.db)
        match = await zone_service.match_zone(
            merchant_id,
            ZoneMatchRequest(lat=dest_lat, lng=dest_lng, order_value=order.total)
        )

        assignment = await self.create_assignment(
            merchant_id=merchant_id,
            order_id=order_id,
            driver_id=best_driver.id,
            pickup_address=None,
            delivery_address=delivery_address,
            delivery_fee=match.base_fee if match.deliverable else Decimal("1.000"),
            distance_km=match.distance_km or Decimal(str(round(best_distance, 2))),
            notes=None
        )

        return AutoAssignResponse(
            order_id=order_id,
            driver_id=best_driver.id,
            driver_name=best_driver.name,
            distance_km=Decimal(str(round(best_distance, 2))),
            eta_minutes=match.estimated_min if match.deliverable else 30,
            assigned=True
        )

    async def get_tracking(self, assignment_id: UUID, merchant_id: UUID) -> Optional[DeliveryTrackingResponse]:
        """Get real-time delivery tracking info."""
        assignment = await self.get_assignment(assignment_id, merchant_id)
        if not assignment:
            return None

        # Get driver details
        driver_result = await self.db.execute(
            select(Driver).where(Driver.id == assignment.driver_id)
        )
        driver = driver_result.scalar_one_or_none()

        # Get cached location
        cached = await cache_get(f"delivery:track:{assignment_id}")
        current_lat = cached.get("lat") if cached else None
        current_lng = cached.get("lng") if cached else None

        if not current_lat and driver:
            current_lat = driver.current_lat
            current_lng = driver.current_lng

        # Build route from cache history
        route = []
        if cached:
            route.append(GPSTrackPoint(
                lat=cached["lat"],
                lng=cached["lng"],
                timestamp=datetime.fromisoformat(cached["timestamp"]),
            ))

        # Calculate distance remaining
        distance_remaining = None
        if current_lat and current_lng and assignment.delivery_address:
            dest_lat = assignment.delivery_address.get("lat")
            dest_lng = assignment.delivery_address.get("lng")
            if dest_lat and dest_lng:
                distance_remaining = Decimal(str(round(
                    GeoUtils.haversine_distance(current_lat, current_lng, dest_lat, dest_lng), 2
                )))

        return DeliveryTrackingResponse(
            delivery_id=assignment.id,
            order_id=assignment.order_id,
            driver_id=assignment.driver_id,
            driver_name=driver.name if driver else "Unknown",
            driver_phone=driver.phone if driver else "",
            status=assignment.status,
            current_lat=current_lat,
            current_lng=current_lng,
            route=route,
            estimated_delivery_at=assignment.estimated_delivery_at,
            actual_delivery_at=assignment.actual_delivery_at,
            customer_address=assignment.delivery_address or {},
            distance_remaining_km=distance_remaining
        )
