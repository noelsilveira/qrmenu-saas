from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.db.session import get_db
from app.schemas.driver import DriverCreate, DriverResponse, DriverLocationUpdate
from app.services.delivery.driver_service import DriverService
from app.core.auth import get_current_user

router = APIRouter()

@router.get("")
async def list_drivers(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = DriverService(db)
    return await service.list_drivers(current_user.merchant_id)

@router.post("")
async def create_driver(
    driver_in: DriverCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = DriverService(db)
    return await service.create_driver(driver_in, current_user.merchant_id)

@router.post("/{driver_id}/documents")
async def upload_driver_documents(
    driver_id: UUID,
    license_doc: UploadFile = File(...),
    insurance_doc: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = DriverService(db)
    return await service.upload_documents(driver_id, license_doc, insurance_doc)

@router.post("/{driver_id}/location")
async def update_driver_location(
    driver_id: UUID,
    location: DriverLocationUpdate,
    db: AsyncSession = Depends(get_db)
):
    """GPS ping from driver mobile app"""
    from app.services.delivery.tracking_service import GPSTrackingService
    service = GPSTrackingService(db)
    return await service.handle_location_update(driver_id, location)

@router.get("/{driver_id}/earnings")
async def get_driver_earnings(
    driver_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    from app.services.delivery.settlement_service import DriverSettlementService
    service = DriverSettlementService(db)
    return await service.get_period_earnings(driver_id)
