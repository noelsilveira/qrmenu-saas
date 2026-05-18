from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.db.session import get_db
from app.schemas.delivery import ZoneCreate, ZoneResponse, PricingRuleCreate, FeeCalculationRequest
from app.services.delivery.zone_service import ZoneService
from app.services.delivery.pricing_service import PricingService
from app.core.auth import get_current_user

router = APIRouter()

@router.get("/zones", response_model=list[ZoneResponse])
async def list_zones(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = ZoneService(db)
    return await service.list_zones(current_user.merchant_id)

@router.post("/zones", response_model=ZoneResponse)
async def create_zone(
    zone_in: ZoneCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = ZoneService(db)
    return await service.create_zone(zone_in, current_user.merchant_id)

@router.post("/calculate-fee")
async def calculate_delivery_fee(
    request: FeeCalculationRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = PricingService(db)
    return await service.calculate_fee(
        lat=request.lat, lng=request.lng,
        order_subtotal=request.subtotal,
        merchant_id=current_user.merchant_id
    )

@router.get("/surge-status")
async def get_surge_status(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = PricingService(db)
    return await service.get_current_surge_multipliers(current_user.merchant_id)
