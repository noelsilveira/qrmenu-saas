from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.db.session import get_db
from app.schemas.third_party import PartnerCreate, PartnerResponse, OrderPushRequest
from app.services.third_party.adapter_service import ThirdPartyAdapterService
from app.core.auth import get_current_user

router = APIRouter()

@router.get("/partners")
async def list_partners(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = ThirdPartyAdapterService(db)
    return await service.list_partners(current_user.merchant_id)

@router.post("/partners")
async def add_partner(
    partner_in: PartnerCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = ThirdPartyAdapterService(db)
    return await service.add_partner(partner_in, current_user.merchant_id)

@router.post("/orders/{order_id}/push")
async def push_to_partner(
    order_id: UUID,
    partner_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = ThirdPartyAdapterService(db)
    return await service.push_order(order_id, partner_id)

@router.post("/webhooks/{partner_name}")
async def partner_webhook(
    partner_name: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Handle incoming webhooks from Talabat, Zomato, Jahez, etc."""
    payload = await request.json()
    service = ThirdPartyAdapterService(db)
    return await service.handle_webhook(partner_name, payload)
