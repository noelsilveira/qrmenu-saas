from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.auth import get_current_active_user, require_role
from app.models import User, Order, Merchant
from app.schemas.whatsapp import (
    OrderAcceptanceRequest, OrderAcceptanceResponse,
    MerchantAcceptAction, MerchantAcceptActionResponse,
    WhatsAppWebhookPayload, WhatsAppMessageWebhook, WhatsAppStatusWebhook,
    CustomerNotificationRequest, CustomerNotificationResponse,
    TimeoutConfig, TimeoutStatus,
)
from app.services.whatsapp_service import WhatsAppService
from app.services.order_service import OrderService

router = APIRouter()

def _get_merchant_id(user: User) -> UUID:
    return user.merchant_id


# ---------------------------------------------------------------------------
# Trigger Acceptance Flow
# ---------------------------------------------------------------------------
@router.post("/acceptance/request", response_model=OrderAcceptanceResponse, status_code=status.HTTP_201_CREATED)
async def request_acceptance(
    data: OrderAcceptanceRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager", "staff")),
):
    """Trigger WhatsApp acceptance flow for an order."""
    merchant_id = _get_merchant_id(current_user)

    # Verify order belongs to merchant
    result = await db.execute(
        select(Order).where(
            Order.id == data.order_id,
            Order.merchant_id == merchant_id
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Get merchant notification phone
    merchant_result = await db.execute(
        select(Merchant).where(Merchant.id == merchant_id)
    )
    merchant = merchant_result.scalar_one_or_none()

    # Build order summary
    service = OrderService(db)
    order_response = await service.get_order(data.order_id, merchant_id)
    items_summary = "\n".join([
        f"• {item.name} x{item.quantity}" 
        for item in (order_response.items if order_response else [])
    ]) if order_response else "Order details"

    # Get merchant phone from settings or fallback
    merchant_phone = merchant.whatsapp_number if merchant and merchant.whatsapp_number else "+97312345678"

    # Send acceptance request
    result = await WhatsAppService.send_acceptance_request(
        order_id=data.order_id,
        merchant_id=merchant_id,
        merchant_phone=merchant_phone,
        customer_phone=order.customer_phone,
        order_summary=items_summary,
        total=order.total,
        timeout_minutes=data.timeout_minutes,
    )

    return OrderAcceptanceResponse(
        order_id=data.order_id,
        acceptance_status="pending",
        timeout_at=datetime.fromisoformat(result["timeout_at"]) if result.get("timeout_at") else None,
        notified_at=datetime.utcnow(),
        merchant_phone=merchant_phone,
        message_id=result.get("message_id"),
    )


# ---------------------------------------------------------------------------
# Manual Respond (via Merchant Portal / API)
# ---------------------------------------------------------------------------
@router.post("/acceptance/respond", response_model=MerchantAcceptActionResponse)
async def respond_acceptance(
    data: MerchantAcceptAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager", "staff")),
):
    """Merchant responds to acceptance request via portal (not WhatsApp)."""
    merchant_id = _get_merchant_id(current_user)

    # Verify order belongs to merchant
    result = await db.execute(
        select(Order).where(
            Order.id == data.order_id,
            Order.merchant_id == merchant_id
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    response = await WhatsAppService.handle_merchant_response(
        order_id=data.order_id,
        action=data.action,
        reason=data.reason,
        responded_by=str(current_user.id),
        db=db,
    )

    return response


# ---------------------------------------------------------------------------
# Get Acceptance Status
# ---------------------------------------------------------------------------
@router.get("/acceptance/{order_id}", response_model=Dict[str, Any])
async def get_acceptance_status(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get current acceptance status for an order."""
    merchant_id = _get_merchant_id(current_user)

    # Verify order belongs to merchant
    result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.merchant_id == merchant_id
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    status = await WhatsAppService.get_acceptance_status(order_id)
    if not status:
        return {
            "order_id": str(order_id),
            "status": "not_requested",
            "message": "No acceptance request was sent for this order"
        }

    return status


# ---------------------------------------------------------------------------
# WhatsApp Webhook Handler
# ---------------------------------------------------------------------------
@router.post("/webhook")
async def whatsapp_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle incoming WhatsApp Business API webhooks.
    Supports both message and status callbacks.
    """
    payload = await request.json()

    # Handle different webhook types
    if payload.get("object") == "whatsapp_business_account":
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # Handle messages
                if "messages" in value:
                    for msg in value.get("messages", []):
                        await _handle_incoming_message(msg, db)

                # Handle message statuses (delivered, read, failed)
                if "statuses" in value:
                    for status in value.get("statuses", []):
                        await _handle_message_status(status)

    return {"status": "ok"}


async def _handle_incoming_message(msg: dict, db: AsyncSession):
    """Process incoming WhatsApp message (button click, text reply)."""
    from_number = msg.get("from")
    msg_type = msg.get("type")

    # Extract button payload or interactive response
    button_payload = None
    if msg_type == "interactive" and msg.get("interactive", {}).get("type") == "button_reply":
        button_payload = msg["interactive"]["button_reply"].get("id")
    elif msg_type == "button":
        button_payload = msg.get("button", {}).get("payload")

    if not button_payload:
        return

    # Parse payload: "accept:order-uuid" or "reject:order-uuid"
    parts = button_payload.split(":")
    if len(parts) != 2:
        return

    action, order_id_str = parts
    if action not in ["accept", "reject"]:
        return

    try:
        order_id = UUID(order_id_str)
    except ValueError:
        return

    # Handle merchant response
    await WhatsAppService.handle_merchant_response(
        order_id=order_id,
        action=action,
        responded_by=from_number,
        db=db,
    )


async def _handle_message_status(status: dict):
    """Process message status update (delivered, read, failed)."""
    # Could update message delivery tracking in DB
    pass


# ---------------------------------------------------------------------------
# Customer Notification
# ---------------------------------------------------------------------------
@router.post("/customer/notify", response_model=CustomerNotificationResponse)
async def notify_customer(
    data: CustomerNotificationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager", "staff")),
):
    """Send manual notification to customer."""
    merchant_id = _get_merchant_id(current_user)

    # Verify order belongs to merchant
    result = await db.execute(
        select(Order).where(
            Order.id == data.order_id,
            Order.merchant_id == merchant_id
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return await WhatsAppService.notify_customer(data)


# ---------------------------------------------------------------------------
# Timeout Configuration
# ---------------------------------------------------------------------------
@router.get("/timeout/config", response_model=TimeoutConfig)
async def get_timeout_config(
    current_user: User = Depends(get_current_active_user),
):
    """Get merchant timeout configuration."""
    # In production, fetch from merchant settings
    return TimeoutConfig(
        enabled=True,
        timeout_minutes=5,
        auto_reject_reason="Merchant did not respond in time",
        fallback_action="auto_reject"
    )


@router.put("/timeout/config", response_model=TimeoutConfig)
async def update_timeout_config(
    data: TimeoutConfig,
    current_user: User = Depends(require_role("owner", "manager")),
):
    """Update merchant timeout configuration."""
    # In production, save to merchant settings
    return data
