from typing import Optional, List, Dict, Any
from uuid import UUID
from decimal import Decimal
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.auth import get_current_active_user, require_role
from app.models import User
from app.schemas.delivery import (
    DeliveryZoneCreate, DeliveryZoneUpdate, DeliveryZoneResponse,
    ZoneMatchRequest, ZoneMatchResponse,
    DriverCreate, DriverUpdate, DriverResponse,
    DriverLocationUpdate, DriverLocationResponse,
    DeliveryAssignmentCreate, DeliveryAssignmentResponse,
    DeliveryStatusUpdate, DeliveryStatus,
    BulkAssignRequest, AutoAssignRequest, AutoAssignResponse,
    DeliveryTrackingResponse, FleetStatusResponse,
)
from app.services.delivery_service import ZoneService, DriverService, DeliveryAssignmentService

router = APIRouter()

def _get_merchant_id(user: User) -> UUID:
    return user.merchant_id


# ---------------------------------------------------------------------------
# Delivery Zones
# ---------------------------------------------------------------------------
@router.post("/zones", response_model=DeliveryZoneResponse, status_code=status.HTTP_201_CREATED)
async def create_zone(
    data: DeliveryZoneCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    """Create a delivery zone with polygon boundaries."""
    merchant_id = _get_merchant_id(current_user)
    service = ZoneService(db)
    zone = await service.create_zone(merchant_id, data.model_dump())
    return zone


@router.get("/zones", response_model=List[DeliveryZoneResponse])
async def list_zones(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all delivery zones for merchant."""
    merchant_id = _get_merchant_id(current_user)
    service = ZoneService(db)
    return await service.list_zones(merchant_id)


@router.get("/zones/{zone_id}", response_model=DeliveryZoneResponse)
async def get_zone(
    zone_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get zone details."""
    merchant_id = _get_merchant_id(current_user)
    service = ZoneService(db)
    zone = await service.get_zone(zone_id, merchant_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    return zone


@router.put("/zones/{zone_id}", response_model=DeliveryZoneResponse)
async def update_zone(
    zone_id: UUID,
    data: DeliveryZoneUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    """Update zone."""
    merchant_id = _get_merchant_id(current_user)
    service = ZoneService(db)
    zone = await service.get_zone(zone_id, merchant_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "boundaries" and value:
            value = [{"lat": b.lat, "lng": b.lng} for b in value]
        setattr(zone, field, value)

    await db.flush()
    await db.refresh(zone)
    return zone


@router.delete("/zones/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_zone(
    zone_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    """Delete zone."""
    merchant_id = _get_merchant_id(current_user)
    service = ZoneService(db)
    deleted = await service.delete_zone(zone_id, merchant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Zone not found")


@router.post("/zones/match", response_model=ZoneMatchResponse)
async def match_zone(
    data: ZoneMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Check if a location is within any delivery zone."""
    merchant_id = _get_merchant_id(current_user)
    service = ZoneService(db)
    return await service.match_zone(merchant_id, data)


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------
@router.post("/drivers", response_model=DriverResponse, status_code=status.HTTP_201_CREATED)
async def create_driver(
    data: DriverCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    """Add a new driver to fleet."""
    merchant_id = _get_merchant_id(current_user)
    service = DriverService(db)
    driver = await service.create_driver(merchant_id, data.model_dump())
    return driver


@router.get("/drivers", response_model=List[DriverResponse])
async def list_drivers(
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all drivers. Filter by status."""
    merchant_id = _get_merchant_id(current_user)
    service = DriverService(db)
    driver_status = None
    if status:
        try:
            from app.schemas.delivery import DriverStatus
            driver_status = DriverStatus(status)
        except ValueError:
            pass
    return await service.list_drivers(merchant_id, driver_status)


@router.get("/drivers/{driver_id}", response_model=DriverResponse)
async def get_driver(
    driver_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get driver details."""
    merchant_id = _get_merchant_id(current_user)
    service = DriverService(db)
    driver = await service.get_driver(driver_id, merchant_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    return driver


@router.put("/drivers/{driver_id}", response_model=DriverResponse)
async def update_driver(
    driver_id: UUID,
    data: DriverUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    """Update driver info."""
    merchant_id = _get_merchant_id(current_user)
    service = DriverService(db)
    driver = await service.get_driver(driver_id, merchant_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(driver, field, value)

    await db.flush()
    await db.refresh(driver)
    return driver


@router.post("/drivers/{driver_id}/location")
async def update_driver_location(
    driver_id: UUID,
    data: DriverLocationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update driver GPS location (called by driver app)."""
    merchant_id = _get_merchant_id(current_user)
    service = DriverService(db)
    driver = await service.update_location(driver_id, merchant_id, data)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    return {"status": "ok", "driver_id": str(driver_id)}


@router.get("/drivers/{driver_id}/location", response_model=DriverLocationResponse)
async def get_driver_location(
    driver_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get driver's current location."""
    merchant_id = _get_merchant_id(current_user)
    service = DriverService(db)

    driver = await service.get_driver(driver_id, merchant_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    loc = await service.get_location(driver_id)
    if not loc:
        raise HTTPException(status_code=404, detail="No location data")

    return DriverLocationResponse(
        driver_id=driver_id,
        name=driver.name,
        lat=loc["lat"],
        lng=loc["lng"],
        accuracy=loc.get("accuracy"),
        heading=loc.get("heading"),
        speed=loc.get("speed"),
        status=driver.status,
        updated_at=datetime.fromisoformat(loc["timestamp"]) if loc.get("timestamp") else datetime.utcnow()
    )


@router.post("/drivers/{driver_id}/status")
async def update_driver_status(
    driver_id: UUID,
    status: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager", "staff")),
):
    """Update driver status (available, busy, offline, on_break)."""
    merchant_id = _get_merchant_id(current_user)
    service = DriverService(db)

    from app.schemas.delivery import DriverStatus
    try:
        driver_status = DriverStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    driver = await service.update_status(driver_id, merchant_id, driver_status)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    return {"status": "ok", "driver_status": driver.status.value}


# ---------------------------------------------------------------------------
# Fleet Dashboard
# ---------------------------------------------------------------------------
@router.get("/fleet/status", response_model=FleetStatusResponse)
async def get_fleet_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get fleet overview: active drivers, deliveries, etc."""
    merchant_id = _get_merchant_id(current_user)
    service = DriverService(db)
    status = await service.get_fleet_status(merchant_id)
    return FleetStatusResponse(**status)


# ---------------------------------------------------------------------------
# Delivery Assignments
# ---------------------------------------------------------------------------
@router.post("/assignments", response_model=DeliveryAssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    data: DeliveryAssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager", "staff")),
):
    """Manually assign a driver to an order."""
    merchant_id = _get_merchant_id(current_user)
    service = DeliveryAssignmentService(db)

    # Verify driver belongs to merchant
    driver_service = DriverService(db)
    driver = await driver_service.get_driver(data.driver_id, merchant_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    assignment = await service.create_assignment(
        merchant_id=merchant_id,
        order_id=data.order_id,
        driver_id=data.driver_id,
        pickup_address=data.pickup_address,
        delivery_address=data.delivery_address,
        delivery_fee=Decimal("1.000"),  # Should calculate from zone
        distance_km=None,
        notes=data.notes
    )
    return assignment


@router.get("/assignments", response_model=List[DeliveryAssignmentResponse])
async def list_assignments(
    status: Optional[str] = Query(None),
    driver_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List delivery assignments with filters."""
    merchant_id = _get_merchant_id(current_user)
    from sqlalchemy import select, and_
    from app.models import DeliveryAssignment as DA

    conditions = [DA.merchant_id == merchant_id]
    if status:
        conditions.append(DA.status == status)
    if driver_id:
        conditions.append(DA.driver_id == driver_id)

    result = await db.execute(
        select(DA).where(and_(*conditions)).order_by(DA.created_at.desc())
    )
    return result.scalars().all()


@router.get("/assignments/{assignment_id}", response_model=DeliveryAssignmentResponse)
async def get_assignment(
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get assignment details."""
    merchant_id = _get_merchant_id(current_user)
    service = DeliveryAssignmentService(db)
    assignment = await service.get_assignment(assignment_id, merchant_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment


@router.put("/assignments/{assignment_id}/status", response_model=DeliveryAssignmentResponse)
async def update_assignment_status(
    assignment_id: UUID,
    data: DeliveryStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager", "staff")),
):
    """Update delivery status: picked_up, en_route, arrived, delivered, cancelled."""
    merchant_id = _get_merchant_id(current_user)
    service = DeliveryAssignmentService(db)

    assignment = await service.update_status(
        assignment_id=assignment_id,
        merchant_id=merchant_id,
        status=data.status,
        lat=data.lat,
        lng=data.lng,
        notes=data.notes
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment


@router.post("/assignments/auto", response_model=AutoAssignResponse)
async def auto_assign(
    data: AutoAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager", "staff")),
):
    """Auto-assign best available driver to order."""
    merchant_id = _get_merchant_id(current_user)
    service = DeliveryAssignmentService(db)
    return await service.auto_assign(merchant_id, data.order_id, data.strategy)


@router.post("/assignments/bulk", response_model=List[AutoAssignResponse])
async def bulk_assign(
    data: BulkAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager", "staff")),
):
    """Bulk assign orders to a specific driver."""
    merchant_id = _get_merchant_id(current_user)
    service = DeliveryAssignmentService(db)

    results = []
    for order_id in data.order_ids:
        # Manual assignment
        assignment = await service.create_assignment(
            merchant_id=merchant_id,
            order_id=order_id,
            driver_id=data.driver_id,
            pickup_address=None,
            delivery_address={},
            delivery_fee=Decimal("1.000"),
            distance_km=None,
            notes="Bulk assignment"
        )
        results.append(AutoAssignResponse(
            order_id=order_id,
            driver_id=data.driver_id,
            assigned=True
        ))

    return results


# ---------------------------------------------------------------------------
# Tracking
# ---------------------------------------------------------------------------
@router.get("/assignments/{assignment_id}/tracking", response_model=DeliveryTrackingResponse)
async def get_tracking(
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get real-time delivery tracking for customer/merchant."""
    merchant_id = _get_merchant_id(current_user)
    service = DeliveryAssignmentService(db)
    tracking = await service.get_tracking(assignment_id, merchant_id)
    if not tracking:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return tracking
