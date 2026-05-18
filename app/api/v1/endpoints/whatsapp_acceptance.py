from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.db.session import get_db
from app.services.whatsapp.acceptance_service import AcceptanceService
from app.core.auth import get_current_user

router = APIRouter()

@router.post("/webhooks/interactive")
async def whatsapp_interactive_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Handle Meta WhatsApp interactive button responses"""
    payload = await request.json()
    service = AcceptanceService(db)
    return await service.handle_interactive_response(payload)

@router.post("/webhooks/delivery")
async def whatsapp_delivery_status_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Handle Meta message delivery status updates"""
    payload = await request.json()
    service = AcceptanceService(db)
    return await service.handle_delivery_status(payload)

@router.get("/merchant/acceptance-stats")
async def get_acceptance_stats(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    from app.services.whatsapp.analytics_service import WhatsAppAnalyticsService
    service = WhatsAppAnalyticsService(db)
    return await service.get_merchant_dashboard(current_user.merchant_id, days)
