import os
import uuid
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, List
from uuid import UUID

from app.schemas.whatsapp import (
    AcceptanceStatus, WhatsAppButton, WhatsAppInteractiveMessage,
    WhatsAppTextMessage, CustomerNotificationRequest, CustomerNotificationResponse,
    TimeoutConfig, MerchantAcceptAction, MerchantAcceptActionResponse
)
from app.schemas.orders import OrderStatus, PaymentStatus
from app.services.order_service import OrderService
from app.core.cache import cache_get, cache_set, cache_delete

# WhatsApp Business API config
WABA_API_URL = os.getenv("WABA_API_URL", "https://graph.facebook.com/v18.0")
WABA_PHONE_NUMBER_ID = os.getenv("WABA_PHONE_NUMBER_ID", "")
WABA_ACCESS_TOKEN = os.getenv("WABA_ACCESS_TOKEN", "")

# respond.io fallback
RESPOND_IO_API_URL = os.getenv("RESPOND_IO_API_URL", "https://app.respond.io/api/v1")
RESPOND_IO_TOKEN = os.getenv("RESPOND_IO_TOKEN", "")


class WhatsAppService:
    """
    WhatsApp Acceptance Flow Service.
    Handles merchant acceptance requests, timeout engine, and customer notifications.
    """

    @staticmethod
    async def send_acceptance_request(
        order_id: UUID,
        merchant_id: UUID,
        merchant_phone: str,
        customer_phone: Optional[str],
        order_summary: str,
        total: Decimal,
        timeout_minutes: int = 5,
    ) -> Dict[str, Any]:
        """Send interactive Accept/Reject message to merchant."""

        # Build interactive message with buttons
        message = WhatsAppInteractiveMessage(
            to=merchant_phone,
            header_text=f"New Order #{str(order_id)[:8]}",
            body_text=f"{order_summary}\n\nTotal: BHD {total}\n\nRespond within {timeout_minutes} minutes or order will be auto-rejected.",
            footer_text="Powered by QRMenu SaaS",
            buttons=[
                WhatsAppButton(type="reply", title="✅ Accept", id=f"accept:{order_id}"),
                WhatsAppButton(type="reply", title="❌ Reject", id=f"reject:{order_id}"),
            ]
        )

        # Send via WhatsApp Business API
        result = await WhatsAppService._send_interactive_message(message)

        # Store pending acceptance in cache with TTL
        acceptance_data = {
            "order_id": str(order_id),
            "merchant_id": str(merchant_id),
            "merchant_phone": merchant_phone,
            "customer_phone": customer_phone,
            "status": AcceptanceStatus.pending.value,
            "timeout_minutes": timeout_minutes,
            "sent_at": datetime.utcnow().isoformat(),
            "timeout_at": (datetime.utcnow() + timedelta(minutes=timeout_minutes)).isoformat(),
            "message_id": result.get("message_id"),
        }
        await cache_set(
            f"acceptance:{order_id}",
            acceptance_data,
            ttl_seconds=timeout_minutes * 60 + 300  # Extra 5 min buffer
        )

        # Schedule timeout task
        asyncio.create_task(
            WhatsAppService._timeout_task(order_id, timeout_minutes)
        )

        return {
            "order_id": order_id,
            "message_id": result.get("message_id"),
            "status": "sent",
            "timeout_at": acceptance_data["timeout_at"],
        }

    @staticmethod
    async def _send_interactive_message(message: WhatsAppInteractiveMessage) -> Dict[str, Any]:
        """Send interactive message via WhatsApp Business API."""
        import aiohttp

        if not WABA_ACCESS_TOKEN or not WABA_PHONE_NUMBER_ID:
            # Fallback: simulate send for testing
            return {"message_id": f"test_{uuid.uuid4().hex[:12]}", "status": "sent"}

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": message.to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": message.header_text
                } if message.header_text else None,
                "body": {"text": message.body_text},
                "footer": {"text": message.footer_text} if message.footer_text else None,
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": btn.id,
                                "title": btn.title
                            }
                        }
                        for btn in message.buttons
                    ]
                }
            }
        }

        # Remove None values
        if payload["interactive"]["header"] is None:
            del payload["interactive"]["header"]
        if payload["interactive"]["footer"] is None:
            del payload["interactive"]["footer"]

        url = f"{WABA_API_URL}/{WABA_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WABA_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {
                        "message_id": data.get("messages", [{}])[0].get("id"),
                        "status": "sent"
                    }
                return {"error": data, "status": "failed"}

    @staticmethod
    async def _send_text_message(message: WhatsAppTextMessage) -> Dict[str, Any]:
        """Send plain text message via WhatsApp Business API."""
        import aiohttp

        if not WABA_ACCESS_TOKEN or not WABA_PHONE_NUMBER_ID:
            return {"message_id": f"test_{uuid.uuid4().hex[:12]}", "status": "sent"}

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": message.to,
            "type": "text",
            "text": {"body": message.body}
        }

        url = f"{WABA_API_URL}/{WABA_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WABA_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {
                        "message_id": data.get("messages", [{}])[0].get("id"),
                        "status": "sent"
                    }
                return {"error": data, "status": "failed"}

    @staticmethod
    async def _timeout_task(order_id: UUID, timeout_minutes: int):
        """Background task: auto-reject order if merchant doesn't respond."""
        await asyncio.sleep(timeout_minutes * 60)

        # Check if acceptance is still pending
        data = await cache_get(f"acceptance:{order_id}")
        if not data:
            return  # Already processed or expired

        if data.get("status") == AcceptanceStatus.pending.value:
            # Auto-reject
            from app.db.session import async_session
            async with async_session() as db:
                service = OrderService(db)
                try:
                    merchant_id = None
                    if data.get("merchant_id"):
                        merchant_id = UUID(data["merchant_id"])
                    await service.update_status(
                        order_id=order_id,
                        merchant_id=merchant_id,
                        new_status=OrderStatus.cancelled,
                        reason="Auto-rejected: merchant did not respond in time"
                    )
                    await db.commit()
                except Exception:
                    await db.rollback()
                    pass  # Order may not exist or already processed

                # Update acceptance cache
                data["status"] = AcceptanceStatus.auto_rejected.value
                data["auto_rejected_at"] = datetime.utcnow().isoformat()
                await cache_set(f"acceptance:{order_id}", data, ttl_seconds=3600)

                # Notify customer
                customer_phone = data.get("customer_phone")
                if customer_phone:
                    await WhatsAppService.notify_customer(
                        CustomerNotificationRequest(
                            order_id=order_id,
                            customer_phone=customer_phone,
                            notification_type="order_rejected",
                            message="We apologize, but your order was not accepted by the merchant. Please try again or contact support."
                        )
                    )

    @staticmethod
    async def handle_merchant_response(
        order_id: UUID,
        action: str,
        reason: Optional[str] = None,
        responded_by: Optional[str] = None,
        db=None,
    ) -> MerchantAcceptActionResponse:
        """Handle merchant Accept/Reject response from WhatsApp."""

        # Get acceptance data
        acceptance_data = await cache_get(f"acceptance:{order_id}")

        if not acceptance_data:
            return MerchantAcceptActionResponse(
                order_id=order_id,
                action=action,
                new_status="unknown",
                order_status="unknown",
                customer_notified=False
            )

        if acceptance_data.get("status") != AcceptanceStatus.pending.value:
            return MerchantAcceptActionResponse(
                order_id=order_id,
                action=action,
                new_status=acceptance_data["status"],
                order_status="unknown",
                customer_notified=False
            )

        # Update order status
        async def _do_update(db_session):
            service = OrderService(db_session)

            merchant_id = None
            if acceptance_data.get("merchant_id"):
                merchant_id = UUID(acceptance_data["merchant_id"])

            if action == "accept":
                order = await service.update_status(
                    order_id=order_id,
                    merchant_id=merchant_id,
                    new_status=OrderStatus.confirmed
                )
                acceptance_data["status"] = AcceptanceStatus.accepted.value
                customer_notification_type = "order_accepted"
                customer_message = f"Great news! Your order #{str(order_id)[:8]} has been accepted and is being prepared. Estimated ready time: {order.estimated_ready_at.strftime('%H:%M') if order.estimated_ready_at else 'soon'}."
                new_status = "accepted"

            else:  # reject
                order = await service.update_status(
                    order_id=order_id,
                    merchant_id=merchant_id,
                    new_status=OrderStatus.cancelled,
                    reason=reason or "Merchant rejected the order"
                )
                acceptance_data["status"] = AcceptanceStatus.rejected.value
                customer_notification_type = "order_rejected"
                customer_message = f"We apologize, but your order #{str(order_id)[:8]} could not be accepted. {reason or 'Please try again or contact support.'}"
                new_status = "rejected"

            acceptance_data["responded_at"] = datetime.utcnow().isoformat()
            acceptance_data["responded_by"] = responded_by
            acceptance_data["reason"] = reason
            await cache_set(f"acceptance:{order_id}", acceptance_data, ttl_seconds=3600)

            # Notify customer
            customer_notified = False
            if acceptance_data.get("customer_phone"):
                result = await WhatsAppService.notify_customer(
                    CustomerNotificationRequest(
                        order_id=order_id,
                        customer_phone=acceptance_data["customer_phone"],
                        notification_type=customer_notification_type,
                        message=customer_message
                    )
                )
                customer_notified = result.sent

            return order, new_status, customer_notified

        if db is not None:
            order, new_status, customer_notified = await _do_update(db)
        else:
            from app.db.session import async_session
            async with async_session() as db_session:
                order, new_status, customer_notified = await _do_update(db_session)
                await db_session.commit()

        return MerchantAcceptActionResponse(
            order_id=order_id,
            action=action,
            new_status=new_status,
            order_status=order.status.value.lower() if order else "unknown",
            customer_notified=customer_notified
        )

    @staticmethod
    async def notify_customer(request: CustomerNotificationRequest) -> CustomerNotificationResponse:
        """Send notification to customer via WhatsApp."""
        message = WhatsAppTextMessage(
            to=request.customer_phone,
            body=request.message or WhatsAppService._default_customer_message(request.notification_type, request.order_id)
        )

        result = await WhatsAppService._send_text_message(message)

        return CustomerNotificationResponse(
            order_id=request.order_id,
            sent=result.get("status") == "sent",
            message_id=result.get("message_id"),
            channel="whatsapp",
            timestamp=datetime.utcnow()
        )

    @staticmethod
    def _default_customer_message(notification_type: str, order_id: UUID) -> str:
        messages = {
            "order_accepted": f"Your order #{str(order_id)[:8]} has been accepted! We are preparing it now.",
            "order_rejected": f"We apologize, but your order #{str(order_id)[:8]} could not be accepted.",
            "order_ready": f"Your order #{str(order_id)[:8]} is ready for pickup/delivery!",
            "order_delayed": f"Your order #{str(order_id)[:8]} is running slightly behind. We appreciate your patience.",
        }
        return messages.get(notification_type, f"Update on your order #{str(order_id)[:8]}.")

    @staticmethod
    async def get_acceptance_status(order_id: UUID) -> Optional[Dict[str, Any]]:
        """Get current acceptance status for an order."""
        data = await cache_get(f"acceptance:{order_id}")
        if not data:
            return None

        timeout_at = datetime.fromisoformat(data["timeout_at"]) if data.get("timeout_at") else None
        is_expired = timeout_at and timeout_at < datetime.utcnow()
        time_remaining = int((timeout_at - datetime.utcnow()).total_seconds()) if timeout_at and not is_expired else 0

        return {
            "order_id": order_id,
            "status": data.get("status"),
            "timeout_at": timeout_at,
            "time_remaining_seconds": time_remaining if time_remaining > 0 else None,
            "is_expired": is_expired,
            "responded_at": data.get("responded_at"),
            "responded_by": data.get("responded_by"),
            "reason": data.get("reason"),
            "message_id": data.get("message_id"),
        }

    @staticmethod
    async def cancel_timeout(order_id: UUID):
        """Cancel pending timeout task (e.g., when merchant responds manually via portal)."""
        await cache_delete(f"acceptance:{order_id}")
